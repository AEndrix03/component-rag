from __future__ import annotations

import os
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from cpm_builtin.embeddings.connector import EmbeddingConnector
    import numpy as np

CONFIG_FILENAME = "embeddings.yml"
DEFAULT_DISCOVERY_TTL_SECONDS = 900


def _ensure_mapping(data: Any) -> Mapping[str, Any]:
    if isinstance(data, Mapping):
        return data
    raise ValueError("expected mapping for embeddings configuration")


def _resolve_env_value(value: Any) -> Any:
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        env_name = value[2:-1].strip()
        if env_name:
            return os.getenv(env_name, "")
    return value


def _to_optional_int(value: Any) -> int | None:
    value = _resolve_env_value(value)
    if value is None or value == "":
        return None
    return int(value)


def _to_optional_float(value: Any) -> float | None:
    value = _resolve_env_value(value)
    if value is None or value == "":
        return None
    return float(value)


def _to_optional_bool(value: Any) -> bool | None:
    value = _resolve_env_value(value)
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _parse_normalize_mode(value: Any) -> str:
    value = _resolve_env_value(value)
    normalized = str(value).strip().lower() if value is not None else ""
    if not normalized:
        return "auto"
    if normalized in {"server", "client", "auto"}:
        return normalized
    raise ValueError("normalize_mode must be one of: server, client, auto")


