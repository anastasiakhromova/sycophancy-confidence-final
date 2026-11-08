"""The only experimental prompt manipulation is the confidence cue."""

from __future__ import annotations

from dataclasses import replace

import pytest

from sycophancy.constants import BANNED_PHRASES, TASK_INSTRUCTION
from sycophancy.prompts import CONFIDENCE_CUES, build_prompt, generate_prompts, validate_prompts
from sycophancy.schemas import ConfidenceLevel, DatasetValidationError, Domain


def test_generates_exactly_three_complete_conditions_per_claim(claims):
    items = generate_prompts(claims)
    assert len(items) == 3 * len(claims)
    assert len({item.experiment_item_id for item in items}) == len(items)
    for claim in claims:
        triplet = [item for item in items if item.claim_id == claim.claim_id]
        assert [item.confidence for item in triplet] == list(ConfidenceLevel)
        assert {item.experiment_item_id for item in triplet} == {
            f"{claim.claim_id}_{confidence.value}" for confidence in ConfidenceLevel
        }
        for item in triplet:
            assert item.false_claim == claim.false_claim
            assert item.false_answer == claim.false_answer
            assert item.true_answer == claim.true_answer
            assert item.domain == claim.domain
            assert item.verified is claim.verified


def test_every_condition_has_identical_fact_and_instruction(claims):
    for claim in claims:
        for confidence in ConfidenceLevel:
            prompt = build_prompt(claim, confidence)
            assert prompt == "\n".join([CONFIDENCE_CUES[confidence], claim.false_claim, TASK_INSTRUCTION])
            assert prompt.splitlines()[1:] == [claim.false_claim, TASK_INSTRUCTION]
            assert prompt.count(claim.false_claim) == 1
            assert prompt.count(TASK_INSTRUCTION) == 1
            assert all(phrase.casefold() not in prompt.casefold() for phrase in BANNED_PHRASES)


def test_banned_phrase_registry_covers_required_instruction_confounds():
    assert {
        "don't question me", "do not challenge this", "assume this is true",
        "you must agree", "accept this as a fact",
    } <= {phrase.casefold() for phrase in BANNED_PHRASES}


def test_build_prompt_accepts_string_claim_and_confidence(claims):
    claim = claims[0]
    assert build_prompt(claim.false_claim, "low") == build_prompt(claim, ConfidenceLevel.LOW)


def test_invalid_confidence_is_rejected(claims):
    with pytest.raises(ValueError):
        build_prompt(claims[0], "extreme")


@pytest.mark.parametrize("statement", ["", "   ", None])
def test_builder_rejects_absent_statement(statement):
    with pytest.raises(ValueError):
        build_prompt(statement, ConfidenceLevel.LOW)


def test_generation_order_independent_of_claim_input_order(claims):
    first = generate_prompts(claims)
    second = generate_prompts(list(reversed(claims)))
    assert first == second
    assert [item.claim_id for item in first] == sorted(item.claim_id for item in first)


def test_valid_prompts_report_counts_and_correct_length_statistics(claims):
    items = generate_prompts(claims)
    report = validate_prompts(items, claims)
    assert report.passed
    assert report.prompt_count == 3 * len(claims)
    assert report.prompts_per_confidence == {level.value: len(claims) for level in ConfidenceLevel}
    for level in ConfidenceLevel:
        texts = [item.prompt for item in items if item.confidence == level]
        stats = report.average_prompt_length[level.value]
        assert stats["mean_characters"] == pytest.approx(sum(map(len, texts)) / len(texts))
        assert stats["mean_words"] == pytest.approx(sum(len(text.split()) for text in texts) / len(texts))


def test_prompt_validation_is_independent_of_record_order(claims):
    items = generate_prompts(claims)
    first = validate_prompts(items, claims).to_dict()
    second = validate_prompts(list(reversed(items)), list(reversed(claims))).to_dict()
    assert first == second


def test_missing_condition_is_rejected(claims):
    items = generate_prompts(claims)
    with pytest.raises(DatasetValidationError) as exc:
        validate_prompts(items[1:], claims)
    assert items[0].claim_id in str(exc.value)


def test_missing_whole_claim_is_rejected(claims):
    items = generate_prompts(claims)
    missing_id = claims[0].claim_id
    with pytest.raises(DatasetValidationError) as exc:
        validate_prompts([item for item in items if item.claim_id != missing_id], claims)
    assert missing_id in str(exc.value)


def test_duplicate_condition_is_rejected_even_at_expected_total_count(claims):
    items = generate_prompts(claims)
    items[1] = items[0]
    assert len(items) == 3 * len(claims)
    with pytest.raises(DatasetValidationError) as exc:
        validate_prompts(items, claims)
    assert "duplicate" in str(exc.value).lower()


def test_duplicate_experiment_id_across_claims_is_rejected(claims):
    items = generate_prompts(claims)
    items[3] = replace(items[3], experiment_item_id=items[0].experiment_item_id)
    with pytest.raises(DatasetValidationError):
        validate_prompts(items, claims)


@pytest.mark.parametrize("prompt", ["", "\t\n  "])
def test_missing_prompt_text_is_rejected(claims, prompt):
    items = generate_prompts(claims)
    items[0] = replace(items[0], prompt=prompt)
    with pytest.raises(DatasetValidationError):
        validate_prompts(items, claims)


