# Scientific Dependencies Report

Phase 8.0.1 resolves the dependency policy for core scientific metrics.

## Decision

Verfeinertv2 is a scientific research framework. Scientific correctness and v1 methodology alignment take priority over keeping analyzer metrics dependency-light.

## Runtime Dependencies

The base runtime dependencies now include:

- `numpy`
- `pennylane`

These are required because:

- expressibility uses NumPy RNG and histogram behavior from v1;
- trainability uses PennyLane autodiff through `qml.grad`;
- trainability parameter samples use PennyLane NumPy arrays with `requires_grad=True`.

## Optional Dependencies

- `joblib` remains optional for future parallel execution support.
- `matplotlib` remains in the visualization extra.
- `pandas` is dev/test-only for v1 reference fixture comparison and is not part of the v2 public metric API.

## Boundary Policy

`numpy` and `pennylane` are allowed in analyzer metric modules. They remain forbidden in `core`, `ansatz_generator`, `ansatz_evolver`, workflow orchestration, notebooks-as-dependencies, and package boundary code.
