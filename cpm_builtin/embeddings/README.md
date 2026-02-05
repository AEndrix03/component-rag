# cpm_builtin/embeddings - Embedding Management System

**HTTP-based embedding provider configuration and connector system.**

The embedding system provides a flexible, YAML-configured approach to managing multiple embedding providers with HTTP connectivity, authentication, batching, and retry logic.

---

## Quick Start

```python
from cpm_builtin.embeddings.config import EmbeddingsConfigService
from cpm_builtin.embeddings.connector import HttpEmbeddingConnector

# Load configuration
service = EmbeddingsConfigService(config_dir=".cpm/config")

# Get default provider
provider = service.default_provider()

# Create connector
connector = HttpEmbeddingConnector(provider)

# Embed texts
texts = ["Hello, world!", "Another document"]
vectors = connector.embed_texts(texts)
print(vectors.shape)  # (2, 768)
```

---

## Architecture Overview

```
cpm_builtin/embeddings/
├── config.py       # EmbeddingProviderConfig, EmbeddingsConfigService
├── connector.py    # HttpEmbeddingConnector (HTTP client)
└── cache.py        # Embedding result caching (not shown here)
```

---

## Configuration

### YAML Structure

Embeddings are configured in `.cpm/config/embeddings.yml`:

```yaml
# .cpm/config/embeddings.yml
default: local-jina

providers:
  - name: local-jina
    type: http
    url: http://127.0.0.1:8876
    model: jinaai/jina-embeddings-v2-base-code
    dims: 768
    batch_size: 32
    timeout: 60
    headers:
      Content-Type: application/json
    auth:
      type: bearer
      token: ${EMBEDDING_API_KEY}

  - name: openai-ada
    type: http
    url: https://api.openai.com/v1
    model: text-embedding-ada-002
    dims: 1536
    batch_size: 16
    timeout: 30
    auth:
      type: bearer
      token: ${OPENAI_API_KEY}

  - name: local-sentence-transformers
    type: http
    url: http://localhost:8877
    model: all-MiniLM-L6-v2
    dims: 384
    batch_size: 64
    timeout: 120
```

**Field Descriptions:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Unique provider identifier |
| `type` | string | Yes | Provider type (currently only "http") |
| `url` | string | Yes | Base URL for embedding API |
| `model` | string | No | Model name to pass to API |
| `dims` | int | No | Expected embedding dimension |
| `batch_size` | int | No | Number of texts per request (default: all at once) |
| `timeout` | float | No | Request timeout in seconds (default: 10.0) |
| `headers` | dict | No | Custom HTTP headers |
| `auth` | object | No | Authentication configuration |
| `extra` | dict | No | Additional options passed to API |

### Authentication

#### Bearer Token

```yaml
auth:
  type: bearer
  token: ${API_KEY}  # Environment variable expansion
```

#### Basic Auth

```yaml
auth:
  type: basic
  username: myuser
  password: ${PASSWORD}
```

#### Simple Token (Legacy)

```yaml
auth: ${API_KEY}  # Treated as bearer token
```

---

## EmbeddingProviderConfig

Data class representing a single provider configuration:

```python
from cpm_builtin.embeddings.config import EmbeddingProviderConfig

provider = EmbeddingProviderConfig(
    name="my-provider",
    type="http",
    url="http://localhost:8876",
    model="sentence-transformers/all-MiniLM-L6-v2",
    dims=384,
    batch_size=32,
    timeout=60.0,
    headers={"X-Custom-Header": "value"},
    auth={"type": "bearer", "token": "secret"},
    extra={"normalize": True},
)

# Serialize to dict
data = provider.to_dict()

# Deserialize from dict
provider = EmbeddingProviderConfig.from_dict("my-provider", data)
```

---

## EmbeddingsConfigService

Service for managing provider configurations:

```python
from cpm_builtin.embeddings.config import EmbeddingsConfigService

service = EmbeddingsConfigService(config_dir=".cpm/config")
```

### List Providers

```python
providers = service.list_providers()
for provider in providers:
    print(f"{provider.name}: {provider.url} ({provider.dims} dims)")
```

### Get Specific Provider

```python
try:
    provider = service.get_provider("local-jina")
    print(f"Model: {provider.model}")
except KeyError:
    print("Provider not found")
```

### Get Default Provider

```python
provider = service.default_provider()
if provider:
    print(f"Default: {provider.name}")
else:
    print("No default provider configured")
```

### Add Provider

