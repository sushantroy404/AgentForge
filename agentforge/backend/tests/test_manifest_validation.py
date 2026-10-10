import pytest
from pydantic import ValidationError

from app.models.manifest import EvalTestCase, EvaluationSuite, GuardrailsSpec, MissionSpec, PatchOp, PersonaSpec


def case(i, cat):
    return EvalTestCase(id=f"t{i}", category=cat, kind="rag", prompt="a valid prompt", expect_refusal=cat != "in_scope")


def test_suite_requires_3_1_1():
    ok = [case(1, "in_scope"), case(2, "in_scope"), case(3, "in_scope"), case(4, "out_of_scope"), case(5, "prompt_injection")]
    assert len(EvaluationSuite(test_cases=ok).test_cases) == 5
    bad = [case(i, "in_scope") for i in range(5)]
    with pytest.raises(ValidationError):
        EvaluationSuite(test_cases=bad)
    with pytest.raises(ValidationError):
        EvaluationSuite(test_cases=ok[:4])


def test_required_lists_not_empty():
    with pytest.raises(ValidationError):
        MissionSpec(primary_goal="Help customers with orders", in_scope_topics=[], out_of_scope_topics=["x"])
    with pytest.raises(ValidationError):
        GuardrailsSpec(never_do_rules=[])
    with pytest.raises(ValidationError):
        PersonaSpec(tone=["a", "b", "c", "d", "e", "f"], greeting_message="Hello there")


def test_patch_op_shape():
    assert PatchOp(op="add", path="persona.tone", value=["warm"]).op == "add"
    with pytest.raises(ValidationError):
        PatchOp(op="delete", path="x", value="y")
