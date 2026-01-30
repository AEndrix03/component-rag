from __future__ import annotations

import os
import re
import sys
import json
import tarfile
import tempfile
import signal
import subprocess
from pathlib import Path
from typing import Dict, Optional

import typer
import uvicorn

from .settings import RegistrySettings, load_env_file
from .client import RegistryClient
from .api import make_app  # run uvicorn with app object (avoid import-path issues)

app = typer.Typer(help="CPM Package Registry")

PID_FILE = Path("registry") / ".registry.pid"
LOG_FILE = Path("registry") / ".registry.log"


# -------------------------
# Helpers
# -------------------------
def _default_base_url() -> str:
    return os.getenv("REGISTRY_URL", "http://127.0.0.1:8787").rstrip("/")


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def parse_name_version(spec: str) -> tuple[str, str]:
    if "@" not in spec:
        raise typer.BadParameter("expected format name@version")
    name, version = spec.split("@", 1)
    name = name.strip()
    version = version.strip()
    if not name or not version:
        raise typer.BadParameter("expected format name@version")
    return name, version


def _parse_cpm_yml(path: Path) -> Dict[str, str]:
    """
    Parse the minimal YAML you generate in build (key: value, no nesting).
    Values may be quoted; lists are typically comma-separated strings.
    """
    if not path.exists():
        raise FileNotFoundError(str(path))

    out: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip()

        # strip optional quotes
        if len(v) >= 2 and ((v[0] == '"' and v[-1] == '"') or (v[0] == "'" and v[-1] == "'")):
            v = v[1:-1]

        out[k] = v
    return out


