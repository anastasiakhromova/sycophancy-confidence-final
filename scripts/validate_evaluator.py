"""Prepare blind packets, then compare v1/v2 offline without changing primary data."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "analyze"])
    parser.add_argument("--project", type=Path, default=PROJECT)
    parser.add_argument("--study-dir", type=Path)
    parser.add_argument("--review-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--human", type=Path, action="append", default=[], help="One latest JSON export per packet/person; repeat for independent reviewers")
    parser.add_argument("--bootstrap", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20261006)
    args = parser.parse_args(argv)
    from sycophancy.validation_study import prepare_study, analyze_study
    project = args.project.resolve()
    study = args.study_dir or project / "data/validation_v2"
    try:
        if args.action == "prepare":
            if args.human:
                raise ValueError("Import human exports only with analyze.")
            summary = prepare_study(project, study, args.review_dir or project / "reports/review_v2", seed=args.seed)
        else:
            result = analyze_study(project, study, args.output_dir or project / "reports/evaluator_v2",
                                   draws=args.bootstrap, seed=args.seed, submissions=args.human)
            summary = {"status": result["status"], "human_status": result["human_validation"]["status"],
                       "human_annotations": result["human_validation"]["human_annotations"],
                       "stage_counts": {s: d["v2"]["counts"] for s, d in result["stages"].items()},
                       "protected_source_files": result["protected_source_files"], "model_api_calls": 0}
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"Validation failed: {exc}\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
