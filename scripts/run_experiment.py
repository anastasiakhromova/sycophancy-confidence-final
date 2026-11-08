"""Run independent model requests from a checked TOML experiment config."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sycophancy.experiment_config import load_experiment_config
from sycophancy.llm import LLMError
from sycophancy.runner import run_experiment


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Validate and plan; no network or files are created.")
    args = parser.parse_args(argv)
    try:
        summary = run_experiment(load_experiment_config(args.config), dry_run=args.dry_run)
    except (ValueError, OSError, RuntimeError, LLMError) as exc:
        print(f"Experiment failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] in {"complete", "dry_run"} else 130 if summary["status"] == "interrupted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