def _safe_filename(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", s).strip("-") or "pkg"


def _make_tar_gz_from_dir(src_dir: Path, out_path: Path) -> None:
    """
    Create tar.gz with the directory as the top-level folder.
    """
    if out_path.exists():
        out_path.unlink()

    with tarfile.open(out_path, "w:gz") as tf:
        tf.add(src_dir, arcname=src_dir.name)


# -------------------------
# SERVER
# -------------------------
@app.command("start")
def start(
    host: str = typer.Option(None, "--host"),
    port: int = typer.Option(None, "--port"),
    reload: bool = typer.Option(False, "--reload", help="Dev reload (disabled in this CLI mode)"),
    detach: bool = typer.Option(False, "--detach", help="Run registry in background"),
    env_file: str = typer.Option(None, "--env-file", help="Path to .env (default: registry/.env)"),
):
    """
    Start registry server.

    We start uvicorn with the FastAPI app object (not an import string),
    so it works regardless of repo layout / current working directory.

    NOTE: --reload is disabled here to avoid Windows silent failures & import path issues.
    """
    try:
        used_env = load_env_file(env_file)
        settings = RegistrySettings.from_env(env_file=env_file)

        host = host or settings.host
        port = port or settings.port

        if reload:
            typer.echo("Note: --reload disabled in this CLI mode (use `python -m uvicorn ... --reload` if needed).")
            reload = False

        if detach:
            if PID_FILE.exists():
                try:
                    pid = int(PID_FILE.read_text().strip())
                    if _is_process_alive(pid):
                        typer.echo(f"Registry already running (pid={pid})")
                        raise typer.Exit(1)
                except Exception:
                    pass
                PID_FILE.unlink(missing_ok=True)

            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            log = open(LOG_FILE, "ab", buffering=0)

            cmd = [sys.executable, "-m", "registry.cli", "start", "--host", host, "--port", str(port)]
            if env_file:
                cmd.extend(["--env-file", env_file])

            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

            proc = subprocess.Popen(
                cmd,
                stdout=log,
                stderr=log,
                stdin=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            PID_FILE.write_text(str(proc.pid))
            typer.echo(f"Registry started in background (pid={proc.pid})")
            typer.echo(f"Logs: {LOG_FILE}")
            typer.echo(f"Env file: {used_env}")
            return

        api_app = make_app(settings)

        typer.echo(f"Starting registry on http://{host}:{port}  (env: {used_env})")
        uvicorn.run(api_app, host=host, port=port, log_level="info")

    except Exception as e:
        typer.echo(f"ERROR starting registry: {type(e).__name__}: {e}")
        raise


@app.command("stop")
def stop():
    if not PID_FILE.exists():
        typer.echo("Registry not running (no pid file)")
        raise typer.Exit(1)

    pid_txt = PID_FILE.read_text().strip()
    try:
        pid = int(pid_txt)
    except ValueError:
        PID_FILE.unlink(missing_ok=True)
        typer.echo("Registry pid file corrupted; removed.")
        raise typer.Exit(1)

    if not _is_process_alive(pid):
        PID_FILE.unlink(missing_ok=True)
        typer.echo("Registry was not running (stale pid file removed).")
        return

    try:
        if os.name == "nt":
            os.kill(pid, signal.CTRL_BREAK_EVENT)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception as e:
        typer.echo(f"Failed to stop registry (pid={pid}): {e}")
        raise typer.Exit(1)

    PID_FILE.unlink(missing_ok=True)
    typer.echo(f"Registry stopped (pid={pid})")


@app.command("status")
def status():
    if not PID_FILE.exists():
        typer.echo("Registry: stopped")
        return

    try:
        pid = int(PID_FILE.read_text().strip())
    except ValueError:
        typer.echo("Registry: stale pid file (corrupted) — removing")
        PID_FILE.unlink(missing_ok=True)
        return

    if _is_process_alive(pid):
        typer.echo(f"Registry: running (pid={pid})")
    else:
        typer.echo("Registry: stale pid file — removing")
        PID_FILE.unlink(missing_ok=True)


# -------------------------
# CLIENT COMMANDS
# -------------------------
@app.command("exists")
def exists(
    spec: str = typer.Argument(..., help="name@version"),
    registry_url: str = typer.Option(None, "--registry"),
    env_file: str = typer.Option(None, "--env-file"),
):
    load_env_file(env_file)
    name, version = parse_name_version(spec)
    client = RegistryClient(registry_url or _default_base_url())
    ok = client.exists(name, version)
    raise typer.Exit(code=0 if ok else 1)


@app.command("publish")
def publish(
    from_dir: str = typer.Option(".", "--from", help="Build directory containing cpm.yml + artifacts"),
    registry_url: str = typer.Option(None, "--registry"),
    env_file: str = typer.Option(None, "--env-file", help="Path to .env (default: registry/.env)"),
    keep_tar: bool = typer.Option(False, "--keep-tar", help="Keep generated tar.gz instead of deleting it"),
    tar_out: Optional[str] = typer.Option(None, "--tar-out", help="Optional explicit tar.gz output path"),
):
    """
    Publish from a build directory:
    - reads cpm.yml (name, version)
    - creates a tar.gz of the whole build directory
    - publishes it to the registry
    """
    load_env_file(env_file)
    client = RegistryClient(registry_url or _default_base_url())

    src_dir = Path(from_dir).resolve()
    if not src_dir.exists() or not src_dir.is_dir():
        raise typer.BadParameter(f"--from must be an existing directory: {src_dir}")

    cpm_path = src_dir / "cpm.yml"
    meta = _parse_cpm_yml(cpm_path)

    name = meta.get("name")
    version = meta.get("version")
    if not name or not version:
        raise typer.BadParameter("cpm.yml missing required fields: name, version")

    safe_name = _safe_filename(name)
    safe_ver = _safe_filename(version)

    # Choose tar path
    if tar_out:
        tar_path = Path(tar_out).resolve()
        tar_path.parent.mkdir(parents=True, exist_ok=True)
        temp_created = False
    else:
        fd, tmp = tempfile.mkstemp(prefix=f"cpm-{safe_name}-{safe_ver}-", suffix=".tar.gz")
        os.close(fd)
        tar_path = Path(tmp)
        temp_created = True

    # Create tar.gz
    typer.echo(f"[pack] dir={src_dir}")
    typer.echo(f"[pack] cpm.yml={cpm_path}")
    typer.echo(f"[pack] tar={tar_path}")
    _make_tar_gz_from_dir(src_dir, tar_path)

    # Publish
    try:
        res = client.publish(name, version, str(tar_path))
    finally:
        if not keep_tar and temp_created:
            try:
                tar_path.unlink(missing_ok=True)
            except Exception:
                pass

    typer.echo(f"published {name}@{version} sha256={res['sha256']} size={res['size_bytes']}")
    if keep_tar:
        typer.echo(f"kept tar: {tar_path}")
        typer.echo("meta:", json.dumps(meta, ensure_ascii=False))


@app.command("download")
def download(
    spec: str = typer.Argument(..., help="name@version"),
    out: str = typer.Option(".", "--out", help="Output directory or file path"),
    registry_url: str = typer.Option(None, "--registry"),
    env_file: str = typer.Option(None, "--env-file"),
):
    load_env_file(env_file)
    name, version = parse_name_version(spec)
    client = RegistryClient(registry_url or _default_base_url())

    if os.path.isdir(out) or out.endswith(os.sep) or out in (".", "./"):
        os.makedirs(out, exist_ok=True)
        out_path = os.path.join(out, f"{name}-{version}.tar.gz")
    else:
        out_path = out

    client.download(name, version, out_path)
    typer.echo(out_path)


@app.command("list")
def list_cmd(
    name: str = typer.Argument(..., help="Package name"),
    include_yanked: bool = typer.Option(False, "--include-yanked"),
    registry_url: str = typer.Option(None, "--registry"),
    env_file: str = typer.Option(None, "--env-file"),
):
    load_env_file(env_file)
    client = RegistryClient(registry_url or _default_base_url())
    data = client.list(name, include_yanked=include_yanked)
    versions = data.get("versions", [])
    if not versions:
        typer.echo("(no versions)")
        return
    for v in versions:
        typer.echo(
            f"{name}@{v['version']} sha256={v['sha256']} size={v['size_bytes']} "
            f"published_at={v['published_at']} yanked={v['yanked']}"
        )


if __name__ == "__main__":
    app()
