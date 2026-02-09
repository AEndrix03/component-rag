"""Internal representation types for embedding requests and responses.

These types define a stable internal contract between CPM embedding clients
and the rest of the system, decoupled from external API formats (OpenAI, TEI, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EmbedRequestIR:
    """Internal representation of an embedding request.

    Attributes:
        texts: List of texts to embed (always an array, never empty)
        model: Optional model identifier (can be None if using provider default)
        hints: Semantic hints for embedding behavior (normalize, max_length, etc.)
               These are provider-agnostic parameters that may be passed as headers
               or adapted to provider-specific formats
        extra: Provider-specific parameters (passed through as-is)

    Examples:
        >>> req = EmbedRequestIR(
        ...     texts=["hello world"],
        ...     model="jina-v2-base-en",
        ...     hints={"normalize": True, "max_length": 512}
        ... )
    """

    texts: list[str]
    model: str | None = None
    hints: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate request fields."""
        # Validate texts is a non-empty list of strings
        if not isinstance(self.texts, list):
            raise TypeError(f"texts must be a list, got {type(self.texts).__name__}")

        if not self.texts:
            raise ValueError("texts cannot be empty")

        for idx, text in enumerate(self.texts):
            if not isinstance(text, str):
                raise TypeError(f"texts[{idx}] must be str, got {type(text).__name__}")

        # Validate model is string or None
        if self.model is not None and not isinstance(self.model, str):
            raise TypeError(f"model must be str or None, got {type(self.model).__name__}")

        # Validate hints is a dict
        if not isinstance(self.hints, dict):
            raise TypeError(f"hints must be dict, got {type(self.hints).__name__}")

        # Validate extra is a dict
        if not isinstance(self.extra, dict):
            raise TypeError(f"extra must be dict, got {type(self.extra).__name__}")

    def with_hints(self, **hints: Any) -> EmbedRequestIR:
        """Create a new request with additional hints merged in.

        Args:
            **hints: Additional hints to merge (overwrites existing keys)

        Returns:
            New EmbedRequestIR with merged hints

        Examples:
            >>> req = EmbedRequestIR(texts=["test"])
            >>> req2 = req.with_hints(normalize=True, max_length=512)
        """
        merged = {**self.hints, **hints}
        return EmbedRequestIR(
            texts=self.texts,
            model=self.model,
            hints=merged,
            extra=self.extra,
        )

    def with_extra(self, **extra: Any) -> EmbedRequestIR:
        """Create a new request with additional extra parameters merged in.

        Args:
            **extra: Additional extra parameters to merge

        Returns:
            New EmbedRequestIR with merged extra
        """
        merged = {**self.extra, **extra}
        return EmbedRequestIR(
            texts=self.texts,
            model=self.model,
            hints=self.hints,
            extra=merged,
        )


@dataclass(frozen=True)
class EmbedResponseIR:
    """Internal representation of an embedding response.

    Attributes:
        vectors: List of embedding vectors (one per input text)
                 Each vector is a list of floats (not yet converted to numpy)
        model: Optional model identifier that produced these embeddings
        usage: Optional token usage statistics (prompt_tokens, total_tokens, etc.)
        extra: Optional provider-specific metadata

    Examples:
        >>> resp = EmbedResponseIR(
        ...     vectors=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
        ...     model="jina-v2-base-en",
        ...     usage={"prompt_tokens": 10, "total_tokens": 10}
        ... )
    """

    vectors: list[list[float]]
    model: str | None = None
    usage: dict[str, Any] | None = None
    extra: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Validate response fields."""
        # Validate vectors is a non-empty list of lists
        if not isinstance(self.vectors, list):
            raise TypeError(f"vectors must be a list, got {type(self.vectors).__name__}")

        if not self.vectors:
            raise ValueError("vectors cannot be empty")

        # Validate each vector is a list of floats with consistent dimensions
        first_dim: int | None = None
        for idx, vec in enumerate(self.vectors):
            if not isinstance(vec, list):
                raise TypeError(f"vectors[{idx}] must be list, got {type(vec).__name__}")

            if not vec:
                raise ValueError(f"vectors[{idx}] cannot be empty")

            # Check dimension consistency
            if first_dim is None:
                first_dim = len(vec)
            elif len(vec) != first_dim:
                raise ValueError(
                    f"vectors[{idx}] has dimension {len(vec)}, "
                    f"expected {first_dim} (inconsistent dimensions)"
                )

            # Validate all elements are numeric
            for elem_idx, elem in enumerate(vec):
                if not isinstance(elem, (int, float)):
                    raise TypeError(
                        f"vectors[{idx}][{elem_idx}] must be numeric, "
                        f"got {type(elem).__name__}"
                    )

        # Validate model is string or None
        if self.model is not None and not isinstance(self.model, str):
            raise TypeError(f"model must be str or None, got {type(self.model).__name__}")

        # Validate usage is dict or None
        if self.usage is not None and not isinstance(self.usage, dict):
            raise TypeError(f"usage must be dict or None, got {type(self.usage).__name__}")

        # Validate extra is dict or None
        if self.extra is not None and not isinstance(self.extra, dict):
            raise TypeError(f"extra must be dict or None, got {type(self.extra).__name__}")

    @property
    def dims(self) -> int:
        """Return the dimension of the embedding vectors.

        Returns:
            Dimension of vectors (assumes all vectors have same dimension)

        Examples:
            >>> resp = EmbedResponseIR(vectors=[[0.1, 0.2, 0.3]])
            >>> resp.dims
            3
        """
        return len(self.vectors[0]) if self.vectors else 0

    @property
    def count(self) -> int:
        """Return the number of vectors in this response.

        Returns:
            Number of embedding vectors

        Examples:
            >>> resp = EmbedResponseIR(vectors=[[0.1], [0.2]])
            >>> resp.count
            2
        """
        return len(self.vectors)

    def validate_against_request(self, request: EmbedRequestIR) -> None:
        """Validate that this response matches the given request.

        Args:
            request: The original request that produced this response

        Raises:
            ValueError: If response doesn't match request (e.g., wrong count)

        Examples:
            >>> req = EmbedRequestIR(texts=["a", "b"])
            >>> resp = EmbedResponseIR(vectors=[[0.1], [0.2]])
            >>> resp.validate_against_request(req)  # OK
            >>> bad_resp = EmbedResponseIR(vectors=[[0.1]])
            >>> bad_resp.validate_against_request(req)  # Raises ValueError
        """
        if len(self.vectors) != len(request.texts):
            raise ValueError(
                f"response has {len(self.vectors)} vectors "
                f"but request has {len(request.texts)} texts"
            )
