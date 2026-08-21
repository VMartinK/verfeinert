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

Analyzer candidate analysis consumes `ExecutionConfig` directly. Sequential
execution remains the default. When `execution.mode="multiprocessing"` is
configured with `parallelize_candidates=true`, `AnalysisPipeline` maps
candidate-level analysis work through `verfeinert.core.execution`, restores
results to canonical input order, and records the configured execution mode and
worker count in AnalysisResult provenance.

Multiprocessing is fail-closed. Pickling failures, worker startup/execution
failures, and unsupported worker payloads raise explicit execution errors and
are not retried sequentially. Explicit metric callables supplied by callers
remain the highest-priority state-callable source, but they must be picklable
when multiprocessing is requested.

Metric RNG policy must be deterministic per candidate under multiprocessing.
Analyzer configurations that request an expensive metric with
`rng_policy="global_sequential"` and `execution.mode="multiprocessing"` fail
before candidate work starts; use `rng_policy="per_circuit"` or sequential
execution for that metric policy.

Workflow analysis stages pass the workflow `ExecutionConfig` into the analyzer,
including analysis of generated/evolutionary candidates. Direct
`ansatz_evolver.EvolverConfig` remains sequential-only because the evolver owns
state transitions and selection, not analyzer metric execution.

## Failure Expectations

Core validation failures are raised before executor construction when the
requested primitive configuration is inconsistent, such as sequential mode with
candidate parallelization enabled. Worker failures propagate from the executor
call as `ExecutionError`; core does not retry or reinterpret scientific
exceptions.

Analyzer multiprocessing failures surface as `AnalysisPipelineExecutionError`
with machine-readable reason, execution configuration, and either worker
failure metadata or wrapped executor failure metadata. Workflow callers receive
the analyzer failure rather than partial analysis artifacts.
