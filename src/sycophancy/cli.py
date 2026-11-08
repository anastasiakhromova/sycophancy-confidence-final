"""Offline preparation CLI with fail-closed validation and clear diagnostics."""

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from .data import load_claims, save_prompts, save_report
from .prompts import generate_prompts, validate_prompts
from .schemas import DatasetValidationError, ValidationReport
from .validation import validate_claims

LOGGER = logging.getLogger(__name__)


def _parser(project_root: Path) -> argparse.ArgumentParser:
    """Define explicit paths; direct script defaults are repository-relative."""
    parser = argparse.ArgumentParser(description="Validate claims and generate controlled confidence prompts.")
    parser.add_argument("--input", type=Path, default=project_root / "data/raw/claims_demo.csv")
    parser.add_argument("--output", type=Path, default=project_root / "data/processed/prompts.csv")
    parser.add_argument("--report", type=Path, default=project_root / "data/validation/dataset_report.json")
    parser.add_argument(
        "--require-verified", action="store_true",
        help="Reject candidate claims; every claim must have verified=true and source metadata.",
    )
    return parser


def _show_summary(report: ValidationReport) -> None:
    """Print counts with their provenance limits, including failed-run errors."""
    print("Dataset validation\n------------------")
    print(f"Claims: {report.total_claims}")
    print(f"Verified: {report.verified_claims}\nUnverified: {report.unverified_claims}")
    print("\nDomains:")
    for domain, count in report.claims_per_domain.items():
        print(f"  {domain}: {count}")
    print(f"\nGenerated experimental items: {report.prompt_count}")
    print("Confidence:")
    for condition, count in report.prompts_per_confidence.items():
        print(f"  {condition}: {count}")
    if report.average_prompt_length:
        print("\nAverage prompt length (characters / whitespace-delimited words):")
        for condition, lengths in report.average_prompt_length.items():
            print(f"  {condition}: {lengths['mean_characters']:.2f} / {lengths['mean_words']:.2f}")
    for warning in report.warnings:
        LOGGER.warning(warning)
    for error in report.errors:
        LOGGER.error(error)
    print(f"\nValidation: {'PASSED' if report.passed else 'FAILED'}")


def _paths_are_distinct(paths: Sequence[Path]) -> bool:
    """Prevent output/report arguments from overwriting raw input or each other."""
    resolved = [path.resolve() for path in paths]
    if len(set(resolved)) != len(paths):
        return False
    for index, left in enumerate(paths):
        for right in paths[index + 1:]:
            if left.exists() and right.exists() and left.samefile(right):
                return False
    return True


def main(argv: Sequence[str] | None = None, *, project_root: Path | None = None) -> int:
    """Run validation, generation and writes; return 0 on success, 1 on failure.

    The installed command defaults to the working directory. The repository
    script passes its own root explicitly. Explicit relative paths use the cwd.
    A failed validation writes a failed report but preserves any older output.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _parser(project_root or Path.cwd()).parse_args(argv)
    try:
        if not _paths_are_distinct((args.input, args.output, args.report)):
            LOGGER.error("Input, output and report must be distinct paths. No files were written.")
            return 1
    except OSError as exc:
        LOGGER.error("Cannot resolve input/output paths: %s", exc)
        return 1
    report = ValidationReport()
    try:
        claims, report = validate_claims(load_claims(args.input))
        if args.require_verified and report.unverified_claims:
            report.errors.append(
                f"--require-verified: {report.unverified_claims} unverified claims remain. "
                "Independently verify each claim and record its source first."
            )
            raise DatasetValidationError(report)
        items = generate_prompts(claims)
        validate_prompts(items, claims, report)
        save_prompts(items, args.output)
    except DatasetValidationError as exc:
        report = exc.report
    except (OSError, UnicodeError) as exc:
        report.errors.append(f"Dataset preparation I/O error: {exc}")
    try:
        save_report(report, args.report)
    except OSError as exc:
        report.errors.append(f"Cannot write validation report {args.report}: {exc}")
    _show_summary(report)
    if report.passed:
        LOGGER.info("Saved prompts: %s", args.output)
        LOGGER.info("Saved validation report: %s", args.report)
        return 0
    LOGGER.error(
        "This run failed. Any existing processed CSV may be from an earlier run; "
        "do not use it as the result of this run."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