```python
from cpm_builtin.embeddings.config import EmbeddingProviderConfig

new_provider = EmbeddingProviderConfig(
    name="azure-openai",
    type="http",
    url="https://my-resource.openai.azure.com",
    model="text-embedding-ada-002",
    dims=1536,
    auth={"type": "bearer", "token": "azure-key"},
)

service.add_provider(new_provider, set_default=True)
```

### Remove Provider

```python
service.remove_provider("old-provider")
```

### Set Default Provider

```python
service.set_default_provider("azure-openai")
```

### Test Provider

```python
from cpm_builtin.embeddings.connector import HttpEmbeddingConnector

success, message, vectors = service.test_provider(
    "local-jina",
    connector_factory=HttpEmbeddingConnector,
    texts=["test string"],
)

if success:
    print(f"Provider OK: {message}")
    print(f"Vector shape: {vectors.shape}")
else:
    print(f"Provider failed: {message}")
```

---

## HttpEmbeddingConnector

HTTP client for embedding APIs:

```python
from cpm_builtin.embeddings.connector import HttpEmbeddingConnector
from cpm_builtin.embeddings.config import EmbeddingProviderConfig

provider = EmbeddingProviderConfig(
    name="local",
    type="http",
    url="http://127.0.0.1:8876",
    model="all-MiniLM-L6-v2",
    dims=384,
    batch_size=32,
    timeout=60.0,
)

connector = HttpEmbeddingConnector(provider, max_retries=3)
```

### Embed Texts

```python
import numpy as np

texts = ["First document", "Second document", "Third document"]
vectors = connector.embed_texts(texts)

print(vectors.shape)  # (3, 384)
print(vectors.dtype)  # float32
```

### API Request Format

The connector sends POST requests to `{url}/embed`:

```json
{
  "texts": ["First text", "Second text"],
  "model": "model-name",
  "extra": {
    "normalize": true
  }
}
```

### API Response Format

Expected response:

```json
{
  "vectors": [
    [0.1, 0.2, 0.3, ...],
    [0.4, 0.5, 0.6, ...]
  ]
}
```

### Batching

If `batch_size` is set, the connector automatically splits large requests:

```python
provider = EmbeddingProviderConfig(
    name="local",
    url="http://localhost:8876",
    model="all-MiniLM-L6-v2",
    dims=384,
    batch_size=32,  # Process 32 texts per request
)

connector = HttpEmbeddingConnector(provider)

# Automatically batches into 4 requests (32 + 32 + 32 + 4)
texts = ["text"] * 100
vectors = connector.embed_texts(texts)  # (100, 384)
```

### Retry Logic

The connector retries failed requests with exponential backoff:

```python
connector = HttpEmbeddingConnector(provider, max_retries=3)

# On failure:
# - Attempt 1: immediate
# - Attempt 2: wait 0.1s
# - Attempt 3: wait 0.2s
# - Raise exception if all fail
```

### Authentication Handling

#### Bearer Token

```python
provider = EmbeddingProviderConfig(
    name="openai",
    url="https://api.openai.com/v1",
    auth={"type": "bearer", "token": "sk-..."},
)

# Adds header: Authorization: Bearer sk-...
```

#### Basic Auth

```python
provider = EmbeddingProviderConfig(
    name="private",
    url="https://private.api",
    auth={"type": "basic", "username": "user", "password": "pass"},
)

# Uses HTTP Basic Authentication
```

#### Custom Headers

```python
provider = EmbeddingProviderConfig(
    name="custom",
    url="https://custom.api",
    headers={"X-API-Key": "my-key"},
)

# Adds custom headers to all requests
```

---

## Usage Examples

### Example 1: Basic Embedding

```python
from cpm_builtin.embeddings.config import EmbeddingsConfigService
from cpm_builtin.embeddings.connector import HttpEmbeddingConnector

# Load configuration
service = EmbeddingsConfigService(".cpm/config")
provider = service.default_provider()

# Connect and embed
connector = HttpEmbeddingConnector(provider)
texts = ["Machine learning", "Natural language processing"]
vectors = connector.embed_texts(texts)

print(f"Embedded {len(texts)} texts into {vectors.shape[1]}-dimensional vectors")
```

### Example 2: Multi-Provider Setup

```python
from cpm_builtin.embeddings.config import (
    EmbeddingsConfigService,
    EmbeddingProviderConfig,
)

service = EmbeddingsConfigService(".cpm/config")

# Add multiple providers
providers = [
    EmbeddingProviderConfig(
        name="local-fast",
        url="http://localhost:8876",
        model="all-MiniLM-L6-v2",
        dims=384,
    ),
    EmbeddingProviderConfig(
        name="local-accurate",
        url="http://localhost:8877",
        model="jinaai/jina-embeddings-v2-base-code",
        dims=768,
    ),
]

for provider in providers:
    service.add_provider(provider)

service.set_default_provider("local-fast")

# List all
for p in service.list_providers():
    print(f"{p.name}: {p.dims} dims")
```

