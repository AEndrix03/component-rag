"""Integration tests for the CPM LLM builder plugin."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import numpy as np
import pytest

from cpm_core.events import EventBus
from cpm_core.paths import UserDirs
from cpm_core.plugin import PluginManager
from cpm_core.workspace import Workspace


def _create_workspace(tmp_path: Path) -> Workspace:
    root = tmp_path / ".cpm"
    root.mkdir()
    config = root / "config.toml"
    config.write_text("", encoding="utf-8")
    return Workspace(root=root, config_path=config)


def _build_manager(tmp_path: Path, workspace: Workspace) -> PluginManager:
    user_data = tmp_path / "user_data"
    return PluginManager(
        workspace=workspace,
        events=EventBus(),
        user_dirs=UserDirs(data_dir_override=user_data),
    )


def _install_plugin(workspace: Workspace) -> Path:
    destination = workspace.root / "plugins" / "llm_builder"
    shutil.copytree(Path("cpm_plugins") / "llm_builder", destination)
    return destination


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http error: {self.status_code}")

    def json(self) -> dict:
        return self._payload


class _FakeEmbedder:
    def health(self) -> bool:
        return True

    def embed_texts(
        self,
        texts: list[str],
        *,
        model_name: str,
        max_seq_length: int,
        normalize: bool,
        dtype: str,
        show_progress: bool,
    ) -> np.ndarray:
        matrix = np.zeros((len(texts), 3), dtype=np.float32)
        for idx, text in enumerate(texts):
            matrix[idx, 0] = float(len(text))
            matrix[idx, 1] = float(len(text.split()))
            matrix[idx, 2] = 1.0
        return matrix


def test_llm_builder_plugin_registers_builder(tmp_path: Path) -> None:
    workspace = _create_workspace(tmp_path)
    (workspace.root / "plugins").mkdir()
    _install_plugin(workspace)

    manager = _build_manager(tmp_path, workspace)
    manager.register("core")
    manager.load_plugins()

    entry = manager.registry.resolve("llm:cpm-llm-builder")
    assert entry.group == "llm"
    assert entry.origin == "llm_builder"


def test_llm_builder_incremental_skips_enrichment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _create_workspace(tmp_path)
    (workspace.root / "plugins").mkdir()
    _install_plugin(workspace)

    manager = _build_manager(tmp_path, workspace)
    manager.register("core")
    manager.load_plugins()
    entry = manager.registry.resolve("llm:cpm-llm-builder")

    import importlib

    feature_module = importlib.import_module("cpm_llm_builder_plugin.features")
    llm_module = importlib.import_module("cpm_llm_builder_plugin.llm_client")

    calls: list[str] = []

    def fake_post(url: str, *, json: dict, timeout: float) -> _FakeResponse:
        del url, timeout
        if "input" in json:
            source_path = json["input"][0]["content"][1]["json"]["source"]["path"]
            segments = json["input"][0]["content"][1]["json"]["segments"]
            calls.extend(str(item["id"]) for item in segments)
            chunks = [
                {
                    "id": segment["id"],
                    "title": "Title",
                    "summary": "Summary",
                    "tags": ["test"],
                    "anchors": {
                        "path": source_path,
                        "start_line": segment["start"],
                        "end_line": segment["end"],
                    },
                    "text": segment["text"],
                    "relations": {"calls": [], "called_by": []},
                }
                for segment in segments
            ]
            return _FakeResponse({"output": [{"type": "output_json", "json": {"chunks": chunks}}]})

        import json as _json

        user_payload = _json.loads(json["messages"][1]["content"])
        source_path = user_payload["source"]["path"]
        segments = user_payload["segments"]
        calls.extend(str(item["id"]) for item in segments)
        chunks = [
            {
                "id": segment["id"],
                "title": "Title",
                "summary": "Summary",
                "tags": ["test"],
                "anchors": {
                    "path": source_path,
                    "start_line": segment["start"],
                    "end_line": segment["end"],
                },
                "text": segment["text"],
                "relations": {"calls": [], "called_by": []},
            }
            for segment in segments
        ]
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": _json.dumps({"chunks": chunks}, ensure_ascii=False)
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(llm_module.requests, "post", fake_post)
    monkeypatch.setattr(feature_module, "EmbeddingClient", lambda **kwargs: _FakeEmbedder())

    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "Sample.java").write_text(
        "public class Sample {\npublic int add(int a, int b) { return a + b; }\n}\n",
        encoding="utf-8",
    )
    destination = tmp_path / "packet"

    command = entry.target()
    args = argparse.Namespace(
        source=str(source_dir),
        destination=str(destination),
        packet_version="1.2.3",
        config=None,
        llm_endpoint=None,
        request_timeout=None,
        llm_model=None,
        prompt_version=None,
        max_retries=None,
        max_chunk_tokens=None,
        min_chunk_tokens=None,
        max_segments_per_request=None,
        model_name="test-model",
        max_seq_length=256,
        embed_url="http://embed.local",
        embeddings_mode="http",
        timeout=5.0,
        archive=False,
        archive_format="tar.gz",
    )

    assert command.run(args) == 0
    first_call_count = len(calls)
    assert first_call_count > 0

    assert command.run(args) == 0
    assert len(calls) == first_call_count
