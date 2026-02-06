from __future__ import annotations

from typing import Sequence

import numpy as np


def l2_normalize(matrix: np.ndarray) -> np.ndarray:
    """L2-normalize each row of a 2D matrix, preserving zero vectors."""
    if matrix.ndim != 2:
        raise ValueError("vectors must be a 2D matrix")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    non_zero = norms.squeeze(axis=1) > 0.0
    matrix = matrix.copy()
    matrix[non_zero] = matrix[non_zero] / norms[non_zero]
    return matrix


def is_l2_normalized(matrix: np.ndarray, *, tolerance: float = 1e-3) -> bool:
    """Return True when all non-zero rows have unit L2 norm within tolerance."""
    if matrix.ndim != 2:
        raise ValueError("vectors must be a 2D matrix")
    norms = np.linalg.norm(matrix, axis=1)
    non_zero = norms > 0.0
    if not np.any(non_zero):
        return True
    return bool(np.all(np.abs(norms[non_zero] - 1.0) <= tolerance))


def prepare_embedding_matrix(
    vectors: Sequence[Sequence[float]],
    *,
    expected_dim: int | None = None,
    normalize: bool = False,
    fail_on_non_finite: bool = True,
) -> tuple[np.ndarray, int]:
    """Validate and optionally normalize vectors into a float32 embedding matrix."""
    if not vectors:
        dim = int(expected_dim or 0)
        return np.zeros((0, dim), dtype=np.float32), dim

    dim = len(vectors[0])
    if expected_dim is not None and dim != expected_dim:
        raise ValueError("response vector does not match expected dims")

    for row in vectors:
        if len(row) != dim:
            raise ValueError("inconsistent vector dimensions")
        if expected_dim is not None and len(row) != expected_dim:
            raise ValueError("vector length does not line up with config dims")

    matrix = np.asarray(vectors, dtype=np.float32)
    if matrix.ndim != 2:
        raise ValueError("vectors must be a 2D matrix")
    if expected_dim is not None and matrix.shape[1] != expected_dim:
        raise ValueError("final embedding matrix geometry mismatch")

    if fail_on_non_finite and not np.all(np.isfinite(matrix)):
        raise ValueError("embedding vectors contain NaN or Inf values")

    if normalize:
        matrix = l2_normalize(matrix)
    return matrix, dim
