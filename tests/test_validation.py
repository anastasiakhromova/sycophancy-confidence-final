"""Dataset integrity checks without internet or model dependencies."""

from __future__ import annotations

import copy

import pytest

from sycophancy.constants import BANNED_PHRASES
from sycophancy.schemas import DatasetValidationError, Domain
from sycophancy.validation import validate_claims


def test_valid_dataset_counts_all_domains(valid_rows):
    claims, report = validate_claims(valid_rows)
    assert len(claims) == report.total_claims == 5
    assert report.verified_claims == 0
    assert report.unverified_claims == 5
    assert report.duplicate_count == 0
    assert report.passed
    assert not report.errors
    assert report.warnings  # Candidate status must remain visible.
    assert report.claims_per_domain == {domain.value: 1 for domain in Domain}
    assert [claim.claim_id for claim in claims] == sorted(row["claim_id"] for row in valid_rows)


def test_validation_does_not_modify_caller_records(valid_rows):
    valid_rows[0]["false_claim"] = "  The capital of Canada\t is Toronto.  "
    before = copy.deepcopy(valid_rows)
    validate_claims(valid_rows)
    assert valid_rows == before


def test_normalizes_unicode_whitespace_and_optional_blanks(valid_rows):
    valid_rows[0].update(
        claim_id="  geo_001  ",
        false_claim="  The\tcapital of Canada\n is Toronto.\u00a0 ",
        false_answer=" Ｔｏｒｏｎｔｏ ",
        true_answer="  Ottawa\u00a0",
        source="  ",
        source_type="\t",
        notes="\n",
    )
    claims, _ = validate_claims(valid_rows)
    claim = next(claim for claim in claims if claim.claim_id == "geo_001")
    assert claim.false_claim == "The capital of Canada is Toronto."
    assert claim.false_answer == "Toronto"
    assert claim.true_answer == "Ottawa"
    assert claim.source is claim.source_type is claim.notes is None


def test_duplicate_claim_id_is_actionable(valid_rows):
    valid_rows[1]["claim_id"] = "geo_001"
    with pytest.raises(DatasetValidationError) as exc:
        validate_claims(valid_rows)
    assert "geo_001" in str(exc.value)
    assert "duplicate" in str(exc.value).lower()
    assert exc.value.report.duplicate_count >= 1


@pytest.mark.parametrize("replacement", [
    "the capital of canada is toronto.",
    "  The capital  of Canada\t is Toronto! ",
    "Ｔｈｅ capital of Canada is Toronto.",
])
def test_duplicate_normalized_claim_under_another_id(valid_rows, replacement):
    valid_rows[1]["false_claim"] = replacement
    with pytest.raises(DatasetValidationError) as exc:
        validate_claims(valid_rows)
    assert "duplicate" in str(exc.value).lower()
    assert exc.value.report.duplicate_count >= 1


def test_exact_duplicate_record_is_rejected(valid_rows):
    valid_rows.append(dict(valid_rows[0]))
    with pytest.raises(DatasetValidationError) as exc:
        validate_claims(valid_rows)
    assert exc.value.report.duplicate_count >= 1


@pytest.mark.parametrize("domain", ["politics", "GEOGRAPHY", 7])
def test_invalid_domain_is_rejected(valid_rows, domain):
    valid_rows[0]["domain"] = domain
    with pytest.raises(DatasetValidationError, match="domain"):
        validate_claims(valid_rows)


@pytest.mark.parametrize("field", ["claim_id", "domain", "false_claim", "false_answer", "true_answer"])
@pytest.mark.parametrize("missing", [None, "", "  \t\n"])
def test_required_values_are_reported(valid_rows, field, missing):
    valid_rows[0][field] = missing
    with pytest.raises(DatasetValidationError) as exc:
        validate_claims(valid_rows)
    assert field in str(exc.value)
    assert exc.value.report.missing_values[field] >= 1


def test_missing_column_is_rejected_even_when_optional_value(valid_rows):
    del valid_rows[0]["notes"]
    with pytest.raises(DatasetValidationError, match="notes"):
        validate_claims(valid_rows)


def test_unknown_column_is_rejected(valid_rows):
    valid_rows[0]["confidence"] = "high"
    with pytest.raises(DatasetValidationError, match="confidence"):
        validate_claims(valid_rows)


@pytest.mark.parametrize("field,value", [
    ("false_claim", 123), ("false_answer", []), ("true_answer", {}),
    ("source", True), ("source_type", 7), ("notes", ["text"]),
])
def test_non_string_text_values_fail_cleanly(valid_rows, field, value):
    valid_rows[0][field] = value
    with pytest.raises(DatasetValidationError) as exc:
        validate_claims(valid_rows)
    assert field in str(exc.value)


@pytest.mark.parametrize("row", [None, "not a mapping", ["not", "a", "mapping"]])
def test_non_mapping_rows_fail_with_validation_report(row):
    with pytest.raises(DatasetValidationError) as exc:
        validate_claims([row])
    assert "mapping" in str(exc.value).lower()


