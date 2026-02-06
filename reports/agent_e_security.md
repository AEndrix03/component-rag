# Agent E — Security & Robustness

**Status**: PASS_WITH_WARNINGS

## Summary

The embeddings implementation demonstrates good security practices in several areas but has a few notable security and robustness gaps. Most critical: **no URL scheme validation allows SSRF attacks**, and **API keys/tokens are potentially logged**. Timeout handling is solid, input validation is comprehensive, and header handling is reasonable. The code is generally robust against common attack vectors but needs URL validation and logging improvements.

## Findings

| Severity | Description | File:Line | Suggested Fix |
|----------|-------------|-----------|---------------|
| HIGH | No URL scheme validation - SSRF risk | config.py:129, connector.py:34, openai.py:148 | Validate URL schemes (allow only http/https) |
| HIGH | API keys/tokens may leak in debug logs | openai.py:183-188 | Redact auth headers from logs |
| MEDIUM | Error messages expose full response body | openai.py:30-33, 197-199 | Limit snippet size, sanitize sensitive data |
| MEDIUM | Basic auth credentials stored/passed in clear | connector.py:44-46 | Document TLS requirement, consider warnings |
| LOW | No validation of custom headers | config.py:98, 106, connector.py:54 | Sanitize header values, block sensitive keys |
| LOW | Metadata header propagation without filtering | openai.py:70-72 | Document or filter metadata_b64 content |
| LOW | Cache stores full text in clear | cache.py:16, 32 | Consider encrypting cache or document risks |

## Security Checklist

- [x] Logging: no full payloads (vectors not logged)
- [ ] **Logging: API keys NOT redacted** - headers may contain auth tokens
- [x] Headers: sensitive metadata not leaked (reasonable isolation)
- [ ] **URL validation: NO scheme check** - file://, data://, ftp:// all accepted
- [x] Timeouts: always set (defaults to 10.0s)
- [x] Input sanitization: comprehensive validation

## Specific Issues Found

### 1. SSRF Vulnerability - No URL Scheme Validation (HIGH)

**Location**:
- `cpm_builtin/embeddings/config.py:129` - URL from config accepted without validation
- `cpm_builtin/embeddings/connector.py:34` - URL used directly in requests
- `cpm_builtin/embeddings/openai.py:148` - Endpoint used without scheme check

**Issue**:
```python
# config.py line 129
url_str = str(url if url is not None else http_base_url)
# No validation of URL scheme

# connector.py line 34
self.endpoint = f"{provider.resolved_http_base_url}{provider.resolved_http_path}"
# Endpoint constructed without scheme validation

# requests made to arbitrary URLs
resp = requests.post(
    self.endpoint,  # Could be file://, data://, ftp://, etc.
    json=payload,
    headers=self._headers,
    timeout=timeout,
    auth=self._auth,
)
```

**Risk**: An attacker who can control the embeddings configuration (via config file or environment variables) can make the application:
- Read local files via `file:///etc/passwd`
- Make requests to internal services via `http://localhost:6379/`
- Exfiltrate data via `ftp://attacker.com/`

**Suggested Fix**:
```python
from urllib.parse import urlparse

def validate_url_scheme(url: str) -> None:
    """Validate that URL uses safe HTTP/HTTPS scheme."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"Invalid URL scheme '{parsed.scheme}'. "
            "Only http:// and https:// are allowed for security."
        )

# Apply in config.py line 129:
url_str = str(url if url is not None else http_base_url)
validate_url_scheme(url_str)
```

### 2. API Keys May Leak in Debug Logs (HIGH)

**Location**: `cpm_builtin/embeddings/openai.py:183-188`

**Issue**:
```python
logger.debug(
    "openai embeddings request attempt=%s endpoint=%s count=%s",
    attempt,
    self.endpoint,
    len(request.texts),
)
# Headers with API keys are sent in line 192
response = requests.post(
    self.endpoint,
    json=payload,
    headers=headers,  # Contains Authorization: Bearer <token>
    timeout=self.timeout,
)
```

While the logger doesn't explicitly log headers, if debug logging is enabled elsewhere or if requests library logging is verbose, authorization headers could leak. Additionally, no explicit redaction is performed on error messages.

**Risk**: API keys/tokens could be exposed in:
- Application logs when debug mode is enabled
- Error traces and stack dumps
- Monitoring/observability systems that capture log output

