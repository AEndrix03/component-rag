# Agent A — Contract & Standard Compliance

**Status**: PASS

## Summary

The HTTP embeddings implementation demonstrates **strong OpenAI API compatibility** with a well-designed separation of concerns. The implementation correctly uses only standard OpenAI request fields (`model`, `input`) in the request body, passes all hints via custom headers (X-Embedding-*, X-Model-Hint), and properly handles OpenAI-compliant responses including index-based ordering, missing optional fields, and appropriate error handling.

The codebase follows a layered architecture:
- **types.py**: Internal representation (IR) types for request/response contracts
- **openai.py**: OpenAI-specific HTTP client with serialization/parsing
- **client.py**: High-level facade supporting both "http" (OpenAI) and "legacy" modes
- **connector.py**: Legacy connector (not OpenAI-compliant, different contract)

## Findings

| Severity | Description | File:Line | Suggested Fix |
|----------|-------------|-----------|---------------|
| LOW | `extra` dict merged into request body could theoretically include non-standard required fields | openai.py:81 | Already mitigated by design - `extra` is explicitly for provider-specific extensions. Document that users should not abuse this field. |
| LOW | Timeout handling could distinguish network timeouts from server timeouts | openai.py:215-243 | Current retry logic is adequate - all timeouts trigger retry, which is appropriate for both cases. No action required. |
| INFO | Legacy connector (connector.py) uses non-OpenAI format | connector.py:89-93 | Intentional - this is the "legacy" mode. Not an issue for OpenAI compliance. |

## Request/Response Examples

### Request Body Structure (OpenAI-Compliant)

From `openai.py:76-82` - `serialize_openai_request()`:

```python
payload: dict[str, Any] = {"input": _coerce_inputs(request.texts)}
model = request.model or request.hints.get("model")
if model:
    payload["model"] = str(model)
payload.update(request.extra)
return payload
```

**Result**: Only `input` and `model` fields in body (OpenAI standard). The `extra` dict is merged but is explicitly for optional provider-specific extensions.

**Test Evidence** (test_openai_embeddings.py:107-119):
```python
request = EmbedRequestIR(
    texts=["alpha", "beta"],
    hints={"model": "text-embedding-3-small", "dim": 3},
    extra={"user": "ci-suite"},
)
payload = serialize_openai_request(request)

assert payload == {
    "input": ["alpha", "beta"],
    "model": "text-embedding-3-small",
    "user": "ci-suite",  # from extra
}
```

### Hint Headers (Custom Extension Headers)

From `openai.py:50-73` - `_build_hint_headers()`:

```python
headers: dict[str, str] = {}
if dim is not None:
    headers["X-Embedding-Dim"] = str(int(dim))
if normalize is not None:
    headers["X-Embedding-Normalize"] = "true" if normalize else "false"
if task is not None:
    headers["X-Embedding-Task"] = str(task)
if model_hint is not None:
    headers["X-Model-Hint"] = str(model_hint)
```

**Headers Used**:
- `X-Embedding-Dim`: Desired embedding dimension
- `X-Embedding-Normalize`: Whether to normalize vectors
- `X-Embedding-Task`: Task type (e.g., "retrieval.query")
- `X-Model-Hint`: Model identifier hint
- `X-CPM-Metadata`: Base64-encoded metadata (optional)

**Test Evidence** (test_openai_embeddings.py:154-173):
```python
request = EmbedRequestIR(
    texts=["a", "b"],
    model="text-embedding-3-small",
    hints={"dim": 3, "normalize": True, "task": "retrieval.query"},
)
response = client.embed(request)

assert server.last_headers["X-Embedding-Dim"] == "3"
assert server.last_headers["X-Embedding-Normalize"] == "true"
assert server.last_headers["X-Embedding-Task"] == "retrieval.query"
assert server.last_headers["X-Model-Hint"] == "text-embedding-3-small"
```

### Response Parsing

From `openai.py:85-129` - `parse_openai_response()`:

```python
data = body.get("data")
if not isinstance(data, list):
    raise TypeError("response.data must be a list")

indexed_vectors: list[tuple[int, list[float]]] = []
for item in data:
    if "index" not in item:
        raise ValueError("response.data entry missing 'index'")
    if "embedding" not in item:
        raise ValueError("response.data entry missing 'embedding'")
    indexed_vectors.append((item["index"], item["embedding"]))

indexed_vectors.sort(key=lambda item: item[0])  # Sort by index

usage = body.get("usage")  # Optional field
model = body.get("model")  # Optional field
```

**Key Features**:
1. Reads `data[*].embedding` and `data[*].index` (required fields)
2. Tolerates missing `usage` and `model` fields (optional per OpenAI spec)
3. Sorts results by index to ensure correct ordering
4. Validates index contiguity (0, 1, 2, ... n-1)

**Test Evidence** (test_openai_embeddings.py:122-132):
```python
body = {
    "data": [
        {"index": 1, "embedding": [0.0, 1.0]},
        {"index": 0, "embedding": [1.0, 0.0]},
    ],
}
parsed = parse_openai_response(body)
assert parsed.vectors == [[1.0, 0.0], [0.0, 1.0]]  # Correctly ordered by index
assert parsed.model is None  # Missing model is OK
assert parsed.usage is None  # Missing usage is OK
```

### Error Handling

From `openai.py:175-244` - `embed()` method:

