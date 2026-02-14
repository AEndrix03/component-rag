from __future__ import annotations

import json
from pathlib import Path

from cpm_core.oci.install_state import read_install_lock


def test_read_install_lock_normalizes_legacy_payload(tmp_path: Path) -> None:
    workspace_root = tmp_path / ".cpm"
    lock_path = workspace_root / "state" / "install" / "demo.lock.json"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(
            {
                "name": "demo",
                "version": "1.0.0",
                "packet_ref": "registry.local/team/demo:1.0.0",
                "packet_digest": "sha256:" + ("a" * 64),
                "selected_model": "text-embedding",
            }
        ),
        encoding="utf-8",
    )

    payload = read_install_lock(workspace_root, "demo")
    assert payload is not None
    assert isinstance(payload.get("sources"), list)
    assert payload["sources"][0]["uri"] == "oci://registry.local/team/demo:1.0.0"
    assert payload["sources"][0]["digest"].startswith("sha256:")
    assert float(payload["trust_score"]) == 0.0