**Suggested Fix**:
```python
def _redact_headers_for_logging(headers: dict[str, str]) -> dict[str, str]:
    """Return headers dict with sensitive values redacted."""
    redacted = headers.copy()
    sensitive_keys = {"authorization", "x-api-key", "api-key"}
    for key in redacted:
        if key.lower() in sensitive_keys:
            redacted[key] = "***REDACTED***"
    return redacted

# In logging statements:
logger.debug(
    "openai embeddings request attempt=%s endpoint=%s count=%s headers=%s",
    attempt,
    self.endpoint,
    len(request.texts),
    _redact_headers_for_logging(headers),
)
```

### 3. Error Messages Expose Response Bodies (MEDIUM)

**Location**: `cpm_builtin/embeddings/openai.py:30-33, 197-199`

**Issue**:
```python
def _error_body_snippet(response: requests.Response, max_chars: int = 200) -> str:
    body = response.text or ""
    compact = " ".join(body.split())
    return compact[:max_chars]  # Truncated but still 200 chars

# Used in error handling:
snippet = _error_body_snippet(response)
raise ValueError(
    f"bad request (status={status}) payload_snippet='{snippet}'"
)
```

**Risk**: Error responses from upstream services might contain:
- Internal service details (versions, paths)
- Sensitive configuration information
- Stack traces or debugging info
- User data from malformed requests

**Suggested Fix**:
```python
def _error_body_snippet(response: requests.Response, max_chars: int = 100) -> str:
    """Extract sanitized error snippet, redacting sensitive patterns."""
    body = response.text or ""
    compact = " ".join(body.split())

    # Redact common sensitive patterns
    import re
    compact = re.sub(r'Bearer\s+[\w-]+', 'Bearer ***', compact, flags=re.IGNORECASE)
    compact = re.sub(r'api[_-]?key["\s:=]+[\w-]+', 'api_key=***', compact, flags=re.IGNORECASE)
    compact = re.sub(r'password["\s:=]+[^\s"]+', 'password=***', compact, flags=re.IGNORECASE)

    return compact[:max_chars]
```

### 4. Basic Auth Credentials in Clear (MEDIUM)

**Location**: `cpm_builtin/embeddings/connector.py:44-46`

**Issue**:
```python
if auth_type == "basic":
    username = auth_entry.get("username") or ""
    password = auth_entry.get("password") or ""
    auth_object = HTTPBasicAuth(username, password)
```

HTTPBasicAuth sends credentials in base64 encoding (not encrypted). Without TLS, credentials are transmitted in clear text.

**Risk**: If used over HTTP (not HTTPS):
- Credentials can be intercepted via network sniffing
- Man-in-the-middle attacks can capture credentials
- Proxy servers may log credentials

**Note**: While the code doesn't prevent HTTPS usage, there's no warning or validation.

**Suggested Fix**:
```python
if auth_type == "basic":
    username = auth_entry.get("username") or ""
    password = auth_entry.get("password") or ""
    auth_object = HTTPBasicAuth(username, password)

    # Warn if using basic auth without TLS
    if not self.provider.resolved_http_base_url.startswith("https://"):
        logger.warning(
            "Basic authentication over HTTP is insecure. "
            "Credentials will be transmitted in base64 (not encrypted). "
            "Use HTTPS for secure credential transmission."
        )
```

### 5. No Validation of Custom Headers (LOW)

**Location**:
- `cpm_builtin/embeddings/config.py:98, 106`
- `cpm_builtin/embeddings/connector.py:54`

**Issue**:
```python
# config.py - headers accepted as-is
for header_key, header_value in headers_raw.items():
    headers[str(header_key)] = str(_resolve_env_value(header_value))

# connector.py - headers merged without filtering
headers.update(self._build_hint_headers())
```

**Risk**: Users could inject sensitive or problematic headers:
- `Host` header manipulation
- `X-Forwarded-For` spoofing
- `Content-Length` / `Content-Type` manipulation
- Injection of authentication headers that conflict

**Suggested Fix**:
```python
FORBIDDEN_HEADERS = {
    "host", "content-length", "content-type",
    "transfer-encoding", "connection"
}

def _sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    """Remove forbidden headers and validate values."""
    sanitized = {}
    for key, value in headers.items():
        key_lower = key.lower()
        if key_lower in FORBIDDEN_HEADERS:
            logger.warning(f"Ignoring forbidden header: {key}")
            continue
        # Validate header value (no newlines, no control chars)
        if "\n" in value or "\r" in value:
            raise ValueError(f"Invalid header value for '{key}': contains newline")
        sanitized[key] = value
    return sanitized
```

### 6. Metadata Header Propagation (LOW)

**Location**: `cpm_builtin/embeddings/openai.py:70-72`

