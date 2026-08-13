# Phase 10.3 Public Reproducibility Report

Phase 10.3 migrates the public reproducibility examples onto the generic
Phase 10.1/10.2 public API surface.

## CX-01

CX-01 is now explicitly configured as an individual workflow:

- `workflow.campaign_type: individual`;
- `workflow.scientific_execution: [generate, analyze]`;
- `workflow.postprocessing: [ranking]`.

The example still prepares CX knock-in candidate records from documented
campaign/profile data, then delegates Candidate/StagedPackage persistence,
analysis, and ranking to `WorkflowRunner`. It no longer requests `evolve` and
does not produce an EvolutionRun.

The `materialized_smoke` profile demonstrates analyzer-owned PennyLane
materialization with explicit expensive-metric and QNode permissions using tiny
expressibility/trainability sample counts.

## MIXT-5G

MIXT-5G is now explicitly configured as an evolutionary workflow:

- `workflow.campaign_type: evolutionary`;
- `workflow.scientific_execution: [generate, analyze, evolve]`;
- configured mutation schedule converted into generic `evolver.mutation_policy`;
- public `InsertGateMutationFactory`;
- one `WorkflowRunner` invocation creates a coherent EvolutionRun.

The previous example-local generation loop and hand-built combined EvolutionRun
were removed. The remaining wrapper only builds the initial Sanz19 population,
adapts profile edges/schedule into generic mutation-policy recipe parameters,
and writes a small example comparison summary.

Smoke candidate IDs and deterministic G1/G2 structural hashes are preserved.
Resume uses the same public workflow path with `scientific_execution: [evolve]`
and no postprocessing, so historical generations are loaded from the persisted
EvolutionRun and only the next generation is analyzed.

## Public Surface

Normal workflow execution can use public imports:

- `verfeinert.workflow.WorkflowConfig`;
- `verfeinert.workflow.WorkflowRunner`;
- `verfeinert.workflow.run_workflow`;
- `verfeinert.ansatz_generator.InsertGateMutationFactory`;
- `verfeinert.ansatz_evolver.MutationPolicy`;
- `verfeinert.ansatz_evolver.MutationRecipe`;

The optional CLI entry point `verfeinert run config.yaml` loads the same YAML
mapping, applies an optional output-root override, and delegates directly to
`WorkflowConfig` and `run_workflow`.

## Boundaries

No framework core logic branches on CX-01, MIXT-5G, historical campaign names,
or third-campaign names. Notebooks and visualization reference data remain
non-runtime material. Phase 10.4 comparison and visualization work was not
started.
