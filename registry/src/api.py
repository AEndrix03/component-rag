from __future__ import annotations

import hashlib
import logging
from typing import Any

from botocore.exceptions import ClientError
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse

from database import RegistryDB
from settings import RegistrySettings
from storage import S3Storage

log = logging.getLogger(__name__)


def object_key_for_sha256(sha256: str) -> str:
    return f"blobs/sha256/{sha256}.tar.gz"


def make_app(settings: RegistrySettings) -> FastAPI:
    db = RegistryDB(settings.db_path)
    db.init_schema()

    storage = S3Storage(
        bucket=settings.s3_bucket,
        endpoint_url=settings.s3_endpoint_url,
        region=settings.s3_region,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        force_path_style=settings.s3_force_path_style,
    )
    storage.ensure_bucket()

    app = FastAPI(title="CPM Registry", version="0.1.0")

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.head("/v1/packages/{name}/{version}")
    def head_exists(name: str, version: str):
        if db.exists(name, version):
            return Response(status_code=200)
        return Response(status_code=404)

    @app.get("/v1/packages/{name}/{version}")
    def get_metadata(name: str, version: str):
        row = db.get_version(name, version)
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        return {
            "name": row.name,
            "version": row.version,
            "sha256": row.sha256,
            "size_bytes": row.size_bytes,
            "object_key": row.object_key,
            "checksum": row.checksum,
            "published_at": row.published_at,
            "yanked": bool(row.yanked),
        }

    @app.get("/v1/packages/{name}")
    def list_package(name: str, include_yanked: bool = False):
        versions = db.list_versions(name, include_yanked=include_yanked)
        return {"name": name, "versions": versions}

    @app.post("/v1/resolve")
    async def resolve_source(payload: dict[str, Any]):
        uri = str(payload.get("uri") or "").strip()
        if not uri:
            raise HTTPException(status_code=400, detail="uri is required")
        cached = db.get_resolution(uri)
        if cached:
            return {
                "uri": cached["uri"],
                "resolved_uri": cached["resolved_uri"],
                "digest": cached["digest"],
                "refs": cached["refs"],
                "trust": cached["trust"],
                "cached": True,
            }

        digest = _digest_for_uri(uri)
        refs = [
            {"kind": "sbom", "present": False},
            {"kind": "signature", "present": False},
            {"kind": "provenance", "present": False},
        ]
        trust = {"trust_score": 0.0, "strict_failures": []}
        db.upsert_resolution(
            uri=uri,
            resolved_uri=uri,
            digest=digest,
            refs=refs,
            trust=trust,
        )
        return {
            "uri": uri,
            "resolved_uri": uri,
            "digest": digest,
            "refs": refs,
            "trust": trust,
            "cached": False,
        }

    @app.post("/v1/policy/evaluate")
    async def evaluate_policy(payload: dict[str, Any]):
        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
        source_uri = str(context.get("source_uri") or "")
        trust_score = float(context.get("trust_score") or 0.0)
        strict_failures = context.get("strict_failures")
        failures = strict_failures if isinstance(strict_failures, list) else []
        allowed_sources = policy.get("allowed_sources")
        min_trust = float(policy.get("min_trust_score") or 0.0)
        mode = str(policy.get("mode") or "strict").lower()

        deny_reason = ""
        if isinstance(allowed_sources, list) and source_uri:
            if not any(_source_matches(str(pattern), source_uri) for pattern in allowed_sources):
                deny_reason = "source_not_allowlisted"
        if not deny_reason and trust_score < min_trust:
            deny_reason = "trust_score_below_threshold"
        if not deny_reason and mode == "strict" and failures:
            deny_reason = "strict_verification_failed"

        if deny_reason:
            db.record_policy_decision(decision="deny", reason=deny_reason, payload=payload)
            return {"allow": False, "decision": "deny", "reason": deny_reason}

        db.record_policy_decision(decision="allow", reason="ok", payload=payload)
        if mode == "warn" and failures:
            return {"allow": True, "decision": "warn", "reason": "strict_failures_ignored", "warnings": failures}
        return {"allow": True, "decision": "allow", "reason": "ok"}

    @app.get("/v1/capabilities")
    def capabilities():
        return {
            "verify": {
                "signature": True,
                "sbom": True,
                "provenance": True,
                "referrers_api": True,
                "referrers_tag_fallback": True,
            },
            "retrieval": {
                "dense_faiss": True,
                "hybrid_bm25_rrf": False,
                "cross_encoder_reranker": False,
            },
            "policy": {
                "modes": ["strict", "warn"],
            },
        }

    @app.post("/v1/packages/{name}/{version}")
    async def publish(
            name: str,
            version: str,
            request: Request,
            file: UploadFile = File(...),
            overwrite: bool = False,
    ):

        # check if already exists (avoid overwrite)
        if db.exists(name, version):
            if not overwrite:
                raise HTTPException(status_code=409, detail="already exists")
            # overwrite requested → delete previous mapping
            db.delete_version(name, version)

        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="empty upload")

        sha256 = hashlib.sha256(data).hexdigest()
        key = object_key_for_sha256(sha256)

        # upload to S3 (dedup: if already there, ok)
        if storage.head(key) is None:
            try:
                storage.put_bytes(key, data, content_type="application/gzip")
            except ClientError as e:
                log.error(f"S3 upload failed: {e}")
                raise HTTPException(status_code=500, detail="S3 upload failed") from e

        # insert db mapping
        db.insert_version(
            name=name,
            version=version,
            sha256=sha256,
            size_bytes=len(data),
            object_key=key,
            checksum=None,
            manifest_json=None,
        )

        db.log("publish", package=name, version=version, sha256=sha256, remote=request.client.host if request.client else None)

        return JSONResponse(
            status_code=201,
            content={"ok": True, "name": name, "version": version, "sha256": sha256, "object_key": key, "size_bytes": len(data)},
        )

    @app.get("/v1/packages/{name}/{version}/download")
    def download(name: str, version: str, request: Request):
        row = db.get_version(name, version)
        if not row or row.yanked:
            raise HTTPException(status_code=404, detail="not found")

        body = storage.get_streaming_body(row.object_key)

        db.log("download", package=name, version=version, sha256=row.sha256, remote=request.client.host if request.client else None)

        filename = f"{name}-{version}.tar.gz"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}

        return StreamingResponse(body, media_type="application/gzip", headers=headers)

    @app.post("/v1/packages/{name}/{version}/yank")
    def yank(name: str, version: str, request: Request, yanked: bool = True):
        ok = db.yank(name, version, yanked=yanked)
        if not ok:
            raise HTTPException(status_code=404, detail="not found")
        db.log("yank" if yanked else "unyank", package=name, version=version, remote=request.client.host if request.client else None)
        return {"ok": True, "name": name, "version": version, "yanked": yanked}

    return app


# Uvicorn entrypoint: `uvicorn rag.registry.api:app --port 8786`
settings = RegistrySettings.from_env()
app = make_app(settings)


def _digest_for_uri(uri: str) -> str:
    return f"sha256:{hashlib.sha256(uri.encode('utf-8')).hexdigest()}"


def _source_matches(pattern: str, value: str) -> bool:
    if pattern.endswith("*"):
        return value.startswith(pattern[:-1])
    return pattern == value