**Issue**:
```python
metadata = hints.get("metadata_b64")
if metadata is not None:
    headers["X-CPM-Metadata"] = str(metadata)
```

**Risk**: The `metadata_b64` field is passed directly from hints to headers without validation. If this contains sensitive or malicious content:
- Could leak sensitive information to upstream servers
- Could be used for header injection if not properly validated
- Base64 content is opaque and hard to audit

**Suggested Fix**:
```python
# Option 1: Document the security implications
# Add to docstring:
"""
WARNING: metadata_b64 is passed directly to upstream servers via
X-CPM-Metadata header. Do not include sensitive information.
"""

# Option 2: Validate base64 format and size limit
import base64

metadata = hints.get("metadata_b64")
if metadata is not None:
    metadata_str = str(metadata)
    # Validate base64 format
    try:
        base64.b64decode(metadata_str, validate=True)
    except Exception:
        raise ValueError("metadata_b64 must be valid base64")
    # Limit size to prevent header bloat
    if len(metadata_str) > 1024:
        raise ValueError("metadata_b64 exceeds maximum size (1024 bytes)")
    headers["X-CPM-Metadata"] = metadata_str
```

### 7. Cache Stores Cleartext (LOW)

**Location**: `cpm_builtin/embeddings/cache.py:16, 32`

**Issue**:
```python
def _entry_path(self, provider: str, text: str) -> Path:
    digest = hashlib.sha256(f"{provider}|{text}".encode("utf-8")).hexdigest()
    # ...

def set(self, provider: str, text: str, vector: Sequence[float]) -> None:
    path = self._entry_path(provider, text)
    payload = {"vector": [float(value) for value in vector]}
    path.write_text(json.dumps(payload, ...), encoding="utf-8")
```

**Risk**: While text content is hashed for the filename, the cache stores:
- The original text could be reverse-engineered from vectors in some cases
- Cache directory permissions might be too permissive
- No encryption at rest

**Note**: This is LOW severity because:
- Embedding vectors are generally less sensitive than original text
- Cache is in `.cpm/cache` which should be gitignored
- Real risk depends on sensitivity of embedded content

**Suggested Fix**:
```python
# Document cache security considerations
"""
SECURITY NOTE: Embedding cache stores vectors in cleartext JSON.
- Ensure .cpm/cache is in .gitignore
- Set restrictive permissions on cache directory (0700)
- Do not embed sensitive PII or secrets
- Consider encrypting cache in high-security environments
"""

def __init__(self, cache_root: Path | str | None = None) -> None:
    base = Path(cache_root) if cache_root else Path(".cpm/cache/embeddings")
    self.cache_root = base.expanduser()
    self.cache_root.mkdir(parents=True, exist_ok=True)
    # Set restrictive permissions
    self.cache_root.chmod(0o700)
```

## Robustness Analysis

### Connection Failures
✅ **Well Handled**
- Retry logic with exponential backoff (openai.py:181-244)
- Proper exception catching for `RequestException`, `Timeout`
- Maximum retry count enforced (default: 2 retries)
- Timeouts always specified (default: 10.0s)

```python
for attempt in range(1, self.max_retries + 1):
    try:
        response = requests.post(...)
        # ...
    except Timeout as exc:
        last_error = exc
        logger.warning("openai embeddings timeout attempt=%s/%s", ...)
    except RequestException as exc:
        last_error = exc
        logger.warning("openai embeddings transport error attempt=%s/%s: %s", ...)
```

### Partial Responses
✅ **Well Handled**
- Response validation checks vector count matches input count (types.py:201-221)
- Index validation ensures contiguous ordering (openai.py:109-113)
- Dimension consistency validation (types.py:136-151)
- Empty vectors explicitly rejected (types.py:132-133, 142)

```python
def validate_against_request(self, request: EmbedRequestIR) -> None:
    if len(self.vectors) != len(request.texts):
        raise ValueError(
            f"response has {len(self.vectors)} vectors "
            f"but request has {len(request.texts)} texts"
        )
```

### Resource Cleanup
⚠️ **Mostly Good, Minor Gaps**

**Good:**
- No persistent connections (uses requests.post directly)
- No file handles left open
- Cache writes are atomic (write_text handles cleanup)

**Minor Gaps:**
- No explicit session management with connection pooling
- Could benefit from context managers for better resource guarantees

**Suggestion**:
```python
# Could improve with session reuse:
class OpenAIEmbeddingsHttpClient:
    def __init__(self, ...):
        # ...
        self._session = requests.Session()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._session.close()

    def embed(self, ...):
        response = self._session.post(...)  # Reuse session
```

