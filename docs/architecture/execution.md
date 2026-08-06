# Execution Architecture

Verfeinert centralizes execution policy in `verfeinert.core.execution`.
Scientific modules should request an executor from core and call its ordered
`map(function, items)` interface instead of creating multiprocessing pools
directly.

## Current Modes

The initial supported modes are:

- `sequential`: executes candidate work in the current process with
  `worker_count=1` and `parallelize_candidates=false`;
- `multiprocessing`: executes candidate work through a process pool owned by
  core with `parallelize_candidates=true` and an explicit `worker_count`.

Both modes preserve input order in their returned result list. Neither mode
executes QNodes, notebooks, campaigns, or plotting by itself.

## Configuration Contract

Execution is configured through `ExecutionConfig`:

```python
ExecutionConfig(
    mode="multiprocessing",
    parallelize_candidates=True,
    worker_count=2,
    scope="candidate",
)
```

Only `scope="candidate"` is implemented now. Metric-level, generation-level,
campaign-level, joblib, Dask, MPI, and HPC execution are future extension
points and are not advertised as available runtime backends.

## Scientific Module Boundary

Future scientific modules should accept an executor or an execution config at
their public boundary. Internals should express independent candidate work as a
plain function plus iterable input, leaving process ownership to core. This
keeps algorithms testable in sequential mode and allows execution backends to
evolve without rewriting scientific logic.

## Failure Expectations

Validation failures are raised before executor construction when the requested
configuration is inconsistent, such as sequential mode with candidate
parallelization enabled. Worker failures propagate from the executor call; core
does not retry or reinterpret scientific exceptions.
