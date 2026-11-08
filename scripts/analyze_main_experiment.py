from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from sycophancy.main_reporting import analyze_main


def main(argv=None):
    parser=argparse.ArgumentParser(description="Analyze the real multi-model collection.")
    parser.add_argument("--run-dir",type=Path,required=True)
    parser.add_argument("--metadata",type=Path,required=True)
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--bootstrap",type=int,default=5000)
    parser.add_argument("--seed",type=int,default=20261006)
    parser.add_argument("--annotations",type=Path)
    parser.add_argument("--robustness-dir",type=Path)
    args=parser.parse_args(argv)
    try:
        result=analyze_main(args.run_dir,args.metadata,args.output_dir,n_bootstrap=args.bootstrap,
                            seed=args.seed,annotation_path=args.annotations,robustness_dir=args.robustness_dir)
    except (ValueError,OSError) as exc:
        print(f"Analysis failed: {exc}",file=sys.stderr)
        return 1
    print(json.dumps(result,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
