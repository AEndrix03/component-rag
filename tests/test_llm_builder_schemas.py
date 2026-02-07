"""Unit tests for llm builder schemas/adapters/classifier."""

from __future__ import annotations

from pathlib import Path
import sys

PLUGIN_SRC = Path("cpm_plugins/llm_builder").resolve()
if str(PLUGIN_SRC) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SRC))

from cpm_llm_builder_plugin.classifiers import classify_file
from cpm_llm_builder_plugin.schemas import normalize_chunk_list


def test_normalize_chunk_list_legacy_and_openai_like() -> None:
    legacy = {"chunks": ["a", {"id": "x", "text": "b"}]}
    chunks_legacy = normalize_chunk_list(legacy)
    assert len(chunks_legacy) == 2
    assert chunks_legacy[0].text == "a"
    assert chunks_legacy[1].id == "x"

    openai = {
        "output": [
            {
                "type": "output_json",
                "json": {"chunks": [{"id": "y", "text": "chunk"}]},
            }
        ]
    }
    chunks_openai = normalize_chunk_list(openai)
    assert len(chunks_openai) == 1
    assert chunks_openai[0].id == "y"


def test_classify_file_java_and_fallback() -> None:
    java_cls = classify_file(Path("Sample.java"), "public class Sample {}")
    assert java_cls.pipeline == "java"
    assert java_cls.language == "java"

    fallback = classify_file(Path("unknown.foo"), "plain text")
    assert fallback.pipeline == "text"


def test_chunk_from_dict_tolerates_non_mapping_fields() -> None:
    payload = {
        "id": "x",
        "text": "body",
        "anchors": ["path=/tmp/a.py", "start=1"],
        "relations": "not-json",
        "metadata": '{"k":"v"}',
    }
    chunks = normalize_chunk_list({"chunks": [payload]})
    assert len(chunks) == 1
    assert chunks[0].id == "x"
    assert "items" in chunks[0].anchors or "path" in chunks[0].anchors
    assert "raw" in chunks[0].relations or chunks[0].relations == {}
    assert chunks[0].metadata.get("k") == "v"
