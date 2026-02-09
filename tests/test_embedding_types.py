"""Tests for embedding internal representation types."""

import pytest

from cpm_builtin.embeddings.types import EmbedRequestIR, EmbedResponseIR


class TestEmbedRequestIR:
    """Tests for EmbedRequestIR validation and behavior."""

    def test_minimal_request(self) -> None:
        """Test creating a minimal valid request."""
        req = EmbedRequestIR(texts=["hello"])
        assert req.texts == ["hello"]
        assert req.model is None
        assert req.hints == {}
        assert req.extra == {}

    def test_full_request(self) -> None:
        """Test creating a request with all fields."""
        req = EmbedRequestIR(
            texts=["hello", "world"],
            model="jina-v2-base-en",
            hints={"normalize": True, "max_length": 512},
            extra={"custom_param": "value"},
        )
        assert req.texts == ["hello", "world"]
        assert req.model == "jina-v2-base-en"
        assert req.hints == {"normalize": True, "max_length": 512}
        assert req.extra == {"custom_param": "value"}

    def test_empty_texts_raises(self) -> None:
        """Test that empty texts list raises ValueError."""
        with pytest.raises(ValueError, match="texts cannot be empty"):
            EmbedRequestIR(texts=[])

    def test_non_list_texts_raises(self) -> None:
        """Test that non-list texts raises TypeError."""
        with pytest.raises(TypeError, match="texts must be a list"):
            EmbedRequestIR(texts="hello")  # type: ignore[arg-type]

    def test_non_string_text_raises(self) -> None:
        """Test that non-string elements in texts raise TypeError."""
        with pytest.raises(TypeError, match=r"texts\[1\] must be str"):
            EmbedRequestIR(texts=["hello", 123])  # type: ignore[list-item]

    def test_non_string_model_raises(self) -> None:
        """Test that non-string model raises TypeError."""
        with pytest.raises(TypeError, match="model must be str or None"):
            EmbedRequestIR(texts=["test"], model=123)  # type: ignore[arg-type]

    def test_non_dict_hints_raises(self) -> None:
        """Test that non-dict hints raises TypeError."""
        with pytest.raises(TypeError, match="hints must be dict"):
            EmbedRequestIR(texts=["test"], hints="invalid")  # type: ignore[arg-type]

    def test_non_dict_extra_raises(self) -> None:
        """Test that non-dict extra raises TypeError."""
        with pytest.raises(TypeError, match="extra must be dict"):
            EmbedRequestIR(texts=["test"], extra="invalid")  # type: ignore[arg-type]

    def test_with_hints_merges_correctly(self) -> None:
        """Test that with_hints merges hints correctly."""
        req1 = EmbedRequestIR(texts=["test"], hints={"a": 1, "b": 2})
        req2 = req1.with_hints(b=3, c=4)

        # Original unchanged (frozen)
        assert req1.hints == {"a": 1, "b": 2}

        # New request has merged hints
        assert req2.hints == {"a": 1, "b": 3, "c": 4}
        assert req2.texts == req1.texts
        assert req2.model == req1.model
        assert req2.extra == req1.extra

    def test_with_extra_merges_correctly(self) -> None:
        """Test that with_extra merges extra parameters correctly."""
        req1 = EmbedRequestIR(texts=["test"], extra={"x": 10})
        req2 = req1.with_extra(y=20, z=30)

        # Original unchanged
        assert req1.extra == {"x": 10}

        # New request has merged extra
        assert req2.extra == {"x": 10, "y": 20, "z": 30}

    def test_frozen_immutability(self) -> None:
        """Test that EmbedRequestIR is frozen (immutable)."""
        req = EmbedRequestIR(texts=["test"])
        with pytest.raises(Exception):  # FrozenInstanceError in Python 3.10+
            req.texts = ["modified"]  # type: ignore[misc]