```python
for attempt in range(1, self.max_retries + 1):
    try:
        response = requests.post(...)
        status = response.status_code

        # 4xx errors - client errors, no retry
        if 400 <= status < 500:
            snippet = _error_body_snippet(response)
            raise ValueError(f"bad request (status={status}) payload_snippet='{snippet}'")

        # 5xx errors - server errors, trigger retry
        if 500 <= status < 600:
            raise RuntimeError(f"upstream error status={status}")

        response.raise_for_status()
        parsed = parse_openai_response(response.json())
        return parsed

    except Timeout as exc:
        last_error = exc  # Retry on timeout
    except RequestException as exc:
        last_error = exc  # Retry on network error
    except RuntimeError as exc:
        last_error = exc  # Retry on 5xx
    except ValueError:
        raise  # No retry on 4xx (client error)
```

**Error Distinction**:
- **4xx**: Raised as `ValueError`, no retry (client error)
- **5xx**: Raised as `RuntimeError`, triggers retry (server error)
- **Timeout**: Triggers retry with exponential backoff
- **Network errors**: Triggers retry

**Test Evidence** (test_openai_embeddings.py:188-196):
```python
def test_openai_client_integration_400() -> None:
    server, endpoint = _start_server(mode="400")
    client = OpenAIEmbeddingsHttpClient(endpoint, timeout=1.0, max_retries=2)
    with pytest.raises(ValueError, match="bad request"):
        client.embed(request)  # 4xx raises ValueError, no retry
```

**Test Evidence** (test_openai_embeddings.py:199-210):
```python
def test_openai_client_integration_503_retry() -> None:
    server, endpoint = _start_server(mode="503_once")
    client = OpenAIEmbeddingsHttpClient(endpoint, timeout=1.0, max_retries=2)
    response = client.embed(request)
    assert server.call_count == 2  # 5xx triggered retry
```

## OpenAI Compliance Checklist

- [x] **Request body: only {model, input}** - Confirmed in openai.py:76-82. Only standard fields used.
- [x] **Hints via headers only** - Confirmed in openai.py:50-73. All hints use X-Embedding-* or X-Model-Hint headers.
- [x] **Response parsing: data[*].embedding** - Confirmed in openai.py:85-129. Correctly extracts embedding arrays.
- [x] **Response parsing: handles missing usage/model** - Confirmed in openai.py:115-121. Both fields treated as optional.
- [x] **Index-based ordering** - Confirmed in openai.py:109. Results sorted by index field.
- [x] **4xx/5xx error distinction** - Confirmed in openai.py:196-202. 4xx raises ValueError (no retry), 5xx raises RuntimeError (retry).
- [x] **Timeout handling** - Confirmed in openai.py:215-221. Timeouts trigger retry with backoff.

## Architecture Quality

### Strengths

1. **Clean separation of concerns**:
   - `types.py`: Provider-agnostic IR types
   - `openai.py`: OpenAI-specific serialization/parsing
   - `client.py`: High-level facade with mode selection

2. **Robust validation**:
   - Input validation in `_coerce_inputs()` (openai.py:18-27)
   - Response validation in `parse_openai_response()` (openai.py:85-129)
   - Request-response matching in `validate_against_request()` (types.py:201-221)

3. **Type safety**:
   - Strong type hints throughout
   - Dataclass-based IR types with `__post_init__` validation
   - Explicit type coercion for headers

4. **Error handling**:
   - Clear 4xx vs 5xx distinction
   - Exponential backoff with configurable max retries
   - Informative error messages with response snippets

5. **Test coverage**:
   - Mock server for integration tests
   - Tests for success, 4xx, 5xx, timeout, retry scenarios
   - Tests for edge cases (missing fields, index ordering)

### Design Patterns

1. **Internal Representation (IR) Pattern**: `EmbedRequestIR` and `EmbedResponseIR` provide a stable internal contract decoupled from external API formats. This allows supporting multiple providers (OpenAI, legacy) without changing core logic.

2. **Adapter Pattern**: `serialize_openai_request()` and `parse_openai_response()` act as adapters between IR and OpenAI formats.

3. **Retry Pattern**: Exponential backoff with configurable max retries and backoff multiplier.

4. **Template Method Pattern**: `embed()` method handles retry logic, delegates serialization/parsing to helper functions.

## Recommendations

### For Users

1. **Do not abuse `extra` field**: While the implementation allows arbitrary fields in `extra`, users should only use this for legitimate OpenAI API extensions (e.g., `user` field for tracking). Do not add non-standard required fields.

2. **Use `hints` for semantic parameters**: Dimension, normalization, task type should go in `hints`, not `extra`.

3. **Set appropriate timeouts**: Default timeout is 10s. Adjust based on model size and network conditions.

### For Maintainers

1. **Document header contract**: Consider adding a table or reference doc listing all X-Embedding-* and X-Model-Hint headers with their semantics.

2. **Consider OpenAPI spec**: The OpenAI compatibility could be validated against an OpenAPI spec (if available) to ensure full compliance.

3. **Monitor `extra` usage**: If users start abusing `extra` for non-standard required fields, consider adding validation or warnings.

4. **Connection pooling**: For high-throughput scenarios, consider adding connection pooling (e.g., requests.Session with HTTPAdapter).

## Conclusion

The implementation is **fully OpenAI-compliant** with excellent error handling, validation, and test coverage. The design is clean, well-documented, and extensible. No breaking issues found.

**Status**: **PASS**
