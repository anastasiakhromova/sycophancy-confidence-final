"""Structural checks for candidate claims; these cannot establish factual truth."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from .constants import CLAIM_COLUMNS, banned_phrases_in, duplicate_key, normalize_text
from .schemas import Claim, DatasetValidationError, Domain, ValidationReport

_OPTIONAL_FIELDS = frozenset({"source", "source_type", "notes"})
_ID_PATTERN = re.compile(r"[a-z][a-z0-9_]*\Z")
_PLACEHOLDERS = frozenset({"asdf", "qwerty", "zxcv", "blah", "foo", "bar", "baz", "lorem", "ipsum"})


def _normalize_row(
    row: Mapping[str, object], row_number: int, report: ValidationReport,
) -> dict[str, str | bool | None]:
    """Validate column presence/types and return normalized declared values."""
    label = f"Row {row_number}"
    missing_columns = sorted(set(CLAIM_COLUMNS) - set(row))
    unexpected = sorted((repr(key) for key in row if key not in CLAIM_COLUMNS))
    if missing_columns:
        report.errors.append(f"{label}: missing required columns: {', '.join(missing_columns)}.")
    if unexpected:
        report.errors.append(f"{label}: unexpected columns: {', '.join(unexpected)}.")
    normalized: dict[str, str | bool | None] = {}
    for field in CLAIM_COLUMNS:
        value = row.get(field)
        if isinstance(value, str):
            value = normalize_text(value)
        absent = value is None or (isinstance(value, str) and value == "")
        if absent:
            report.missing_values[field] += 1
        if field == "verified":
            if type(value) is not bool:
                report.errors.append(f"{label}: verified must have boolean type, received {value!r}.")
                normalized[field] = None
            else:
                normalized[field] = value
            continue
        if absent:
            normalized[field] = None
            if field not in _OPTIONAL_FIELDS:
                report.errors.append(f"{label}: {field} is required and cannot be empty.")
        elif not isinstance(value, str):
            report.errors.append(f"{label}: {field} must be a string, received {type(value).__name__}.")
            normalized[field] = None
        else:
            if any(ord(character) < 32 or ord(character) == 127 for character in value):
                report.errors.append(f"{label}: {field} contains unsupported control characters.")
            normalized[field] = value
    return normalized


def _check_claim_text(text: str, label: str, report: ValidationReport) -> None:
    """Reject surface noise, not semantic falsehood or every possible gibberish.

    Candidate English statements require 12 characters, three whitespace tokens,
    and six letters. Repeated single tokens, long character runs, and statements
    dominated by common filler/keyboard words are flagged for human rewriting.
    These conservative, explicit heuristics can reject a valid terse statement;
    they do not replace human review of meaning, truth, or ambiguity.
    """
    words = re.findall(r"[^\W\d_]+", text.casefold(), flags=re.UNICODE)
    if len(text) < 12 or len(text.split()) < 3 or sum(character.isalpha() for character in text) < 6:
        report.errors.append(f"{label}: false_claim is too short; use at least 12 characters, 3 words, and 6 letters.")
    repetitive = bool(words) and (len(set(words)) == 1 or re.search(r"([^\W\d_])\1{4,}", text.casefold()) is not None)
    filler = bool(words) and sum(word in _PLACEHOLDERS for word in words) / len(words) >= 0.5
    if repetitive or filler:
        report.errors.append(f"{label}: false_claim appears to contain repetitive or placeholder gibberish; review its meaning.")
    for phrase in banned_phrases_in(text):
        report.errors.append(f"{label}: false_claim contains banned instruction phrase: {phrase!r}.")


def _check_values(
    values: Mapping[str, str | bool | None], label: str, report: ValidationReport,
) -> Domain | None:
    """Check field relationships and provenance without claiming verification."""
    claim_id = values["claim_id"]
    if isinstance(claim_id, str) and not _ID_PATTERN.fullmatch(claim_id):
        report.errors.append(f"{label}: malformed claim_id {claim_id!r}; expected [a-z][a-z0-9_]*.")
    domain = None
    if values["domain"] is not None:
        try:
            domain = Domain(values["domain"])
            report.claims_per_domain[domain.value] += 1
        except ValueError:
            report.errors.append(f"{label}: invalid domain {values['domain']!r}; expected one of {', '.join(item.value for item in Domain)}.")
    text = values["false_claim"]
    if isinstance(text, str):
        _check_claim_text(text, label, report)
    false_answer, true_answer = values["false_answer"], values["true_answer"]
    if isinstance(false_answer, str) and isinstance(true_answer, str):
        if duplicate_key(false_answer) == duplicate_key(true_answer):
            report.errors.append(f"{label}: false_answer and true_answer must differ after normalization.")
    if values["verified"] is True:
        report.verified_claims += 1
        if not values["source"]:
            report.errors.append(f"Verified claim {label} has no source.")
        if not values["source_type"]:
            report.errors.append(f"Verified claim {label} has no source_type.")
    elif values["verified"] is False:
        report.unverified_claims += 1
    return domain


def _add_dataset_warnings(report: ValidationReport) -> None:
    """Make coverage, imbalance, and remaining provenance work visible."""
    absent = [domain for domain, count in report.claims_per_domain.items() if count == 0]
    if absent:
        report.warnings.append(f"Missing domains: {', '.join(absent)}.")
    counts = list(report.claims_per_domain.values())
    if len(set(counts)) > 1:
        ratio = f"{max(counts) / min(counts):.2f}" if min(counts) else "undefined (zero-count domain)"
        summary = ", ".join(f"{domain}={count}" for domain, count in report.claims_per_domain.items())
        report.warnings.append(f"Domain imbalance: {summary}; max/min ratio={ratio}.")
    if report.unverified_claims:
        report.warnings.append(f"{report.unverified_claims} unverified candidate claims require source-based human verification before research use.")


def validate_claims(rows: Sequence[Mapping[str, object]]) -> tuple[list[Claim], ValidationReport]:
    """Normalize claims and aggregate all detectable structural validation errors.

    Optional values may be blank, but their columns must exist. ``verified`` must
    be an actual bool; CSV text conversion belongs to ``load_claims``. Verified
    rows require both a source and source type: a flag without provenance is an
    error. Sources may be URLs or bibliographic text. No source is fetched here.

    ``duplicate_count`` counts duplicate rows beyond the first occurrence, once
    per offending row even if both ID and text duplicate. ``missing_values``
    counts null/blank cells across all columns, including allowed optional ones.
    Valid claims are sorted by ID. Failure raises ``DatasetValidationError``
    carrying the complete report, rather than returning a partial dataset.
    """
    report = ValidationReport(total_claims=len(rows))
    report.missing_values = {column: 0 for column in CLAIM_COLUMNS}
    claims: list[Claim] = []
    seen_ids: set[str] = set()
    seen_texts: dict[str, str] = {}
    if not rows:
        report.errors.append("Dataset contains no claims.")
    for row_number, row in enumerate(rows, start=1):
        errors_before = len(report.errors)
        if not isinstance(row, Mapping):
            report.errors.append(f"Row {row_number} must be a mapping of column names to values.")
            continue
        values = _normalize_row(row, row_number, report)
        claim_id = values["claim_id"]
        label = claim_id if isinstance(claim_id, str) else f"row {row_number}"
        domain = _check_values(values, label, report)
        duplicate = False
        if isinstance(claim_id, str):
            if claim_id in seen_ids:
                report.errors.append(f"Duplicate claim_id detected: {claim_id}.")
                duplicate = True
            seen_ids.add(claim_id)
        text = values["false_claim"]
        if isinstance(text, str):
            key = duplicate_key(text)
            if key in seen_texts:
                report.errors.append(f"Duplicate normalized false_claim detected: {label} matches {seen_texts[key]}.")
                duplicate = True
            else:
                seen_texts[key] = label
        report.duplicate_count += int(duplicate)
        if len(report.errors) == errors_before and domain is not None:
            claims.append(Claim(**{**values, "domain": domain}))
    _add_dataset_warnings(report)
    if report.errors:
        raise DatasetValidationError(report)
    return sorted(claims, key=lambda claim: claim.claim_id), report
