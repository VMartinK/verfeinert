"""Connectivity models for structural ansatz constraints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from verfeinert.core.validation import require_bool, require_positive_int

from .validation import GeneratorValidationError


@dataclass(frozen=True)
class Connectivity:
    """Allowed directed or undirected two-qubit edges."""

    n_qubits: int
    edges: tuple[tuple[int, int], ...] | None = None
    directed: bool = False

    def __post_init__(self) -> None:
        n_qubits = require_positive_int(self.n_qubits, "connectivity.n_qubits")
        directed = require_bool(self.directed, "connectivity.directed")
        normalized_edges = None if self.edges is None else _normalize_edges(self.edges, n_qubits, directed)
        object.__setattr__(self, "n_qubits", n_qubits)
        object.__setattr__(self, "directed", directed)
        object.__setattr__(self, "edges", normalized_edges)

    def allows(self, a: int, b: int) -> bool:
        """Return whether the connectivity permits edge ``(a, b)``."""
        edge = _normalize_edge((a, b), self.n_qubits, self.directed)
        if self.edges is None:
            return True
        return edge in self.edges

    @classmethod
    def all_to_all(cls, n_qubits: int, *, directed: bool = False) -> "Connectivity":
        """Allow every non-self two-qubit edge."""
        return cls(n_qubits=n_qubits, edges=None, directed=directed)

    @classmethod
    def linear(cls, n_qubits: int, *, directed: bool = False) -> "Connectivity":
        """Allow nearest-neighbor line connectivity."""
        return cls(
            n_qubits=n_qubits,
            edges=tuple((wire, wire + 1) for wire in range(n_qubits - 1)),
            directed=directed,
        )

    @classmethod
    def circular(cls, n_qubits: int, *, directed: bool = False) -> "Connectivity":
        """Allow nearest-neighbor ring connectivity."""
        edges = [(wire, wire + 1) for wire in range(n_qubits - 1)]
        if n_qubits > 1:
            edges.append((n_qubits - 1, 0))
        return cls(n_qubits=n_qubits, edges=tuple(edges), directed=directed)


def _normalize_edges(
    edges: Iterable[tuple[int, int]],
    n_qubits: int,
    directed: bool,
) -> tuple[tuple[int, int], ...]:
    return tuple(sorted({_normalize_edge(edge, n_qubits, directed) for edge in edges}))


def _normalize_edge(edge: tuple[int, int], n_qubits: int, directed: bool) -> tuple[int, int]:
    if not isinstance(edge, tuple) or len(edge) != 2:
        raise GeneratorValidationError("connectivity edges must be two-item tuples.")
    a, b = edge
    if type(a) is not int or type(b) is not int:
        raise GeneratorValidationError("connectivity wires must be integers.")
    if a < 0 or b < 0 or a >= n_qubits or b >= n_qubits:
        raise GeneratorValidationError("connectivity wires must be within n_qubits.")
    if a == b:
        raise GeneratorValidationError("connectivity self-edges are not allowed.")
    return (a, b) if directed else tuple(sorted((a, b)))


__all__ = ["Connectivity"]
