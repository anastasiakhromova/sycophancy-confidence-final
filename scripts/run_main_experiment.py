"""Run/resume one collection per model with a shared budget and bounded workers."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sycophancy.experiment_config import load_experiment_config
from sycophancy.multi_model import run_multi_model


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        result = run_multi_model(load_experiment_config(args.config), dry_run=args.dry_run,
                                 max_workers=args.workers)
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Collection failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in {"complete", "dry_run"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
