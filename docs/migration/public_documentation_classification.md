# Public Documentation Classification

## Summary

Phase 9.5.1 classifies the `Verfeinertv2/docs/` tree for the future public
`verfeinert` repository.

Classification key:

- **A - Publish:** permanent value for external researchers or contributors.
- **B - Manual review:** potentially useful, but contains migration, TFG,
  thesis, temporary tooling, or release-preparation context that needs human
  review before publication.
- **C - Exclude:** temporary implementation history, checkpoint reports, or
  placeholder/debugging material that should not be part of the first public
  repository unless humans explicitly want a full provenance archive.

The table includes all documentation files present before Phase 9.5 plus the
new Phase 9.5 reports created by this review phase.

## Architecture And User Documentation

| Path | Class | Recommendation | Reasoning |
| --- | --- | --- | --- |
| `docs/README.md` | B | Rewrite or expand before publish. | Useful landing page location, but still skeletal. |
| `docs/architecture/README.md` | B | Rewrite before publish. | Placeholder text; replace with a real architecture index. |
| `docs/architecture/analyzer_collections.md` | A | Publish. | Permanent analyzer collection design. |
| `docs/architecture/analyzer_foundation.md` | A | Publish after wording pass. | Permanent analyzer foundation design; thesis references are boundary rules. |
| `docs/architecture/ansatz_analyzer_design.md` | A | Publish after wording pass. | Target analyzer architecture has external value. |
| `docs/architecture/ansatz_evolver_design.md` | A | Publish after wording pass. | Target evolver architecture has external value. |
| `docs/architecture/ansatz_generator.md` | A | Publish. | Public generator architecture. |
| `docs/architecture/ansatz_generator_exporters.md` | A | Publish after wording pass. | Public exporter contract; update `Verfeinertv2` wording. |
| `docs/architecture/core.md` | A | Publish after wording pass. | Core boundary design is permanent; remove nested-TFG wording. |
| `docs/architecture/data_and_output_policy.md` | A | Publish after wording pass. | Important public data/output policy; remove development-location wording. |
| `docs/architecture/data_model.md` | A | Publish after wording pass. | Canonical JSON data model is public documentation. |
| `docs/architecture/evolution_data_model.md` | A | Publish. | Public EvolutionRun contract documentation. |
| `docs/architecture/evolver_foundation.md` | A | Publish after wording pass. | Foundation behavior and dependency boundaries are useful to contributors. |
| `docs/architecture/execution.md` | A | Publish after wording pass. | Public execution architecture. |
| `docs/architecture/pareto.md` | A | Publish. | Public Pareto engine design. |
| `docs/architecture/ranking.md` | A | Publish. | Public ranking design. |
| `docs/architecture/schemas.md` | A | Publish after wording pass. | Public schema contract documentation. |
| `docs/architecture/visualization.md` | A | Publish after wording pass. | Visualization contract is useful; thesis style references need review. |
| `docs/architecture/visualization_system.md` | A | Publish. | Public visualization system design. |
| `docs/architecture/workflow_runner.md` | A | Publish after wording pass. | Public workflow orchestration design. |
| `docs/development/ci.md` | A | Publish after wording pass. | Useful contributor CI documentation; update root-name wording. |
| `docs/user/README.md` | B | Rewrite before publish. | Placeholder user-doc index. |
| `docs/user/cx01_example.md` | B | Manual review. | Useful older single-analysis example, but reproduction docs supersede it as the first public path. |
| `docs/user/cx01_reproduction.md` | A | Publish after wording pass. | Researcher-facing reproduction workflow. |
| `docs/user/mixt5g_reproduction.md` | A | Publish after wording pass. | Researcher-facing reproduction workflow. |

## Migration And Release Documentation

