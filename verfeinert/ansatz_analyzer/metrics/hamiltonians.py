"""Parametrized benchmark Hamiltonians for trainability and VQE evaluation.

The module implements the three cost-function families used in the reference
manuscript (Sanz et al., *Efficiently Architecting VQAs*):

* ``local_x``      -- H = h * sum_i X_i                     (J = 0 limit of TFIM)
* ``tfim``         -- H = -J sum_i Z_i Z_{i+1} - h sum_i X_i (transverse-field Ising)
* ``heisenberg``   -- H = sum_i (Jx X_i X_{i+1} + Jy Y_i Y_{i+1} + Jz Z_i Z_{i+1})
                        + h sum_i Z_i                        (isotropic when Jx=Jy=Jz)

Every family is defined for an arbitrary number of qubits ``n`` and exposes
the same representations: a list of Pauli-string terms, a PennyLane
observable, a SciPy sparse matrix, an optional dense matrix (guarded by a
size limit), and the exact ground-state energy obtained by diagonalization.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from verfeinert.core.io.serialization import to_json_safe


HAMILTONIAN_KINDS = ("local_x", "tfim", "heisenberg")
BOUNDARY_CONDITIONS = ("open", "periodic")
HAMILTONIAN_ALIASES = {
    "local_x": "local_x",
    "localx": "local_x",
    "local-x": "local_x",
    "sum_x": "local_x",
    "x": "local_x",
    "tfim": "tfim",
    "ising": "tfim",
    "transverse_field_ising": "tfim",
    "transverse-field-ising": "tfim",
    "heisenberg": "heisenberg",
    "heis": "heisenberg",
    "xxx": "heisenberg",
    "xyz": "heisenberg",
}
DEFAULT_HAMILTONIAN_PARAMETERS: dict[str, dict[str, float]] = {
    "local_x": {"h": 1.0},
    "tfim": {"J": 1.0, "h": 1.0},
    "heisenberg": {"Jx": 1.0, "Jy": 1.0, "Jz": 1.0, "h": 0.0},
}
HAMILTONIAN_PARAMETER_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "local_x": {"h": "Transverse-field strength multiplying every X_i term."},
    "tfim": {
        "J": "Nearest-neighbour Ising coupling of the Z_i Z_{i+1} terms.",
        "h": "Transverse-field strength of the X_i terms.",
    },
    "heisenberg": {
        "Jx": "Coupling of the X_i X_{i+1} terms.",
        "Jy": "Coupling of the Y_i Y_{i+1} terms.",
        "Jz": "Coupling of the Z_i Z_{i+1} terms.",
        "h": "Optional longitudinal field on every Z_i term (0 for the isotropic model).",
    },
}
HAMILTONIAN_LABELS = {
    "local_x": "Local-X",
    "tfim": "Transverse-field Ising (TFIM)",
    "heisenberg": "Heisenberg",
}
LEGACY_HAMILTONIAN_KINDS = {"local_x": "sum_x", "tfim": "tfim", "heisenberg": "heisenberg"}
MAX_DENSE_QUBITS = 12

_PAULI = {
    "I": np.eye(2, dtype=complex),
    "X": np.array([[0.0, 1.0], [1.0, 0.0]], dtype=complex),
    "Y": np.array([[0.0, -1.0j], [1.0j, 0.0]], dtype=complex),
    "Z": np.array([[1.0, 0.0], [0.0, -1.0]], dtype=complex),
}

PauliTerm = tuple[float, tuple[tuple[int, str], ...]]


class HamiltonianError(ValueError):
    """Raised when a Hamiltonian specification is invalid."""


def normalize_hamiltonian_kind(name: str | None) -> str:
    """Return the canonical Hamiltonian kind for a user-facing name."""
    if name is None:
        return "local_x"
    key = str(name).strip().lower().replace(" ", "_")
    if key not in HAMILTONIAN_ALIASES:
        raise HamiltonianError(
            f"Unsupported hamiltonian {name!r}; expected one of {HAMILTONIAN_KINDS} "
            f"(aliases: {sorted(HAMILTONIAN_ALIASES)})."
        )
    return HAMILTONIAN_ALIASES[key]


@dataclass(frozen=True)
class HamiltonianSpec:
    """A benchmark Hamiltonian family with explicit numeric parameters."""

    kind: str = "local_x"
    parameters: Mapping[str, float] | None = None
    boundary: str = "open"

    def __post_init__(self) -> None:
        kind = normalize_hamiltonian_kind(self.kind)
        object.__setattr__(self, "kind", kind)
        if self.boundary not in BOUNDARY_CONDITIONS:
            raise HamiltonianError(f"boundary must be one of {BOUNDARY_CONDITIONS}.")
        defaults = dict(DEFAULT_HAMILTONIAN_PARAMETERS[kind])
        provided = dict(self.parameters or {})
        unknown = sorted(set(str(key) for key in provided) - set(defaults))
        if unknown:
            raise HamiltonianError(
                f"Unknown parameters {unknown} for hamiltonian {kind!r}; "
                f"supported: {sorted(defaults)}."
            )
        resolved: dict[str, float] = {}
        for key, default in defaults.items():
            value = provided.get(key, default)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise HamiltonianError(f"hamiltonian parameter {key!r} must be numeric.")
            numeric = float(value)
            if not math.isfinite(numeric):
                raise HamiltonianError(f"hamiltonian parameter {key!r} must be finite.")
            resolved[key] = numeric
        object.__setattr__(self, "parameters", resolved)

    # ------------------------------------------------------------------ builders
    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any] | str | None) -> "HamiltonianSpec":
        """Build a spec from ``{"kind": ..., "parameters": {...}}`` or a bare name."""
        if mapping is None:
            return cls()
        if isinstance(mapping, str):
            return cls(kind=mapping)
        if isinstance(mapping, HamiltonianSpec):
            return mapping
        if not isinstance(mapping, Mapping):
            raise HamiltonianError("hamiltonian must be a name or a mapping.")
        data = dict(mapping)
        kind = data.get("kind", data.get("hamiltonian", data.get("name", "local_x")))
        parameters = data.get("parameters", data.get("hamiltonian_parameters"))
        if parameters is None:
            parameters = {
                key: value
                for key, value in data.items()
                if key in DEFAULT_HAMILTONIAN_PARAMETERS[normalize_hamiltonian_kind(kind)]
            }
        return cls(kind=kind, parameters=parameters, boundary=str(data.get("boundary", "open")))

    @classmethod
    def resolve(
        cls,
        *,
        hamiltonian: str | Mapping[str, Any] | None,
        hamiltonian_kind: str | None = None,
        hamiltonian_parameters: Mapping[str, float] | None = None,
        hamiltonian_scale: float | None = None,
        boundary: str = "open",
    ) -> "HamiltonianSpec":
        """Resolve a spec from the legacy and new trainability config fields."""
        if isinstance(hamiltonian, Mapping):
            spec = cls.from_mapping(hamiltonian)
            if hamiltonian_parameters:
                spec = cls(kind=spec.kind, parameters={**spec.parameters, **dict(hamiltonian_parameters)}, boundary=spec.boundary)
            return spec
        kind = normalize_hamiltonian_kind(hamiltonian if hamiltonian is not None else hamiltonian_kind)
        if hamiltonian is not None and hamiltonian_kind is not None:
            if normalize_hamiltonian_kind(hamiltonian_kind) != kind:
                raise HamiltonianError(
                    f"hamiltonian={hamiltonian!r} conflicts with hamiltonian_kind={hamiltonian_kind!r}.",
                )
        parameters = dict(hamiltonian_parameters or {})
        if kind == "local_x" and hamiltonian_scale is not None and "h" not in parameters:
            parameters["h"] = float(hamiltonian_scale)
        return cls(kind=kind, parameters=parameters, boundary=boundary)

    # ------------------------------------------------------------------ metadata
    @property
    def legacy_kind(self) -> str:
        """Return the ``hamiltonian_kind`` token kept for artifact compatibility."""
        return LEGACY_HAMILTONIAN_KINDS[self.kind]

    @property
    def label(self) -> str:
        """Return a human-readable family label."""
        return HAMILTONIAN_LABELS[self.kind]

    def definition(self) -> str:
        """Return a compact textual definition of the Hamiltonian."""
        p = self.parameters
        if self.kind == "local_x":
            if math.isclose(p["h"], 1.0):
                return "H = sum_i X_i"
            return f"H = {p['h']:g} * sum_i X_i"
        if self.kind == "tfim":
            return (
                "H = -J sum_i Z_i Z_{i+1} - h sum_i X_i "
                f"(J={p['J']:g}, h={p['h']:g}, {self.boundary})"
            )
        return (
            "H = sum_i (Jx X_i X_{i+1} + Jy Y_i Y_{i+1} + Jz Z_i Z_{i+1}) + h sum_i Z_i "
            f"(Jx={p['Jx']:g}, Jy={p['Jy']:g}, Jz={p['Jz']:g}, h={p['h']:g}, {self.boundary})"
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe description."""
        return to_json_safe(
            {
                "kind": self.kind,
                "label": self.label,
                "parameters": dict(self.parameters),
                "boundary": self.boundary,
                "definition": self.definition(),
            },
        )

    def metric_metadata(self) -> dict[str, Any]:
        """Return the metadata block written into trainability metric records."""
        scale = self.parameters.get("h", 1.0) if self.kind == "local_x" else 1.0
        return {
            "hamiltonian": self.kind,
            "hamiltonian_kind": self.legacy_kind,
            "hamiltonian_definition": self.definition(),
            "hamiltonian_scale": float(scale),
            "hamiltonian_parameters": dict(self.parameters),
            "hamiltonian_boundary": self.boundary,
            "hamiltonian_label": self.label,
        }

    # ------------------------------------------------------------------ terms
    def _bonds(self, n_qubits: int) -> list[tuple[int, int]]:
        n = int(n_qubits)
        bonds = [(i, i + 1) for i in range(n - 1)]
        if self.boundary == "periodic" and n > 2:
            bonds.append((n - 1, 0))
        return bonds

    def pauli_terms(self, n_qubits: int) -> list[PauliTerm]:
        """Return ``(coefficient, ((wire, 'X'|'Y'|'Z'), ...))`` terms for ``n_qubits``."""
        n = int(n_qubits)
        if n <= 0:
            raise HamiltonianError("n_qubits must be positive.")
        p = self.parameters
        terms: list[PauliTerm] = []
        if self.kind == "local_x":
            if p["h"] != 0.0:
                terms.extend((p["h"], ((i, "X"),)) for i in range(n))
        elif self.kind == "tfim":
            if p["J"] != 0.0:
                terms.extend((-p["J"], ((i, "Z"), (j, "Z"))) for i, j in self._bonds(n))
            if p["h"] != 0.0:
                terms.extend((-p["h"], ((i, "X"),)) for i in range(n))
        else:
            for i, j in self._bonds(n):
                for coupling, pauli in (("Jx", "X"), ("Jy", "Y"), ("Jz", "Z")):
                    if p[coupling] != 0.0:
                        terms.append((p[coupling], ((i, pauli), (j, pauli))))
            if p["h"] != 0.0:
                terms.extend((p["h"], ((i, "Z"),)) for i in range(n))
        return terms

    def term_count(self, n_qubits: int) -> int:
        """Return the number of non-zero Pauli terms."""
        return len(self.pauli_terms(n_qubits))

    # ------------------------------------------------------------------ backends
    def to_pennylane(self, n_qubits: int):
        """Return a PennyLane observable ``qml.Hamiltonian`` for ``n_qubits``."""
        import pennylane as qml

        terms = self.pauli_terms(n_qubits)
        if not terms:
            return qml.Hamiltonian([0.0], [qml.Identity(0)])
        gate = {"X": qml.PauliX, "Y": qml.PauliY, "Z": qml.PauliZ}
        coefficients: list[float] = []
        observables = []
        for coefficient, factors in terms:
            operator = gate[factors[0][1]](factors[0][0])
            for wire, pauli in factors[1:]:
                operator = operator @ gate[pauli](wire)
            coefficients.append(float(coefficient))
            observables.append(operator)
        return qml.Hamiltonian(coefficients, observables)

    def to_sparse(self, n_qubits: int):
        """Return a SciPy CSR matrix (2**n x 2**n) for ``n_qubits``."""
        from scipy import sparse

        n = int(n_qubits)
        dimension = 2**n
        matrix = sparse.csr_matrix((dimension, dimension), dtype=complex)
        for coefficient, factors in self.pauli_terms(n):
            paulis = {wire: pauli for wire, pauli in factors}
            term = sparse.identity(1, dtype=complex, format="csr")
            for wire in range(n):
                term = sparse.kron(term, sparse.csr_matrix(_PAULI[paulis.get(wire, "I")]), format="csr")
            matrix = matrix + coefficient * term
        return matrix.tocsr()

    def to_dense(self, n_qubits: int, *, max_qubits: int = MAX_DENSE_QUBITS) -> np.ndarray:
        """Return the dense complex matrix, guarded by ``max_qubits``."""
        n = int(n_qubits)
        if n > int(max_qubits):
            raise HamiltonianError(
                f"dense Hamiltonian for n_qubits={n} exceeds max_qubits={max_qubits}; "
                "use to_sparse() or a PennyLane observable instead.",
            )
        if n <= 6:
            dimension = 2**n
            matrix = np.zeros((dimension, dimension), dtype=complex)
            for coefficient, factors in self.pauli_terms(n):
                paulis = {wire: pauli for wire, pauli in factors}
                term = np.array([[1.0]], dtype=complex)
                for wire in range(n):
                    term = np.kron(term, _PAULI[paulis.get(wire, "I")])
                matrix += coefficient * term
            return matrix
        return np.asarray(self.to_sparse(n).todense(), dtype=complex)

    def expectation(self, state: Sequence[complex], n_qubits: int | None = None) -> float:
        """Return ``<psi|H|psi>`` for a normalized state vector (NumPy, no autodiff)."""
        vector = np.asarray(state, dtype=complex).reshape(-1)
        n = int(n_qubits) if n_qubits is not None else int(round(math.log2(vector.size)))
        if 2**n != vector.size:
            raise HamiltonianError("state dimension is not a power of two matching n_qubits.")
        norm = np.linalg.norm(vector)
        if not np.isfinite(norm) or norm <= 0.0:
            raise HamiltonianError(f"Invalid state norm: {norm}")
        vector = vector / norm
        if n <= MAX_DENSE_QUBITS:
            matrix = self.to_dense(n)
            return float(np.real(np.vdot(vector, matrix @ vector)))
        matrix = self.to_sparse(n)
        return float(np.real(np.vdot(vector, matrix @ vector)))

    def ground_state(self, n_qubits: int) -> tuple[float, np.ndarray]:
        """Return the exact ground-state energy and eigenvector."""
        n = int(n_qubits)
        if n <= 10:
            matrix = self.to_dense(n)
            energies, vectors = np.linalg.eigh(matrix)
            return float(energies[0]), np.asarray(vectors[:, 0], dtype=complex)
        from scipy.sparse.linalg import eigsh

        matrix = self.to_sparse(n)
        energies, vectors = eigsh(matrix, k=1, which="SA")
        return float(np.real(energies[0])), np.asarray(vectors[:, 0], dtype=complex)

    def ground_state_energy(self, n_qubits: int) -> float:
        """Return the exact ground-state energy for ``n_qubits``."""
        return self.ground_state(n_qubits)[0]


