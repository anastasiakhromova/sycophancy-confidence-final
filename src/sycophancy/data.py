"""Strict CSV input and deterministic, atomic output for the dataset pipeline."""

from __future__ import annotations

import csv
import json
import os
import tempfile
from collections import Counter
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO

from .constants import CLAIM_COLUMNS, PROMPT_COLUMNS, normalize_text
from .schemas import DatasetValidationError, ExperimentItem, ValidationReport


def _check_headers(headers: list[str], report: ValidationReport) -> None:
    """Collect every schema error instead of trusting DictReader's overwrites."""
    duplicates = sorted(name for name, count in Counter(headers).items() if count > 1)
    missing = sorted(set(CLAIM_COLUMNS) - set(headers))
    unexpected = sorted(set(headers) - set(CLAIM_COLUMNS))
    if duplicates:
        report.errors.append(f"Duplicate CSV columns: {', '.join(duplicates)}.")
    if missing:
        report.errors.append(f"Missing required CSV columns: {', '.join(missing)}.")
    if unexpected:
        report.errors.append(f"Unexpected CSV columns: {unexpected!r}.")


def load_claims(path: str | Path) -> list[dict[str, object]]:
    """Load a UTF-8 CSV, accepting a BOM and whitespace around column names.

    All nine schema columns must exist, including optional-value columns. Only
    normalized ``true``/``false`` become booleans; other values are retained so
    the domain validator can report them together with other content errors.
    CSV structural errors raise ``DatasetValidationError`` before any data is
    returned. Filesystem errors propagate to the caller.
    """
    report = ValidationReport()
    rows: list[dict[str, object]] = []
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            if reader.fieldnames is None:
                report.errors.append("Empty CSV: a header and at least one claim are required.")
            else:
                reader.fieldnames = [header.strip() for header in reader.fieldnames]
                _check_headers(reader.fieldnames, report)
                for row in reader:
                    report.total_claims += 1
                    label = f"CSV row ending at line {reader.line_num}"
                    if None in row:
                        report.errors.append(f"{label} contains more values than the header.")
                    absent = [key for key, value in row.items() if key is not None and value is None]
                    if absent:
                        report.errors.append(f"{label} contains fewer values than the header: {', '.join(absent)}.")
                    if None in row or absent:
                        continue
                    parsed: dict[str, object] = dict(row)
                    raw_verified = parsed.get("verified")
                    if isinstance(raw_verified, str):
                        normalized = normalize_text(raw_verified).casefold()
                        if normalized in {"true", "false"}:
                            parsed["verified"] = normalized == "true"
                    rows.append(parsed)
                if report.total_claims == 0:
                    report.errors.append("CSV contains no claim rows.")
    except (csv.Error, UnicodeError) as exc:
        report.errors.append(f"Cannot parse UTF-8 CSV: {exc}.")
    if report.errors:
        raise DatasetValidationError(report)
    return rows


@contextmanager
def _atomic_text_file(path: str | Path) -> Iterator[TextIO]:
    """Replace one output only after a successful write, cleaning failed temps."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=destination.parent,
            prefix=f".{destination.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def save_prompts(items: Sequence[ExperimentItem], path: str | Path) -> None:
    """Write prompts in the supplied order with stable columns and LF endings."""
    with _atomic_text_file(path) as stream:
        writer = csv.DictWriter(stream, fieldnames=PROMPT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for item in items:
            if type(item.verified) is not bool:
                raise ValueError(f"Experimental item {item.experiment_item_id}: verified must be a bool before serialization.")
            values = {column: getattr(item, column) for column in PROMPT_COLUMNS}
            values["domain"] = item.domain.value
            values["confidence"] = item.confidence.value
            values["verified"] = "true" if item.verified else "false"
            writer.writerow(values)


def save_report(report: ValidationReport, path: str | Path) -> None:
    """Write a stable UTF-8 JSON report without timestamps or platform newlines."""
    with _atomic_text_file(path) as stream:
        json.dump(report.to_dict(), stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