| Path | Class | Recommendation | Reasoning |
| --- | --- | --- | --- |
| `docs/migration/README.md` | B | Rewrite if migration docs are retained. | Placeholder index with development wording. |
| `docs/migration/analyzer_expressibility_report.md` | C | Exclude. | Temporary Phase 5 implementation report; superseded by metric alignment reports. |
| `docs/migration/analyzer_foundation_report.md` | C | Exclude. | Implementation history rather than lasting user/contributor guidance. |
| `docs/migration/analyzer_phase_5_2_report.md` | C | Exclude. | Phase checkpoint report. |
| `docs/migration/analyzer_phase_5_3_report.md` | C | Exclude. | Phase checkpoint report. |
| `docs/migration/analyzer_phase_5_4_report.md` | C | Exclude. | Phase checkpoint report. |
| `docs/migration/analyzer_trainability_report.md` | C | Exclude. | Temporary Phase 5 implementation report; superseded by metric alignment reports. |
| `docs/migration/analyzer_visualization_report.md` | C | Exclude. | Temporary visualization implementation report. |
| `docs/migration/ansatz_analyzer_audit.md` | B | Manual review. | Useful migration provenance, but contains TFG/thesis-specific audit context. |
| `docs/migration/ansatz_analyzer_implementation_plan.md` | B | Manual review. | Useful historical roadmap; review before publication. |
| `docs/migration/ansatz_evolver_audit.md` | B | Manual review. | Useful migration provenance with TFG/thesis references. |
| `docs/migration/ansatz_evolver_implementation_plan.md` | B | Manual review. | Useful historical roadmap; review before publication. |
| `docs/migration/ansatz_generator_migration_report.md` | B | Manual review. | Captures generator migration choices; contains development context. |
| `docs/migration/ansatz_generator_schema_validation.md` | B | Manual review. | Useful schema-contract provenance. |
| `docs/migration/ci_report.md` | B | Manual review. | Useful release-prep evidence, but implementation-history oriented. |
| `docs/migration/core_foundation_report.md` | C | Exclude. | Temporary implementation report. |
| `docs/migration/cx01_reproduction_report.md` | B | Manual review. | Useful example reproduction provenance. |
| `docs/migration/evolution_schema_refinement_report.md` | B | Manual review. | Schema evolution provenance may help future maintainers. |
| `docs/migration/evolver_checkpoint_b_report.md` | C | Exclude. | Checkpoint status report. |
| `docs/migration/evolver_phase_6_2_report.md` | C | Exclude. | Phase implementation report. |
| `docs/migration/evolver_phase_6_3_report.md` | C | Exclude. | Phase implementation report. |
| `docs/migration/evolver_phase_6_4_report.md` | C | Exclude. | Phase implementation report. |
| `docs/migration/evolver_phase_6_5_report.md` | C | Exclude. | Phase implementation report. |
| `docs/migration/evolver_phase_6_6_report.md` | C | Exclude. | Phase implementation report. |
| `docs/migration/evolver_phase_6_7_report.md` | C | Exclude. | Phase implementation report. |
| `docs/migration/evolver_phase_6_8_report.md` | C | Exclude. | Phase implementation report. |
| `docs/migration/evolver_phase_6_9_report.md` | C | Exclude. | Phase implementation report. |
| `docs/migration/expressibility_alignment_report.md` | B | Manual review. | Important scientific-method alignment provenance. |
| `docs/migration/external_security_scan_report.md` | B | Manual review. | Useful release audit evidence; contains temporary scanner paths. |
| `docs/migration/external_validation_report.md` | B | Manual review. | Useful install-validation evidence; contains temporary environment details. |
| `docs/migration/metrics_expressibility_audit.md` | B | Manual review. | Important scientific audit provenance. |
| `docs/migration/metrics_trainability_audit.md` | B | Manual review. | Important scientific audit provenance. |
| `docs/migration/mixt5g_reproduction_report.md` | B | Manual review. | Useful example reproduction provenance. |
| `docs/migration/package_hardening_report.md` | B | Manual review. | Useful packaging provenance; contains temporary command details. |
| `docs/migration/phase7_report.md` | C | Exclude. | Broad implementation history. |
| `docs/migration/phase8_final_report.md` | B | Manual review. | Release-readiness provenance; review wording before publication. |
| `docs/migration/phase8_metrics_validation_report.md` | B | Manual review. | Scientific validation provenance. |
| `docs/migration/phase9_final_report.md` | B | Manual review. | Release-preparation provenance. |
| `docs/migration/privacy_security_audit.md` | B | Manual review. | Useful public-release audit evidence. |
| `docs/migration/public_repository_preparation_report.md` | B | Manual review. | Release-preparation provenance. |
| `docs/migration/release_metadata_report.md` | B | Manual review. | Release metadata decision record. |
| `docs/migration/release_readiness_report.md` | B | Manual review. | Release-readiness evidence. |
| `docs/migration/repository_extraction_audit.md` | B | Manual review. | Extraction decision record. |
| `docs/migration/scientific_dependencies_report.md` | B | Manual review. | Scientific dependency rationale. |
| `docs/migration/trainability_alignment_report.md` | B | Manual review. | Important scientific-method alignment provenance. |
| `docs/migration/workflow_runner_report.md` | C | Exclude. | Implementation report superseded by architecture docs. |
| `docs/migration/workflow_validation_report.md` | B | Manual review. | Useful end-to-end validation provenance. |
| `docs/migration/public_documentation_classification.md` | B | Manual review. | Phase 9.5 release-prep decision record. |
| `docs/migration/final_repository_tree.md` | B | Manual review. | Phase 9.5 release-prep decision record. |
| `docs/migration/internal_reference_audit.md` | B | Manual review. | Phase 9.5 release-prep audit record. |
| `docs/migration/release_extraction_checklist.md` | B | Manual review. | Pre-extraction checklist for humans. |
| `docs/migration/final_public_review_report.md` | B | Manual review. | Final Phase 9.5 summary. |

## Summary Counts

- **A - Publish:** 22 files.
- **B - Manual review:** 34 files.
- **C - Exclude:** 21 files.

## Recommendation

For the first public repository, publish the A documentation after a light
standalone-name wording pass. Keep B documentation out of the default public
docs set until human review decides which provenance records should ship. Do
not publish C documentation in the first public repository unless a deliberate
full-history archive is desired.
