from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from typing import Any

import pytest

from cpm_builtin.embeddings.openai import (
    OpenAIEmbeddingsHttpClient,
    normalize_embeddings,
    parse_openai_response,
    serialize_openai_request,
)
from cpm_builtin.embeddings.types import EmbedRequestIR


class _ThreadedServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class _OpenAIHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/v1/embeddings":
            self.send_error(404)
            return

        server = self.server
        mode = getattr(server, "mode", "ok")
        call_count = getattr(server, "call_count", 0) + 1
        setattr(server, "call_count", call_count)

        length = int(self.headers.get("Content-Length", "0"))
        payload_raw = self.rfile.read(length)
        payload = json.loads(payload_raw.decode("utf-8"))
        setattr(server, "last_payload", payload)
        setattr(
            server,
            "last_headers",
            {str(k): str(v) for k, v in self.headers.items()},
        )

        if mode == "400":
            self._respond(400, {"error": {"message": "bad request"}})
            return

        if mode == "503_once" and call_count == 1:
            self._respond(503, {"error": {"message": "service unavailable"}})
            return

        if mode == "timeout":
            time.sleep(0.2)
            self._respond(200, {"object": "list", "data": [], "model": "mock-model"})
            return

        texts = payload.get("input") or []
        data = []
        for index, _ in enumerate(texts):
            data.append(
                {
                    "object": "embedding",
                    "index": index,
                    "embedding": [float(index + 1), 0.0, 0.0],
                }
            )
        data.reverse()
        self._respond(
            200,
            {
                "object": "list",
                "data": data,
                "model": "mock-model",
                "usage": {"prompt_tokens": len(texts), "total_tokens": len(texts)},
            },
        )

    def _respond(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        return


def _start_server(mode: str = "ok") -> tuple[_ThreadedServer, str]:
    server = _ThreadedServer(("127.0.0.1", 0), _OpenAIHandler)
    server.mode = mode
    server.call_count = 0
    server.last_headers = {}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}/v1/embeddings"


def _stop_server(server: _ThreadedServer) -> None:
    server.shutdown()
    server.server_close()


def test_serialize_openai_request() -> None:
    request = EmbedRequestIR(
        texts=["alpha", "beta"],
        hints={"model": "text-embedding-3-small", "dim": 3},
        extra={"user": "ci-suite"},
    )
    payload = serialize_openai_request(request)

    assert payload == {
        "input": ["alpha", "beta"],
        "model": "text-embedding-3-small",
        "user": "ci-suite",
    }


def test_parse_openai_response_orders_by_index() -> None:
    body = {
        "data": [
            {"index": 1, "embedding": [0.0, 1.0]},
            {"index": 0, "embedding": [1.0, 0.0]},
        ],
    }
    parsed = parse_openai_response(body)
    assert parsed.vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert parsed.model is None
    assert parsed.usage is None


def test_parse_openai_response_missing_fields() -> None:
    with pytest.raises(ValueError, match="missing 'embedding'"):
        parse_openai_response({"data": [{"index": 0}]})

    with pytest.raises(ValueError, match="missing 'index'"):
        parse_openai_response({"data": [{"embedding": [1.0]}]})


def test_parse_openai_response_embedding_type() -> None:
    with pytest.raises(TypeError, match="embedding must be a list"):
        parse_openai_response({"data": [{"index": 0, "embedding": "bad"}]})


def test_normalize_embeddings_client_side() -> None:
    normalized = normalize_embeddings([[3.0, 4.0], [0.0, 0.0]])
    assert normalized[0] == pytest.approx([0.6, 0.8], rel=1e-6)
    assert normalized[1] == [0.0, 0.0]


def test_openai_client_integration_success() -> None:
    server, endpoint = _start_server(mode="ok")
    try:
        client = OpenAIEmbeddingsHttpClient(endpoint, timeout=1.0, max_retries=2)
        request = EmbedRequestIR(
            texts=["a", "b"],
            model="text-embedding-3-small",
            hints={"dim": 3, "normalize": True, "task": "retrieval.query"},
        )
        response = client.embed(request)

        assert response.model == "mock-model"
        assert response.vectors == [[1.0, 0.0, 0.0], [2.0, 0.0, 0.0]]
        assert server.last_payload == {"input": ["a", "b"], "model": "text-embedding-3-small"}
        assert server.last_headers["X-Embedding-Dim"] == "3"
        assert server.last_headers["X-Embedding-Normalize"] == "true"
        assert server.last_headers["X-Embedding-Task"] == "retrieval.query"
        assert server.last_headers["X-Model-Hint"] == "text-embedding-3-small"
    finally:
        _stop_server(server)


def test_openai_client_integration_success_with_normalization() -> None:
    server, endpoint = _start_server(mode="ok")
    try:
        client = OpenAIEmbeddingsHttpClient(endpoint, timeout=1.0, max_retries=2)
        request = EmbedRequestIR(texts=["a", "b"], model="text-embedding-3-small")
        response = client.embed(request, normalize=True)
        assert response.vectors[0] == pytest.approx([1.0, 0.0, 0.0], rel=1e-6)
        assert response.vectors[1] == pytest.approx([1.0, 0.0, 0.0], rel=1e-6)
    finally:
        _stop_server(server)


def test_openai_client_integration_400() -> None:
    server, endpoint = _start_server(mode="400")
    try:
        client = OpenAIEmbeddingsHttpClient(endpoint, timeout=1.0, max_retries=2)
        request = EmbedRequestIR(texts=["a"], model="text-embedding-3-small")
        with pytest.raises(ValueError, match="bad request"):
            client.embed(request)
    finally:
        _stop_server(server)


def test_openai_client_integration_503_retry() -> None:
    server, endpoint = _start_server(mode="503_once")
    try:
        client = OpenAIEmbeddingsHttpClient(
            endpoint, timeout=1.0, max_retries=2, backoff_seconds=0.01
        )
        request = EmbedRequestIR(texts=["a"], model="text-embedding-3-small")
        response = client.embed(request)
        assert response.vectors == [[1.0, 0.0, 0.0]]
        assert server.call_count == 2
    finally:
        _stop_server(server)


def test_openai_client_integration_timeout() -> None:
    server, endpoint = _start_server(mode="timeout")
    try:
        client = OpenAIEmbeddingsHttpClient(
            endpoint, timeout=0.05, max_retries=2, backoff_seconds=0.01
        )
        request = EmbedRequestIR(texts=["a"], model="text-embedding-3-small")
        with pytest.raises(RuntimeError, match="failed to obtain embeddings"):
            client.embed(request)
        assert server.call_count >= 2
    finally:
        _stop_server(server)


def test_openai_client_embed_texts_accepts_string_input() -> None:
    server, endpoint = _start_server(mode="ok")
    try:
        client = OpenAIEmbeddingsHttpClient(endpoint, timeout=1.0, max_retries=2)
        response = client.embed_texts("single", model="text-embedding-3-small")
        assert response.vectors == [[1.0, 0.0, 0.0]]
        assert server.last_payload == {
            "input": ["single"],
            "model": "text-embedding-3-small",
        }
    finally:
        _stop_server(server)
