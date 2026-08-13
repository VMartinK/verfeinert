# Architecture Documentation

These documents define the public architecture of Verfeinert. JSON is the
canonical exchange format between modules; tables, plots, and notebooks are
derived interfaces over those records.

## Core And Data

- `core.md`: lightweight shared primitives and dependency boundaries.
- `data_model.md`: canonical Candidate, AnalysisResult, EvolutionRun, and
  experiment concepts.
- `schemas.md`: schema versioning and JSON Schema contracts.
- `data_and_output_policy.md`: source/input/output separation.
- `execution.md`: local execution policy and executor behavior.

## Scientific Modules

- `ansatz_generator.md`: generator responsibilities and candidate records.
- `ansatz_generator_exporters.md`: canonical Candidate and StagedPackage
  export.
- `ansatz_analyzer_design.md`: analyzer architecture.
- `analyzer_foundation.md`: structural-cost analysis foundation.
- `analyzer_collections.md`, `pareto.md`, `ranking.md`, and `comparison.md`:
  derived analytical collections, policies, and global comparison contracts.
- `ansatz_evolver_design.md`, `evolver_foundation.md`, and
  `evolution_data_model.md`: reference-based evolution design.

## Workflows And Presentation

- `workflow_runner.md`: public orchestration layer.
- `visualization.md` and `visualization_system.md`: plotting boundaries,
  centralized style, and export policy.
