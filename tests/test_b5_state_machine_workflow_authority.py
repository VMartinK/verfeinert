"""B5 regression contract: WorkflowRunner must drive EvolutionStateMachine lifecycle."""

from __future__ import annotations

import ast
import importlib.util
import inspect
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest import mock

from verfeinert.ansatz_evolver import EvolutionStateMachine
from verfeinert.workflow import WorkflowConfig, WorkflowRunner
import verfeinert.workflow.runner as runner


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = PROJECT_ROOT / "verfeinert" / "workflow" / "runner.py"


def _function_source(name: str) -> str:
    return inspect.getsource(getattr(runner, name))


def _direct_evolution_state_constructors_by_function() -> set[str]:
    tree = ast.parse(RUNNER_PATH.read_text())
    owners: set[str] = set()

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_Call(self, node: ast.Call) -> None:
            if isinstance(node.func, ast.Name) and node.func.id == "EvolutionRunState":
                owners.add(self.stack[-1] if self.stack else "<module>")
            self.generic_visit(node)

    Visitor().visit(tree)
    return owners


def _load_phase102_module():
    path = PROJECT_ROOT / "tests" / "test_workflow_phase_10_2_artifact_orchestration.py"
    name = "b5_phase102_runtime_contract"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_runner_core_contains_real_generation_lifecycle_transitions() -> None:
    source = inspect.getsource(runner.WorkflowRunner._run_evolution)
    for token in (
        ".plan_generation(",
        ".record_candidates_generated(",
        ".request_analysis(",
        ".record_analysis_complete(",
        ".record_selection_complete(",
        ".append_generation(",
    ):
        assert token in source, f"WorkflowRunner._run_evolution does not drive {token}"


def test_runner_does_not_synthesize_lifecycle_run_states_manually() -> None:
    assert _direct_evolution_state_constructors_by_function() == {
        "_state_from_evolution_document"
    }


def test_state_completion_is_owned_directly_by_state_machine() -> None:
    source = _function_source("_state_completed")
    assert "EvolutionRunState(" not in source
    assert "EvolutionStateMachine.from_run_state(state)" in source
    assert ".complete(metadata=metadata)" in source


def test_compatibility_append_helper_uses_full_canonical_lifecycle() -> None:
    source = _function_source("_state_with_generation")
    assert "EvolutionRunState(" not in source
    assert "_checkpoint_generation_lifecycle(" in source


def test_historical_rebuild_replays_canonical_lifecycle() -> None:
    source = _function_source("_new_evolution_state")
    assert "_checkpoint_generation_lifecycle(" in source


def test_actual_workflow_invokes_state_machine_for_every_generation() -> None:
    module = _load_phase102_module()
    calls: list[str] = []

    method_names = (
        "plan_generation",
        "record_candidates_generated",
        "request_analysis",
        "record_analysis_complete",
        "record_selection_complete",
        "append_generation",
    )
    originals = {name: getattr(EvolutionStateMachine, name) for name in method_names}

    def wrapper(name: str):
        original = originals[name]

        def recorded(self, *args, **kwargs):
            calls.append(name)
            return original(self, *args, **kwargs)

        return recorded

    patches = [
        mock.patch.object(EvolutionStateMachine, name, wrapper(name))
        for name in method_names
    ]

    with TemporaryDirectory() as tmp:
        mapping = module._workflow_mapping(
            Path(tmp) / "out",
            run_id="b5-lifecycle",
            campaign_type="evolutionary",
            scientific_execution=("generate", "analyze", "evolve"),
            max_generations=2,
        )
        factory = module.RecordingFactory()

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            result = WorkflowRunner(WorkflowConfig.from_mapping(mapping)).run(
                candidate_factory=factory
            )

    assert result.evolution_run_path is not None

    expected_cycle = list(method_names)
    assert len(calls) >= 2 * len(expected_cycle)

    cursor = 0
    completed_cycles = 0
    while cursor <= len(calls) - len(expected_cycle):
        if calls[cursor : cursor + len(expected_cycle)] == expected_cycle:
            completed_cycles += 1
            cursor += len(expected_cycle)
        else:
            cursor += 1

    assert completed_cycles >= 2, calls
