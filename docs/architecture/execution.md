# Execution Architecture

Verfeinert centralizes primitive execution policy in
`verfeinert.core.execution`. Core executors expose an ordered
`map(function, items)` interface and own any process-pool construction.

## Current Modes

The core primitive modes are:

- `sequential`: executes candidate work in the current process with
  `worker_count=1` and `parallelize_candidates=false`;
- `multiprocessing`: executes candidate work through a process pool owned by
  core with `parallelize_candidates=true` and an explicit `worker_count`.

Both primitive modes preserve input order in their returned result list.
Neither mode executes QNodes, notebooks, campaigns, or plotting by itself.

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

Only `scope="candidate"` is implemented for the core primitive. Metric-level,
generation-level, campaign-level, joblib, Dask, MPI, and HPC execution are
future extension points and are not advertised as available runtime backends.

## Scientific Module Boundary

In v0.3.x, public analyzer, evolver, and workflow scientific paths support
`execution.mode="sequential"` only. They do not consume
`MultiprocessingExecutor`, and they must not silently accept
`execution.mode="multiprocessing"` while running sequentially.

If multiprocessing is requested for candidate science, analyzer/workflow entry
points fail before scientific work starts. The error explains that core
executor primitives exist, but scientific pipeline integration is deferred to
v0.4.0.

Future scientific modules may accept an executor or execution config at their
public boundary once RNG behavior, PennyLane/QNode execution, pickling,
worker-failure behavior, and deterministic provenance have a tested contract.

## Failure Expectations

Core validation failures are raised before executor construction when the
requested primitive configuration is inconsistent, such as sequential mode with
candidate parallelization enabled. Worker failures propagate from the executor
call; core does not retry or reinterpret scientific exceptions.

Scientific analyzer/evolver/workflow validation also fails closed when a
multiprocessing mode is requested for v0.3.x candidate science.
