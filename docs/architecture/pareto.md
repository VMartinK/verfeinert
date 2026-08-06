# Pareto Engine

## Role

`verfeinert.ansatz_analyzer.pareto` classifies canonical AnalysisResult
collections in an objective space. It is a derived analytical policy, not a
metric executor. It never triggers QNodes, generated callables, notebooks, or
plots.

## Inputs And Outputs

Input is an `AnalysisResultCollection` plus optional reference collection and a
`ParetoConfig`. Objectives are resolved from computed metric records. Output is
a `ParetoResult` containing deterministic candidate ranks, frontier IDs,
dominated IDs, optional cost-threshold frontiers, and canonical
`ClassificationRecord` values.

No new canonical JSON schema is introduced. The durable exchange format remains
the candidate-level `AnalysisResult` document; Pareto outputs are derived
records that can be appended as classifications or exported as traceable
derived artifacts.

## Objective Convention

The default objective convention is:

- `expressibility`: maximize
- `trainability`: maximize

Objective directions are explicit configuration. Missing objective values make
a candidate `unrankable` rather than silently assigning an artificial value.

## Cost Policy

Structural cost is an external constraint for cost-threshold frontiers. It is
not a Pareto objective. This preserves the validated scientific convention from
the previous workflows while avoiding campaign-specific branches.

## Reference Comparison

An optional reference collection can be supplied. The engine computes the
reference frontier and records whether each current candidate is dominated by
or dominates that reference frontier. The reference can represent any caller
chosen baseline; the package does not encode campaign names.

## Dependency Boundary

The Pareto engine is pure Python over canonical analyzer records. It does not
depend on pandas, NumPy, Matplotlib, PennyLane, notebooks, generator internals,
or evolver internals.