def hamiltonian_catalog() -> list[dict[str, Any]]:
    """Return a JSON-safe catalog describing every Hamiltonian family."""
    catalog = []
    for kind in HAMILTONIAN_KINDS:
        spec = HamiltonianSpec(kind=kind)
        catalog.append(
            {
                "kind": kind,
                "label": HAMILTONIAN_LABELS[kind],
                "definition": spec.definition(),
                "parameters": [
                    {
                        "name": name,
                        "default": default,
                        "description": HAMILTONIAN_PARAMETER_DESCRIPTIONS[kind][name],
                    }
                    for name, default in DEFAULT_HAMILTONIAN_PARAMETERS[kind].items()
                ],
                "boundaries": list(BOUNDARY_CONDITIONS),
                "aliases": sorted(alias for alias, target in HAMILTONIAN_ALIASES.items() if target == kind),
            },
        )
    return catalog


__all__ = [
    "BOUNDARY_CONDITIONS",
    "DEFAULT_HAMILTONIAN_PARAMETERS",
    "HAMILTONIAN_ALIASES",
    "HAMILTONIAN_KINDS",
    "HAMILTONIAN_LABELS",
    "HamiltonianError",
    "HamiltonianSpec",
    "MAX_DENSE_QUBITS",
    "hamiltonian_catalog",
    "normalize_hamiltonian_kind",
]