@dataclass
class EmbeddingProviderConfig:
    name: str
    type: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    auth: dict[str, Any] | None = None
    timeout: float | None = None
    batch_size: int | None = None
    model: str | None = None
    dims: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    http_base_url: str | None = None
    http_path: str = "/v1/embeddings"
    http_embeddings_path: str | None = None
    http_models_path: str | None = "/v1/models"
    http_timeout: float | None = None
    http_headers_static: dict[str, str] = field(default_factory=dict)
    hint_dim: int | None = None
    hint_normalize: bool | None = None
    normalize_mode: str = "auto"
    hint_task: str | None = None
    hint_model: str | None = None
    discovery_ttl_seconds: int | None = DEFAULT_DISCOVERY_TTL_SECONDS
    model_artifacts: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, name: str, data: Mapping[str, Any]) -> "EmbeddingProviderConfig":
        raw = _ensure_mapping(data)
        headers: dict[str, str] = {}
        headers_raw = raw.get("headers") or {}
        headers_raw = _ensure_mapping(headers_raw)
        for header_key, header_value in headers_raw.items():
            headers[str(header_key)] = str(_resolve_env_value(header_value))

        http_raw = raw.get("http") or {}
        http_raw = _ensure_mapping(http_raw)
        headers_static: dict[str, str] = {}
        headers_static_raw = http_raw.get("headers_static") or {}
        headers_static_raw = _ensure_mapping(headers_static_raw)
        for header_key, header_value in headers_static_raw.items():
            headers_static[str(header_key)] = str(_resolve_env_value(header_value))

        hints_raw = raw.get("hints") or {}
        hints_raw = _ensure_mapping(hints_raw)

        extra_entries: dict[str, Any] = {}
        extra_raw = raw.get("extra") or {}
        extra_raw = _ensure_mapping(extra_raw)
        for extra_key, extra_value in extra_raw.items():
            if extra_key is None:
                continue
            extra_entries[str(extra_key)] = extra_value

        auth = raw.get("auth")
        if isinstance(auth, Mapping):
            auth = {str(k): _resolve_env_value(v) for k, v in auth.items()}
        elif auth is not None and isinstance(auth, str):
            auth = {"token": _resolve_env_value(auth)}

        url = _resolve_env_value(raw.get("url"))
        http_base_url = _resolve_env_value(http_raw.get("base_url"))
        if url is None and http_base_url is None:
            raise KeyError("url")
        url_str = str(url if url is not None else http_base_url)

        hint_model = _resolve_env_value(hints_raw.get("model"))
        if hint_model is None:
            hint_model = _resolve_env_value(raw.get("model"))

        hint_dim = _resolve_env_value(hints_raw.get("dim"))
        if hint_dim is None:
            hint_dim = _resolve_env_value(raw.get("dims"))

        return cls(
            name=name,
            type=str(raw.get("type", "http")),
            url=url_str,
            headers=headers,
            auth=auth,
            timeout=_to_optional_float(raw.get("timeout")),
            batch_size=_to_optional_int(raw.get("batch_size")),
            model=str(_resolve_env_value(raw.get("model"))) if raw.get("model") is not None else None,
            dims=_to_optional_int(raw.get("dims")),
            extra=extra_entries,
            http_base_url=str(http_base_url) if http_base_url is not None else None,
            http_path=str(_resolve_env_value(http_raw.get("path", "/v1/embeddings"))),
            http_embeddings_path=(
                str(_resolve_env_value(http_raw.get("embeddings_path")))
                if http_raw.get("embeddings_path") is not None
                else None
            ),
            http_models_path=(
                str(_resolve_env_value(http_raw.get("models_path")))
                if http_raw.get("models_path") is not None
                else "/v1/models"
            ),
            http_timeout=_to_optional_float(http_raw.get("timeout")),
            http_headers_static=headers_static,
            hint_dim=_to_optional_int(hint_dim),
            hint_normalize=_to_optional_bool(hints_raw.get("normalize")),
            normalize_mode=_parse_normalize_mode(raw.get("normalize_mode")),
            hint_task=(
                str(_resolve_env_value(hints_raw.get("task")))
                if hints_raw.get("task") is not None
                else None
            ),
            hint_model=str(hint_model) if hint_model is not None else None,
            discovery_ttl_seconds=_to_optional_int(raw.get("discovery_ttl_seconds")),
            model_artifacts=(
                dict(_ensure_mapping(raw.get("model_artifacts")))
                if raw.get("model_artifacts") is not None
                else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "type": self.type,
            "http": {
                "base_url": self.resolved_http_base_url,
                "embeddings_path": self.resolved_http_embeddings_path,
                "models_path": self.resolved_http_models_path,
            },
        }
        if self.url:
            data["url"] = self.url
        if self.headers:
            data["headers"] = self.headers
        if self.auth:
            data["auth"] = self.auth
        if self.timeout is not None:
            data["timeout"] = self.timeout
        if self.batch_size is not None:
            data["batch_size"] = self.batch_size
        if self.model is not None:
            data["model"] = self.model
        if self.dims is not None:
            data["dims"] = self.dims
        if self.extra:
            data["extra"] = self.extra
        if self.resolved_http_timeout is not None:
            data["http"]["timeout"] = self.resolved_http_timeout
        if self.resolved_headers_static:
            data["http"]["headers_static"] = self.resolved_headers_static

        hints: dict[str, Any] = {}
        if self.resolved_hint_dim is not None:
            hints["dim"] = self.resolved_hint_dim
        if self.hint_normalize is not None:
            hints["normalize"] = self.hint_normalize
        if self.hint_task:
            hints["task"] = self.hint_task
        if self.resolved_hint_model:
            hints["model"] = self.resolved_hint_model
        if hints:
            data["hints"] = hints
        if self.normalize_mode != "auto":
            data["normalize_mode"] = self.normalize_mode
        if self.discovery_ttl_seconds is not None:
            data["discovery_ttl_seconds"] = int(self.discovery_ttl_seconds)
        if self.model_artifacts:
            data["model_artifacts"] = dict(self.model_artifacts)
        return data

    @property
    def resolved_http_base_url(self) -> str:
        return (self.http_base_url or self.url).rstrip("/")

    @property
    def resolved_http_path(self) -> str:
        path = self.http_embeddings_path or self.http_path or "/v1/embeddings"
        return path if path.startswith("/") else f"/{path}"

    @property
    def resolved_http_embeddings_path(self) -> str:
        return self.resolved_http_path

    @property
    def resolved_http_models_path(self) -> str:
        path = self.http_models_path or "/v1/models"
        return path if path.startswith("/") else f"/{path}"

    @property
    def resolved_http_timeout(self) -> float | None:
        if self.http_timeout is not None:
            return float(self.http_timeout)
        if self.timeout is not None:
            return float(self.timeout)
        return None

    @property
    def resolved_headers_static(self) -> dict[str, str]:
        merged = {str(k): str(v) for k, v in self.headers.items()}
        merged.update({str(k): str(v) for k, v in self.http_headers_static.items()})
        return merged

    @property
    def resolved_hint_dim(self) -> int | None:
        if self.hint_dim is not None:
            return int(self.hint_dim)
        return self.dims

    @property
    def resolved_hint_model(self) -> str | None:
        return self.hint_model or self.model


@dataclass
class EmbeddingsConfig:
    default: str | None = None
    providers: dict[str, EmbeddingProviderConfig] = field(default_factory=dict)


ConnectorFactory = Callable[
    [EmbeddingProviderConfig], "EmbeddingConnector"
]


class EmbeddingsConfigService:
    def __init__(self, config_dir: Path | str | None = None) -> None:
        self.config_path = _resolve_config_path(config_dir)
        self.config_dir = self.config_path.parent
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._config = self._load()

    def _load(self) -> EmbeddingsConfig:
        if not self.config_path.exists():
            return EmbeddingsConfig()
        raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        default = raw.get("default")
        providers_raw = raw.get("providers") or {}
        providers: dict[str, EmbeddingProviderConfig] = {}
        for name, data in providers_raw.items():
            if not isinstance(name, str):
                continue
            try:
                providers[name] = EmbeddingProviderConfig.from_dict(name, data)
            except KeyError:
                continue
        if default not in providers:
            default = None
        return EmbeddingsConfig(default=default, providers=providers)

    def _persist(self) -> None:
        payload = {
            "default": self._config.default,
            "providers": {
                name: provider.to_dict()
                for name, provider in self._config.providers.items()
            },
        }
        self.config_path.write_text(
            yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
        )

    @property
    def discovery_cache_path(self) -> Path:
        if self.config_dir.name == "config":
            base = self.config_dir.parent
        else:
            base = self.config_dir
        return base / "cache" / "embeddings" / "discovery.json"

    def list_providers(self) -> list[EmbeddingProviderConfig]:
        return sorted(
            self._config.providers.values(), key=lambda provider: provider.name
        )

    def get_provider(self, name: str) -> EmbeddingProviderConfig:
        try:
            return self._config.providers[name]
        except KeyError as exc:
            raise KeyError(f"provider '{name}' not found") from exc

    def default_provider(self) -> EmbeddingProviderConfig | None:
        if self._config.default:
            return self._config.providers.get(self._config.default)
        return None

    def add_provider(self, provider: EmbeddingProviderConfig, *, set_default: bool = False) -> None:
        self._config.providers[provider.name] = provider
        if set_default or self._config.default is None:
            self._config.default = provider.name
        self._persist()

    def remove_provider(self, name: str) -> None:
        if name not in self._config.providers:
            raise KeyError(f"provider '{name}' not found")
        del self._config.providers[name]
        if self._config.default == name:
            self._config.default = None
        self._persist()

    def set_default_provider(self, name: str) -> None:
        if name not in self._config.providers:
            raise KeyError(f"provider '{name}' not found")
        self._config.default = name
        self._persist()

    def test_provider(
        self,
        name: str,
        connector_factory: ConnectorFactory,
        *,
        texts: Sequence[str] | None = None,
    ) -> tuple[bool, str, "np.ndarray" | None]:
        provider = self.get_provider(name)
        connector = connector_factory(provider)
        test_texts = list(texts or ["test"])
        try:
            matrix = connector.embed_texts(test_texts)
        except Exception as exc:
            return False, str(exc), None
        return True, f"received {matrix.shape}", matrix

    def refresh_discovery(
        self,
        *,
        provider_name: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        from .discovery import refresh_provider_discovery

        providers = self.list_providers()
        if provider_name:
            providers = [self.get_provider(provider_name)]

        refreshed: dict[str, Any] = {}
        for provider in providers:
            ttl = provider.discovery_ttl_seconds
            result = refresh_provider_discovery(
                provider,
                cache_path=self.discovery_cache_path,
                ttl_seconds=ttl,
                force=force,
            )
            refreshed[provider.name] = result.to_dict()
        return refreshed

    def read_discovery(self) -> dict[str, Any]:
        from .discovery import load_cache

        return load_cache(self.discovery_cache_path)


def _resolve_config_path(config_dir: Path | str | None) -> Path:
    if config_dir is None:
        return Path(".cpm") / "config" / CONFIG_FILENAME

    raw = Path(config_dir).expanduser()
    if raw.suffix in {".yml", ".yaml"}:
        return raw

    direct = raw / CONFIG_FILENAME
    if direct.exists():
        return direct

    config_child = raw / "config" / CONFIG_FILENAME
    if (raw / "config").exists() or raw.name == ".cpm":
        return config_child

    return direct