### Input Validation
✅ **Excellent**
- Type checking for all inputs (types.py:38-61)
- Empty input rejection (types.py:44-45)
- String type validation (types.py:47-49)
- Dimension consistency checks (types.py:136-151)
- Numeric type validation (types.py:154-159)
- NaN/Inf detection (postprocess.py:58-59)

### Error Handling
✅ **Strong**
- Specific exception types for different failures
- Proper error propagation with context
- Status code differentiation (4xx vs 5xx)
- ValueError for bad requests (no retry)
- RuntimeError for server errors (with retry)

## Recommendations

### Priority 1 (Critical - Implement Immediately)

1. **Add URL Scheme Validation**
   - Implement `validate_url_scheme()` function
   - Apply to all URL inputs in config.py, connector.py, client.py
   - Only allow `http://` and `https://` schemes
   - **Impact**: Prevents SSRF attacks
   - **Effort**: 30 minutes

2. **Redact Auth Headers in Logs**
   - Implement `_redact_headers_for_logging()` function
   - Apply to all logging statements that might expose headers
   - Redact `authorization`, `x-api-key`, `api-key` headers
   - **Impact**: Prevents credential leakage
   - **Effort**: 1 hour

### Priority 2 (Important - Implement Soon)

3. **Sanitize Error Messages**
   - Improve `_error_body_snippet()` to redact sensitive patterns
   - Reduce max snippet size from 200 to 100 chars
   - Add regex-based redaction for common secrets
   - **Impact**: Reduces information leakage
   - **Effort**: 1 hour

4. **Warn on Insecure Basic Auth**
   - Add warning when using basic auth over HTTP
   - Document TLS requirement in config documentation
   - **Impact**: Reduces credential exposure risk
   - **Effort**: 30 minutes

### Priority 3 (Nice to Have - Consider for Future)

5. **Validate Custom Headers**
   - Implement header sanitization function
   - Block forbidden headers (Host, Content-Length, etc.)
   - Validate header values (no newlines, control chars)
   - **Impact**: Prevents header injection
   - **Effort**: 1 hour

6. **Document/Validate Metadata Header**
   - Document security implications of metadata_b64
   - Add base64 format validation
   - Enforce size limits (1KB max)
   - **Impact**: Reduces metadata abuse
   - **Effort**: 30 minutes

7. **Harden Cache Security**
   - Set restrictive permissions (0700) on cache directory
   - Add security documentation
   - Consider encryption for sensitive use cases
   - **Impact**: Improves cache security
   - **Effort**: 1 hour

8. **Add Session Reuse**
   - Implement requests.Session for connection pooling
   - Add context manager support
   - **Impact**: Better resource management, improved performance
   - **Effort**: 2 hours

## Positive Security Practices Observed

1. **Timeout Enforcement**: All HTTP requests have timeouts (default 10s)
2. **Input Validation**: Comprehensive type and value checking
3. **Retry Logic**: Proper exponential backoff with max attempts
4. **Error Handling**: Specific exception types, proper propagation
5. **No Code Injection**: No eval(), exec(), or dynamic code execution
6. **Type Safety**: Full type hints, validated at runtime
7. **Vector Validation**: NaN/Inf detection, dimension checks
8. **Response Validation**: Ensures response matches request

## Testing Recommendations

Add security-focused test cases:

```python
def test_ssrf_prevention():
    """Ensure file:// and other schemes are rejected."""
    with pytest.raises(ValueError, match="Invalid URL scheme"):
        EmbeddingProviderConfig.from_dict("test", {
            "url": "file:///etc/passwd"
        })

def test_api_key_not_logged(caplog):
    """Ensure API keys don't appear in logs."""
    client = OpenAIEmbeddingsHttpClient(
        endpoint="http://test.com",
        api_key="secret-key-12345"
    )
    # ... trigger logging ...
    assert "secret-key-12345" not in caplog.text

def test_header_injection_prevention():
    """Ensure newlines in headers are rejected."""
    with pytest.raises(ValueError, match="contains newline"):
        EmbeddingProviderConfig.from_dict("test", {
            "url": "http://test.com",
            "headers": {"X-Custom": "value\nX-Injected: malicious"}
        })
```

## Conclusion

The embeddings implementation is **fundamentally sound** with good robustness patterns, but requires **two critical security fixes** (URL validation and auth header redaction) before production use in security-sensitive environments. The remaining issues are lower severity but should be addressed to meet defense-in-depth best practices.

**Recommendation**: Fix Priority 1 items before any production deployment. Priority 2 items should be addressed in the next sprint. Priority 3 items can be scheduled based on risk assessment and resource availability.