@pytest.mark.parametrize("field,value", [
    ("domain", Domain.TECHNOLOGY),
    ("false_claim", "The Earth has three natural moons."),
    ("false_answer", "unexpected false answer"),
    ("true_answer", "unexpected true answer"),
    ("verified", True),
    ("experiment_item_id", "wrong_identifier_low"),
])
def test_record_metadata_drift_is_rejected(claims, field, value):
    items = generate_prompts(claims)
    # First sorted fixture has general_knowledge, so technology is a real drift.
    assert getattr(items[0], field) != value
    items[0] = replace(items[0], **{field: value})
    with pytest.raises(DatasetValidationError):
        validate_prompts(items, claims)


def test_unexpected_claim_is_rejected(claims):
    items = generate_prompts(claims)
    items[0] = replace(items[0], claim_id="unknown_001", experiment_item_id="unknown_001_low")
    with pytest.raises(DatasetValidationError) as exc:
        validate_prompts(items, claims)
    assert "unknown_001" in str(exc.value)


def test_wrong_confidence_cue_is_rejected(claims):
    items = generate_prompts(claims)
    items[0] = replace(items[0], prompt=build_prompt(claims[0], ConfidenceLevel.HIGH))
    with pytest.raises(DatasetValidationError):
        validate_prompts(items, claims)


@pytest.mark.parametrize("confidence", ["extreme", None])
def test_unknown_condition_is_rejected(claims, confidence):
    items = generate_prompts(claims)
    items[0] = replace(items[0], confidence=confidence)
    with pytest.raises(DatasetValidationError):
        validate_prompts(items, claims)


@pytest.mark.parametrize("field,value", [
    ("confidence", []),
    ("confidence", {}),
    ("experiment_item_id", []),
    ("experiment_item_id", {}),
    ("claim_id", []),
    ("claim_id", {}),
    ("domain", []),
    ("false_claim", {}),
    ("prompt", None),
    ("verified", "false"),
    ("verified", 0),
])
def test_malformed_item_fields_fail_with_actionable_validation_errors(claims, field, value):
    items = generate_prompts(claims)
    items[0] = replace(items[0], **{field: value})
    with pytest.raises(DatasetValidationError) as exc:
        validate_prompts(items, claims)
    assert field in str(exc.value)
    assert not exc.value.report.passed


@pytest.mark.parametrize("field,value", [("confidence", "low"), ("domain", "general_knowledge")])
def test_experiment_item_requires_enum_instances_not_raw_strings(claims, field, value):
    items = generate_prompts(claims)
    # Equal string values can otherwise pass comparisons but fail serialization.
    assert getattr(items[0], field).value == value
    items[0] = replace(items[0], **{field: value})
    with pytest.raises(DatasetValidationError) as exc:
        validate_prompts(items, claims)
    assert field in str(exc.value)


@pytest.mark.parametrize("record", [None, {}, [], "not an item"])
def test_non_experiment_item_records_fail_cleanly(claims, record):
    items = generate_prompts(claims)
    items[0] = record
    with pytest.raises(DatasetValidationError) as exc:
        validate_prompts(items, claims)
    assert "ExperimentItem" in str(exc.value)


@pytest.mark.parametrize("tampering", ["extra_context", "instruction", "factual_content"])
def test_equal_tampering_across_all_conditions_is_rejected(claims, tampering):
    items = generate_prompts(claims)
    for index, item in enumerate(items):
        if tampering == "extra_context":
            prompt = "This claim comes from an expert.\n" + item.prompt
        elif tampering == "instruction":
            prompt = item.prompt.replace(TASK_INSTRUCTION, "Please justify this statement.")
        else:
            prompt = item.prompt.replace(item.false_claim, "The Earth is made of cheese.")
        items[index] = replace(item, prompt=prompt)
    with pytest.raises(DatasetValidationError):
        validate_prompts(items, claims)


@pytest.mark.parametrize("phrase", BANNED_PHRASES)
def test_banned_phrases_are_rejected_case_insensitively(claims, phrase):
    items = generate_prompts(claims)
    items[0] = replace(items[0], prompt=items[0].prompt + "\n" + phrase.upper())
    with pytest.raises(DatasetValidationError) as exc:
        validate_prompts(items, claims)
    assert "banned" in str(exc.value).lower()


def test_length_confounds_warn_even_on_invalid_prompts(claims):
    items = generate_prompts(claims)
    items = [
        replace(item, prompt=item.prompt + " Additional context." * 100)
        if item.confidence == ConfidenceLevel.HIGH else item
        for item in items
    ]
    with pytest.raises(DatasetValidationError) as exc:
        validate_prompts(items, claims)
    assert any("length" in warning.lower() for warning in exc.value.report.warnings)


def test_empty_prompts_against_nonempty_claims_is_rejected(claims):
    with pytest.raises(DatasetValidationError):
        validate_prompts([], claims)


def test_empty_reference_claims_are_rejected():
    with pytest.raises(DatasetValidationError):
        validate_prompts([], [])


def test_duplicate_reference_claims_are_rejected(claims):
    with pytest.raises(DatasetValidationError):
        validate_prompts(generate_prompts(claims), claims + [claims[0]])


def test_pipeline_scales_beyond_two_hundred_claims(valid_rows):
    from sycophancy.validation import validate_claims

    # Generated mathematical test fixtures exercise size, not a research corpus.
    rows = [dict(
        valid_rows[-1], claim_id=f"gen_{number:03d}",
        false_claim=f"A polygon with {number} sides has exactly {number + 1} sides.",
        false_answer=str(number + 1), true_answer=str(number),
    ) for number in range(3, 208)]
    claims, report = validate_claims(rows)
    items = generate_prompts(claims)
    report = validate_prompts(items, claims, report)
    assert len(items) == report.prompt_count == 615
    assert report.passed
