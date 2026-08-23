"""Representative v0.3.2 public API compatibility checks for v0.4.0."""

from __future__ import annotations

from pathlib import Path

from verfeinert.ansatz_analyzer import (
    AnalysisPipeline,
    AnalyzerConfig,
    StructuralCostConfig,
    validate_analysis_result_document,
)
from verfeinert.ansatz_analyzer.visualization import ObjectivePoint, ObjectiveSeries
from verfeinert.ansatz_evolver import CandidateRef, EvolutionRunState
from verfeinert.ansatz_generator import (
    build_sanz19_candidate_record,
    export_candidate_json,
)
from verfeinert.workflow import WorkflowConfig, WorkflowRunner


STRUCTURAL_BOUNDS = {
    "parameter_count": {"min": 0, "max": 8},
    "depth": {"min": 0, "max": 20},
    "two_qubit_operation_count": {"min": 0, "max": 6},
}


def test_generator_candidate_export_usage_remains_valid() -> None:
    record = build_sanz19_candidate_record("A02", 1, n_qubits=4)

    candidate = export_candidate_json(
        record,
        config=None,
        candidate_id="compat-a02-l1",
    )

    assert candidate["candidate_id"] == "compat-a02-l1"
    assert candidate["schema_version"] == "verfeinert.candidate.v1"
    assert candidate["identity"]["structural_hash"]


def test_analyzer_structural_pipeline_usage_remains_valid(tmp_path: Path) -> None:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    candidate = export_candidate_json(
        build_sanz19_candidate_record("A02", 1, n_qubits=4),
        candidate_id="compat-analysis-candidate",
    )
    config = AnalyzerConfig(
        run_id="compat-analysis",
        input_roots=(input_root,),
        output_root=tmp_path / "analysis-output",
        selected_metrics=("structural_cost",),
        structural_cost=StructuralCostConfig(reference_bounds=STRUCTURAL_BOUNDS),
    )

    records = AnalysisPipeline(config).run(candidate)

    assert len(records) == 1
    document = validate_analysis_result_document(records[0].to_dict())
    assert document["analysis_result_id"] == (
        "analysis-compat-analysis-compat-analysis-candidate"
    )
    assert document["cost"]["structural_cost"] is not None


def test_evolver_reference_state_usage_remains_valid() -> None:
    candidate = export_candidate_json(
        build_sanz19_candidate_record("A02", 1, n_qubits=4),
        candidate_id="compat-evolver-candidate",
    )

    ref = CandidateRef(
        candidate["candidate_id"],
        None,
        candidate["identity"]["structural_hash"],
        candidate["identity"]["lineage_hash"],
    )
    state = EvolutionRunState(
        "compat-evolution",
        "running",
        {"random_seed": 17, "execution": {"mode": "sequential"}},
        (),
    )

    assert ref.candidate_id == "compat-evolver-candidate"
    assert ref.structural_hash == candidate["identity"]["structural_hash"]
    assert state.evolution_run_id == "compat-evolution"
    assert state.generations == ()


def test_workflow_legacy_minimal_mapping_usage_remains_valid(tmp_path: Path) -> None:
    config = WorkflowConfig.from_mapping(
        {
            "run_id": "compat-workflow",
            "output_root": str(tmp_path / "workflow-output"),
            "workflow": {"campaign_type": "individual"},
            "generation": {
                "template_ids": ["A02"],
                "layers": [1],
                "n_qubits": 4,
                "candidate_id_prefix": "compatwf",
            },
            "analyzer": {
                "selected_metrics": ["structural_cost"],
                "structural_cost": {"reference_bounds": STRUCTURAL_BOUNDS},
            },
        },
    )

    result = WorkflowRunner(config).run()

    assert result.executed_operations == ("generate", "analyze")
    assert result.candidate_ids == ("compatwf-a02-l1",)
    assert result.evolution_run_path is None


def test_visualization_model_constructor_usage_remains_valid() -> None:
    point = ObjectivePoint("compat-point", 0.1, 1.0)
    series = ObjectiveSeries(
        (point,),
        "series",
        "legacy label",
        0.2,
        3,
        "source-a",
    )

    assert series.points == (point,)
    assert series.role == "series"
    assert series.label == "legacy label"
    assert series.threshold == 0.2
    assert series.generation == 3
    assert series.source_id == "source-a"
    assert series.score is None
