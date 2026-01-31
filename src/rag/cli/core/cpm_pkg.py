# rag/cli/commands/cpm_pkg.py
from __future__ import annotations

import os
import re
import json
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Iterable

# Reuse existing RegistryClient (from registry package)
from .client import RegistryClient  # :contentReference[oaicite:3]{index=3}

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


# ----------------------------
# Semver helpers
# ----------------------------
def parse_semver(v: str) -> Tuple[int, int, int]:
    m = _SEMVER_RE.match((v or "").strip())
    if not m:
        raise ValueError(f"invalid semver: {v!r} (expected x.y.z)")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def semver_to_path(v: str) -> Tuple[str, str, str]:
    x, y, z = parse_semver(v)
    return str(x), str(y), str(z)


def max_semver(versions: Iterable[str]) -> Optional[str]:
    best: Optional[Tuple[int, int, int]] = None
    best_s: Optional[str] = None
    for s in versions:
        try:
            t = parse_semver(s)
        except Exception:
            continue
        if best is None or t > best:
            best = t
            best_s = s
    return best_s


# ----------------------------
# Minimal YAML (same style you already use)
# ----------------------------
def read_simple_yml(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return out
    except UnicodeDecodeError:
        lines = path.read_text(encoding="latin-1").splitlines()

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            out[k] = v
    return out


def write_simple_yml(path: Path, kv: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # stable order (nice diffs)
    keys = sorted(kv.keys())
    lines = []
    for k in keys:
        v = kv[k]
        # quote if needed
        if any(ch in v for ch in [":", "#", "\n", "\r", "\t"]):
            v = v.replace('"', '\\"')
            v = f"\"{v}\""
        lines.append(f"{k}: {v}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ----------------------------
# Layout helpers
# ----------------------------
REQUIRED_ARTIFACTS = [
    "manifest.json",
    "vectors.f16.bin",
    "docs.jsonl",
    "cpm.yml",
    os.path.join("faiss", "index.faiss"),
]


def verify_built_packet_dir(src_dir: Path) -> None:
    missing = []
    for rel in REQUIRED_ARTIFACTS:
        if not (src_dir / rel).exists():
            missing.append(rel)
    if missing:
        raise FileNotFoundError(f"missing required artifacts in {src_dir}: {', '.join(missing)}")


def read_built_meta(src_dir: Path) -> Tuple[str, str]:
    yml = read_simple_yml(src_dir / "cpm.yml")
    name = (yml.get("name") or "").strip()
    version = (yml.get("version") or "").strip()
    if not name or not version:
        raise ValueError("cpm.yml missing required fields: name, version")
    # validate semver here (your system uses x.y.z paths)
    parse_semver(version)
    return name, version


def packet_root(cpm_dir: Path, name: str) -> Path:
    return cpm_dir / name


def packet_pin_path(cpm_dir: Path, name: str) -> Path:
    # packet-level pin file: .cpm/<name>/cpm.yml
    return packet_root(cpm_dir, name) / "cpm.yml"


def version_dir(cpm_dir: Path, name: str, version: str) -> Path:
    x, y, z = semver_to_path(version)
    return packet_root(cpm_dir, name) / x / y / z


def installed_versions(cpm_dir: Path, name: str) -> List[str]:
    root = packet_root(cpm_dir, name)
    if not root.exists():
        return []
    out: List[str] = []
    for major in root.iterdir():
        if not major.is_dir() or not major.name.isdigit():
            continue
        for minor in major.iterdir():
            if not minor.is_dir() or not minor.name.isdigit():
                continue
            for patch in minor.iterdir():
                if not patch.is_dir() or not patch.name.isdigit():
                    continue
                # consider installed if it has manifest or faiss
                if (patch / "manifest.json").exists() or (patch / "faiss" / "index.faiss").exists():
                    out.append(f"{int(major.name)}.{int(minor.name)}.{int(patch.name)}")
    return sorted(out, key=lambda s: parse_semver(s))


def get_pinned_version(cpm_dir: Path, name: str) -> Optional[str]:
    yml = read_simple_yml(packet_pin_path(cpm_dir, name))
    v = (yml.get("version") or "").strip()
    if not v:
        return None
    try:
        parse_semver(v)
    except Exception:
        return None
    return v


def set_pinned_version(cpm_dir: Path, name: str, version: str) -> None:
    parse_semver(version)
    pin = packet_pin_path(cpm_dir, name)
    kv = read_simple_yml(pin)
    kv["version"] = version
    # optional convenience fields
    if "name" not in kv:
        kv["name"] = name
    write_simple_yml(pin, kv)


def resolve_current_packet_dir(cpm_dir: Path, packet: str) -> Optional[Path]:
    """
    Resolve packet argument:
      - direct path (if points to version dir with artifacts)
      - name (use .cpm/<name>/cpm.yml 'version' if present)
      - fallback: max installed version (legacy behavior)
    """
    p = Path(packet)
    if p.exists() and p.is_dir():
        return p

    name = packet
    pinned = get_pinned_version(cpm_dir, name)
    if pinned:
        vd = version_dir(cpm_dir, name, pinned)
        if vd.exists():
            return vd

    # fallback to latest installed
    vs = installed_versions(cpm_dir, name)
    if not vs:
        return None
    best = max_semver(vs)
    if not best:
        return None
    vd = version_dir(cpm_dir, name, best)
    return vd if vd.exists() else None


# ----------------------------
# Tar helpers (publish/install)
# ----------------------------
def _safe_tar_extract(tf: tarfile.TarFile, dest: Path) -> None:
    """
    Prevent path traversal. Only allow members under dest.
    """
    dest = dest.resolve()
    for m in tf.getmembers():
        target = (dest / m.name).resolve()
        if not str(target).startswith(str(dest) + os.sep) and target != dest:
            raise RuntimeError(f"unsafe tar member path: {m.name}")
    tf.extractall(dest)


def make_versioned_tar_from_build_dir(src_dir: Path, name: str, version: str, out_path: Path) -> None:
    """
    Create tar.gz with layout:
      <name>/<x>/<y>/<z>/... (contents copied from src_dir)
    """
    x, y, z = semver_to_path(version)

    if out_path.exists():
        out_path.unlink()

    with tempfile.TemporaryDirectory(prefix="cpm-publish-") as tmpd:
        tmp = Path(tmpd)
        root = tmp / name / x / y / z
        root.mkdir(parents=True, exist_ok=True)

        # Copy ALL files/dirs from src_dir into version dir
        # (exclude any prebuilt archives next to it to avoid recursion)
        for p in src_dir.iterdir():
            if p.is_file() and p.name.endswith((".tar.gz", ".zip")):
                continue
            dst = root / p.name
            if p.is_dir():
                shutil.copytree(p, dst)
            else:
                shutil.copy2(p, dst)

        # Create tar with top-level <name>
        with tarfile.open(out_path, "w:gz") as tf:
            tf.add(tmp / name, arcname=name)


def download_and_extract(client: RegistryClient, name: str, version: str, cpm_dir: Path) -> Path:
    """
    Download tar and extract into cpm_dir. Returns extracted version directory path.
    """
    cpm_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cpm-install-") as tmpd:
        tmp = Path(tmpd)
        tar_path = tmp / f"{name}-{version}.tar.gz"
        client.download(name, version, str(tar_path))
        with tarfile.open(tar_path, "r:gz") as tf:
            _safe_tar_extract(tf, cpm_dir)

    vd = version_dir(cpm_dir, name, version)
    return vd


def registry_latest_version(client: RegistryClient, name: str) -> str:
    data = client.list(name, include_yanked=False)
    versions = data.get("versions") or []
    if not versions:
        raise RuntimeError(f"no versions found on registry for {name}")
    # server returns published_at desc (db ORDER BY published_at DESC) :contentReference[oaicite:4]{index=4}
    return versions[0]["version"]