### Example 3: Error Handling

```python
from cpm_builtin.embeddings.connector import HttpEmbeddingConnector
from requests.exceptions import RequestException

connector = HttpEmbeddingConnector(provider, max_retries=2)

try:
    vectors = connector.embed_texts(["test"])
except RequestException as e:
    print(f"Embedding failed: {e}")
except ValueError as e:
    print(f"Invalid response: {e}")
```

### Example 4: Testing Provider

```python
from cpm_builtin.embeddings.config import EmbeddingsConfigService
from cpm_builtin.embeddings.connector import HttpEmbeddingConnector

service = EmbeddingsConfigService(".cpm/config")

# Test all providers
for provider in service.list_providers():
    success, message, _ = service.test_provider(
        provider.name,
        connector_factory=HttpEmbeddingConnector,
        texts=["test"],
    )
    status = "OK" if success else "FAILED"
    print(f"{provider.name}: {status} - {message}")
```

### Example 5: Custom Provider with Extra Options

```python
from cpm_builtin.embeddings.config import EmbeddingProviderConfig
from cpm_builtin.embeddings.connector import HttpEmbeddingConnector

provider = EmbeddingProviderConfig(
    name="custom",
    url="http://custom.api",
    model="custom-model",
    dims=1024,
    extra={
        "normalize": True,
        "pooling": "mean",
        "precision": "fp16",
    },
)

connector = HttpEmbeddingConnector(provider)
vectors = connector.embed_texts(["sample text"])

# Extra options are passed in the request payload
```

---

## Integration with Build System

The embedding system integrates with the build process:

```python
from cpm_core.app import CPMApp
from cpm_builtin.embeddings.config import EmbeddingsConfigService
from cpm_builtin.embeddings.connector import HttpEmbeddingConnector

app = CPMApp(start_dir=".")
app.bootstrap()

# Load embeddings config
embeddings_service = EmbeddingsConfigService(app.workspace.root / "config")
provider = embeddings_service.default_provider()

# Create connector for build
connector = HttpEmbeddingConnector(provider)

# Use in build process
chunks = [...]  # from chunking
texts = [chunk.text for chunk in chunks]
vectors = connector.embed_texts(texts)
```

---

## Configuration Best Practices

### 1. Use Environment Variables

```yaml
providers:
  - name: production
    url: ${EMBED_URL}
    auth:
      type: bearer
      token: ${EMBED_TOKEN}
```

### 2. Set Appropriate Batch Sizes

```yaml
# For local servers with limited memory
batch_size: 16

# For powerful servers
batch_size: 128

# For remote APIs with rate limits
batch_size: 32
```

### 3. Configure Timeouts

```yaml
# Local server (fast)
timeout: 10

# Remote API (slower)
timeout: 60

# Large batch processing
timeout: 300
```

### 4. Specify Dimensions

Always specify `dims` to enable validation:

```yaml
dims: 768  # Ensures response matches expected dimension
```

---

## Error Handling

### Common Errors

#### Connection Refused

```python
# Server not running
# Solution: Start embedding server or check URL
```

#### Timeout

```python
# Batch too large or server overloaded
# Solution: Reduce batch_size or increase timeout
```

#### Dimension Mismatch

```python
ValueError("response vector does not match expected dims")
# Solution: Verify provider.dims matches model output
```

#### Authentication Failed

```python
# HTTP 401 or 403
# Solution: Check auth configuration and credentials
```

---

## Testing

```bash
# Run all embedding tests
pytest cpm_builtin/embeddings/

# Test configuration
pytest cpm_builtin/embeddings/test_config.py -v

# Test connector
pytest cpm_builtin/embeddings/test_connector.py -v
```

---

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `RAG_EMBED_URL` | Default embedding server URL | `http://127.0.0.1:8876` |
| `EMBEDDING_API_KEY` | API key for embedding service | None |
| `OPENAI_API_KEY` | OpenAI API key | None |

---

## See Also

- [cpm_builtin/README.md](../README.md) - Built-in features overview
- [cpm_builtin/chunking/README.md](../chunking/README.md) - Chunking strategies
- [cpm_core/build/README.md](../../cpm_core/build/README.md) - Build system integration
- [cpm_core/packet/README.md](../../cpm_core/packet/README.md) - Packet structure
