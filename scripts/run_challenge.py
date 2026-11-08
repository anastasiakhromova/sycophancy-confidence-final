"""Plan, freeze, inspect or collect the separate 390-request challenge extension."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sycophancy.challenge import load_challenge_config, run_challenge


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "configs/challenge.toml")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true", help="Validate all 390 prompts and costs; no files or network")
    modes.add_argument("--prepare", action="store_true", help="Freeze the complete plan and sources; no network")
    modes.add_argument("--preflight", action="store_true", help="Freeze and check exact model availability; no generation")
    modes.add_argument("--status", action="store_true", help="Read offline collection status; no key or network")
    parser.add_argument("--max-new-requests", type=int, help="Stop after this many new physical requests; design stays fixed")
    args = parser.parse_args(argv)
    try:
        result = run_challenge(load_challenge_config(args.config), dry_run=args.dry_run,
            prepare=args.prepare, preflight=args.preflight, status_only=args.status,
            max_new_requests=args.max_new_requests)
    except (OSError, ValueError, RuntimeError) as exc:
        # The client may include provider text in exceptions; never print it here.
        print(json.dumps({"status": "error", "error_type": type(exc).__name__,
                          "message": "Challenge stopped. Check frozen inputs, configuration and environment; no model substitution."}))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0 if result["status"] in {"dry_run", "prepared", "preflight_ok", "complete", "not_started", "requested_stop"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
