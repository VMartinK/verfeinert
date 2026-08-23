"""Regression tests for deterministic evolutionary candidate ID uniqueness."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from verfeinert.ansatz_generator import (
    CanonicalMutationFactory,
    InsertGateMutationFactory,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_EXAMPLE = PROJECT_ROOT / "tests" / "fixtures" / "schemas" / "candidate_example.json"
CREATED_AT = "2026-08-06T00:00:00Z"
LEGACY_EXPLICIT_TEMPLATE = "{root_candidate_id}_g{generation:03d}-{recipe_id}-v{variant_ordinal:03d}"
SEED_TEMPLATE = "{root_candidate_id}_g{generation:03d}-seed-p{parent_ordinal:03d}"


def _root_candidate() -> dict:
    return json.loads(CANDIDATE_EXAMPLE.read_text(encoding="utf-8"))


def _request(
    *,
    parent_candidate_id: str,
    root_candidate_id: str,
    generation: int,
    recipe_id: str,
    parent_index: int,
    candidate_id_template: str | None = None,
) -> dict:
    parameters = {
        "gate": "cz",
        "edge": [0, 1],
        "insertion_strategy": "append",
    }
    if candidate_id_template is not None:
        parameters["candidate_id_template"] = candidate_id_template
    return {
        "request_id": f"candidate-id-g{generation}-{recipe_id}-p{parent_index + 1}",
        "parent_candidate_id": parent_candidate_id,
        "root_candidate_id": root_candidate_id,
        "generation_index": generation,
        "mutation_type": "insert",
        "policy_id": "candidate-id-uniqueness",
        "recipe_id": recipe_id,
        "variant_index": 0,
        "parameters": parameters,
        "metadata": {"parent_index": parent_index},
    }


def _seed_two_parents(factory):
    root = _root_candidate()
    root_id = root["candidate_id"]
    parent_a = factory(
        _request(
            parent_candidate_id=root_id,
            root_candidate_id=root_id,
            generation=1,
            recipe_id="seed",
            parent_index=0,
            candidate_id_template=SEED_TEMPLATE,
        ),
        root,
    )
    parent_b = factory(
        _request(
            parent_candidate_id=root_id,
            root_candidate_id=root_id,
            generation=1,
            recipe_id="seed",
            parent_index=1,
            candidate_id_template=SEED_TEMPLATE,
        ),
        root,
    )
    return root_id, parent_a, parent_b


class CandidateIdUniquenessTests(unittest.TestCase):
    def test_default_child_ids_are_unique_across_parents_sharing_root(self) -> None:
        for factory_type in (InsertGateMutationFactory, CanonicalMutationFactory):
            with self.subTest(factory=factory_type.__name__):
                factory = factory_type(created_at=CREATED_AT)
                root_id, parent_a, parent_b = _seed_two_parents(factory)
                child_a = factory(
                    _request(
                        parent_candidate_id=parent_a["candidate_id"],
                        root_candidate_id=root_id,
                        generation=2,
                        recipe_id="next",
                        parent_index=0,
                    ),
                    parent_a,
                )
                child_b = factory(
                    _request(
                        parent_candidate_id=parent_b["candidate_id"],
                        root_candidate_id=root_id,
                        generation=2,
                        recipe_id="next",
                        parent_index=1,
                    ),
                    parent_b,
                )
                self.assertNotEqual(
                    child_a["candidate_id"],
                    child_b["candidate_id"],
                    msg="default candidate IDs collided across parents",
                )
                self.assertEqual(child_a["candidate_id"], f"{root_id}_g002-next-p001-v001")
                self.assertEqual(child_b["candidate_id"], f"{root_id}_g002-next-p002-v001")

    def test_explicit_legacy_template_remains_caller_owned_and_supported(self) -> None:
        for factory_type in (InsertGateMutationFactory, CanonicalMutationFactory):
            with self.subTest(factory=factory_type.__name__):
                factory = factory_type(created_at=CREATED_AT)
                root_id, parent_a, _ = _seed_two_parents(factory)
                child = factory(
                    _request(
                        parent_candidate_id=parent_a["candidate_id"],
                        root_candidate_id=root_id,
                        generation=2,
                        recipe_id="next",
                        parent_index=0,
                        candidate_id_template=LEGACY_EXPLICIT_TEMPLATE,
                    ),
                    parent_a,
                )
                self.assertEqual(child["candidate_id"], f"{root_id}_g002-next-v001")


if __name__ == "__main__":
    unittest.main()
