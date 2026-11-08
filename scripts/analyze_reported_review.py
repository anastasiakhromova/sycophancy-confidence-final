"""Validate the reported second-review reference and reproduce offline metrics."""
import argparse
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
from sycophancy.reported_review_validation import analyze_reported_review, render_confusion_figure


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=PROJECT)
    parser.add_argument("--figures", action="store_true", help="Render real confusion matrices with matplotlib")
    args = parser.parse_args(argv)
    project = args.project.resolve()
    try:
        result = analyze_reported_review(project)
        if args.figures:
            render_confusion_figure(result, project / "reports/reviewer_validation")
            render_confusion_figure(result, project / "reports/figures")
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"Reported-review validation failed: {exc}\n")
    print(json.dumps({"status": result["status"], "pooled": result["scopes"]["pooled"],
                      "model_api_calls": 0}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
