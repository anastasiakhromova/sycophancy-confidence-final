"""Evaluate persisted responses and produce a baseline report without network."""
from pathlib import Path
import sys
import argparse
import json

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from sycophancy.reporting import analyze_run


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir",type=Path,required=True)
    parser.add_argument("--output-dir",type=Path,default=Path("reports"))
    parser.add_argument("--bootstrap",type=int,default=5000)
    parser.add_argument("--seed",type=int,default=20261006)
    parser.add_argument("--annotations",type=Path)
    args=parser.parse_args(argv)
    try:
        result=analyze_run(args.run_dir,args.output_dir,n_bootstrap=args.bootstrap,seed=args.seed,annotation_path=args.annotations)
    except (ValueError,OSError) as exc:
        print(f"Analysis failed: {exc}",file=sys.stderr)
        return 1
    print(json.dumps(result,indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