class TestEmbedResponseIR:
    """Tests for EmbedResponseIR validation and behavior."""

    def test_minimal_response(self) -> None:
        """Test creating a minimal valid response."""
        resp = EmbedResponseIR(vectors=[[0.1, 0.2, 0.3]])
        assert resp.vectors == [[0.1, 0.2, 0.3]]
        assert resp.model is None
        assert resp.usage is None
        assert resp.extra is None

    def test_full_response(self) -> None:
        """Test creating a response with all fields."""
        resp = EmbedResponseIR(
            vectors=[[0.1, 0.2], [0.3, 0.4]],
            model="jina-v2-base-en",
            usage={"prompt_tokens": 10, "total_tokens": 10},
            extra={"provider": "custom"},
        )
        assert resp.vectors == [[0.1, 0.2], [0.3, 0.4]]
        assert resp.model == "jina-v2-base-en"
        assert resp.usage == {"prompt_tokens": 10, "total_tokens": 10}
        assert resp.extra == {"provider": "custom"}

    def test_empty_vectors_raises(self) -> None:
        """Test that empty vectors list raises ValueError."""
        with pytest.raises(ValueError, match="vectors cannot be empty"):
            EmbedResponseIR(vectors=[])

    def test_non_list_vectors_raises(self) -> None:
        """Test that non-list vectors raises TypeError."""
        with pytest.raises(TypeError, match="vectors must be a list"):
            EmbedResponseIR(vectors="invalid")  # type: ignore[arg-type]

    def test_non_list_vector_element_raises(self) -> None:
        """Test that non-list vector elements raise TypeError."""
        with pytest.raises(TypeError, match=r"vectors\[0\] must be list"):
            EmbedResponseIR(vectors=["invalid"])  # type: ignore[list-item]

    def test_empty_vector_raises(self) -> None:
        """Test that empty vector raises ValueError."""
        with pytest.raises(ValueError, match=r"vectors\[0\] cannot be empty"):
            EmbedResponseIR(vectors=[[]])

    def test_inconsistent_dimensions_raises(self) -> None:
        """Test that inconsistent vector dimensions raise ValueError."""
        with pytest.raises(ValueError, match="inconsistent dimensions"):
            EmbedResponseIR(vectors=[[0.1, 0.2], [0.3, 0.4, 0.5]])

    def test_non_numeric_element_raises(self) -> None:
        """Test that non-numeric vector elements raise TypeError."""
        with pytest.raises(TypeError, match=r"vectors\[0\]\[1\] must be numeric"):
            EmbedResponseIR(vectors=[[0.1, "invalid"]])  # type: ignore[list-item]

    def test_non_string_model_raises(self) -> None:
        """Test that non-string model raises TypeError."""
        with pytest.raises(TypeError, match="model must be str or None"):
            EmbedResponseIR(vectors=[[0.1]], model=123)  # type: ignore[arg-type]

    def test_non_dict_usage_raises(self) -> None:
        """Test that non-dict usage raises TypeError."""
        with pytest.raises(TypeError, match="usage must be dict or None"):
            EmbedResponseIR(vectors=[[0.1]], usage="invalid")  # type: ignore[arg-type]

    def test_non_dict_extra_raises(self) -> None:
        """Test that non-dict extra raises TypeError."""
        with pytest.raises(TypeError, match="extra must be dict or None"):
            EmbedResponseIR(vectors=[[0.1]], extra="invalid")  # type: ignore[arg-type]

    def test_dims_property(self) -> None:
        """Test the dims property returns correct dimension."""
        resp = EmbedResponseIR(vectors=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
        assert resp.dims == 3

    def test_count_property(self) -> None:
        """Test the count property returns correct vector count."""
        resp = EmbedResponseIR(vectors=[[0.1], [0.2], [0.3]])
        assert resp.count == 3

    def test_validate_against_request_success(self) -> None:
        """Test successful validation against matching request."""
        req = EmbedRequestIR(texts=["hello", "world"])
        resp = EmbedResponseIR(vectors=[[0.1, 0.2], [0.3, 0.4]])
        resp.validate_against_request(req)  # Should not raise

    def test_validate_against_request_mismatch_raises(self) -> None:
        """Test validation raises when response/request counts don't match."""
        req = EmbedRequestIR(texts=["hello", "world"])
        resp = EmbedResponseIR(vectors=[[0.1, 0.2]])

        with pytest.raises(ValueError, match="response has 1 vectors but request has 2 texts"):
            resp.validate_against_request(req)

    def test_accepts_integers_in_vectors(self) -> None:
        """Test that integer values in vectors are accepted."""
        resp = EmbedResponseIR(vectors=[[1, 2, 3], [4, 5, 6]])
        assert resp.vectors == [[1, 2, 3], [4, 5, 6]]
        assert resp.dims == 3

    def test_frozen_immutability(self) -> None:
        """Test that EmbedResponseIR is frozen (immutable)."""
        resp = EmbedResponseIR(vectors=[[0.1]])
        with pytest.raises(Exception):  # FrozenInstanceError in Python 3.10+
            resp.vectors = [[0.2]]  # type: ignore[misc]


class TestRequestResponseIntegration:
    """Integration tests between request and response types."""

    def test_round_trip_single_text(self) -> None:
        """Test request/response round trip with single text."""
        req = EmbedRequestIR(
            texts=["hello world"],
            model="test-model",
            hints={"normalize": True},
        )
        resp = EmbedResponseIR(
            vectors=[[0.1, 0.2, 0.3]],
            model="test-model",
        )
        resp.validate_against_request(req)
        assert resp.count == len(req.texts)

    def test_round_trip_multiple_texts(self) -> None:
        """Test request/response round trip with multiple texts."""
        req = EmbedRequestIR(texts=["a", "b", "c"])
        resp = EmbedResponseIR(vectors=[[0.1], [0.2], [0.3]])
        resp.validate_against_request(req)
        assert resp.count == 3
        assert resp.dims == 1

    def test_hints_modification_workflow(self) -> None:
        """Test workflow of building request with progressive hint additions."""
        req = EmbedRequestIR(texts=["test"])
        req = req.with_hints(normalize=True)
        req = req.with_hints(max_length=512)
        req = req.with_extra(provider_specific="value")

        assert req.hints == {"normalize": True, "max_length": 512}
        assert req.extra == {"provider_specific": "value"}