def test_unsupported_control_characters_are_rejected(valid_rows):
    valid_rows[0]["false_claim"] += "\x00"
    with pytest.raises(DatasetValidationError) as exc:
        validate_claims(valid_rows)
    assert "control" in str(exc.value).lower()


@pytest.mark.parametrize("true_answer", ["Toronto", " TORONTO ", "Ｔｏｒｏｎｔｏ"])
def test_false_and_true_answer_must_differ_after_normalization(valid_rows, true_answer):
    valid_rows[0]["true_answer"] = true_answer
    with pytest.raises(DatasetValidationError) as exc:
        validate_claims(valid_rows)
    assert "answer" in str(exc.value).lower()


@pytest.mark.parametrize("value", ["false", "true", "yes", "0", 0, 1, None, "", []])
def test_verified_must_be_actual_boolean_in_mapping_api(valid_rows, value):
    valid_rows[0]["verified"] = value
    with pytest.raises(DatasetValidationError, match="verified"):
        validate_claims(valid_rows)


@pytest.mark.parametrize("missing_field", ["source", "source_type"])
def test_verified_claim_requires_source_and_source_type(valid_rows, missing_field):
    valid_rows[0].update(verified=True, source="Test fixture bibliography", source_type="reference")
    valid_rows[0][missing_field] = None
    with pytest.raises(DatasetValidationError) as exc:
        validate_claims(valid_rows)
    assert missing_field in str(exc.value)
    assert "geo_001" in str(exc.value)


def test_verified_record_allows_non_url_bibliography(valid_rows):
    valid_rows[0].update(verified=True, source="Synthetic fixture bibliography, page 7", source_type="book")
    claims, report = validate_claims(valid_rows)
    assert sum(claim.verified for claim in claims) == 1
    assert report.verified_claims == 1
    assert report.unverified_claims == 4


@pytest.mark.parametrize("claim_id", ["Geo_001", "geo-001", "001", "geo 001", "../geo_001"])
def test_ids_have_safe_canonical_form(valid_rows, claim_id):
    valid_rows[0]["claim_id"] = claim_id
    with pytest.raises(DatasetValidationError, match="claim_id"):
        validate_claims(valid_rows)


@pytest.mark.parametrize("false_claim", ["x", "!!!", "12345678901234567890", "asdf qwer zxcv"])
def test_obvious_non_claims_are_rejected(valid_rows, false_claim):
    valid_rows[0]["false_claim"] = false_claim
    with pytest.raises(DatasetValidationError, match="false_claim"):
        validate_claims(valid_rows)


@pytest.mark.parametrize("phrase", BANNED_PHRASES)
def test_instruction_contamination_in_claim_is_rejected(valid_rows, phrase):
    valid_rows[0]["false_claim"] += " " + phrase.upper()
    with pytest.raises(DatasetValidationError):
        validate_claims(valid_rows)


@pytest.mark.parametrize("phrase", [
    "Don’t question me",
    "DO\t NOT\n CHALLENGE THIS",
    "Ａｓｓｕｍｅ this is true",
])
def test_unicode_and_whitespace_do_not_hide_banned_instructions(valid_rows, phrase):
    valid_rows[0]["false_claim"] += " " + phrase
    with pytest.raises(DatasetValidationError) as exc:
        validate_claims(valid_rows)
    assert "banned" in str(exc.value).lower()


def test_validation_collects_independent_errors(valid_rows):
    valid_rows[0]["true_answer"] = ""
    valid_rows[1]["domain"] = "not_a_domain"
    valid_rows[2]["verified"] = "yes"
    with pytest.raises(DatasetValidationError) as exc:
        validate_claims(valid_rows)
    report = exc.value.report
    assert len(report.errors) >= 3
    assert not report.passed
    assert report.missing_values["true_answer"] == 1
    assert all(field in str(exc.value) for field in ["true_answer", "domain", "verified"])


def test_absent_domains_and_imbalance_are_visible(valid_rows):
    _, report = validate_claims(valid_rows[:1])
    warning_text = " ".join(report.warnings).lower()
    assert "science" in warning_text
    assert "missing" in warning_text or "absent" in warning_text
    assert report.claims_per_domain["science"] == 0


def test_imbalance_warning_when_all_domains_present(valid_rows):
    valid_rows.append(dict(valid_rows[0], claim_id="geo_002", false_claim="The capital of Australia is Sydney."))
    _, report = validate_claims(valid_rows)
    assert any("imbalan" in warning.lower() for warning in report.warnings)
    assert report.claims_per_domain["geography"] == 2


def test_empty_dataset_is_rejected():
    with pytest.raises(DatasetValidationError):
        validate_claims([])


def test_reordering_rows_preserves_claims_and_report(valid_rows):
    first_claims, first_report = validate_claims(valid_rows)
    second_claims, second_report = validate_claims(list(reversed(valid_rows)))
    assert first_claims == second_claims
    assert first_report.to_dict() == second_report.to_dict()
