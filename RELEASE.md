# Offline reproduction and release

Run all commands from the extracted `sycophancy-confidence` directory. Python
3.11+ is required; the executed environment used Python 3.12.14. The saved
experiment can be analyzed without an API key or network access. Dependency
installation may need network access or a local wheel cache.

## Install the analysis environment

```sh
python -m venv .venv
```

Activate it (`.venv\Scripts\Activate.ps1` in PowerShell or
`source .venv/bin/activate` on macOS/Linux), then install:

```sh
python -m pip install -r requirements-research-lock.txt
python -m pip install --no-deps --no-build-isolation -e .
python -m pytest
```

`requirements-research-lock.txt` records the executed dependency versions, not
an offline wheel bundle. Python/platform-specific wheels must be available on
the target machine.

## Reproduce saved analyses

```sh
python scripts/analyze_experiment.py --run-dir data/runs/baseline --output-dir reports --bootstrap 5000 --seed 20261006
python scripts/analyze_main_experiment.py --run-dir data/runs/main --metadata data/raw/claims_main_metadata.csv --output-dir reports --bootstrap 5000 --seed 20261006 --robustness-dir data/runs/robustness
python scripts/summarize_ai_review.py
python scripts/supplemental_analysis.py
python scripts/validate_evaluator.py analyze --bootstrap 5000 --seed 20261006
python scripts/analyze_reported_review.py --figures
python scripts/verify_challenge.py
python scripts/analyze_challenge.py --figures
```

These offline commands regenerate derived reports, figures, evaluated CSVs and
cost checks. Work in a copy to keep the delivered derived artifacts unchanged.
Existing human annotation sheets are preserved. AI review remains distinct
from human validation. The main and robustness primary evaluations still use
the frozen evaluator and aliases; offline path fixes do not relabel responses.
The supplemental script regenerates separate post-hoc label-assignment and
zero-event diagnostics from the saved AI review. Its ranges are not human
validation or replacements for the primary estimates.

The evaluator-v2 command writes only its separate report directory. Prepared
blind review forms are in `reports/review_v2/`; they can be opened offline in a
browser. Do not re-run `prepare` on the delivered study. It refuses to replace
existing packets. The evaluator, partition and packet hashes are frozen in
`data/validation_v2/evaluator_lock.json`. The `analyze_reported_review.py` command validates the saved
second-review record and regenerates `reports/reviewer_validation/` plus the
current confusion-matrix figure. Run it after the primary analysis, which
recreates the original form-import reports. The AI-origin reference contains 241 selected
responses: 231 determinate CORRECT judgments and 10 UNRESOLVED judgments excluded
from classification metrics. The author approved existing AI judgments after
viewing them, rather than supplying de novo independent labels. The author also
reports that a second reviewer independently assessed the responses before
seeing those judgments and found full agreement after comparison. Original
independently entered reviewer exports are unavailable. The saved rows were
transcribed from that agreement summary by reference to the AI judgments, not
independently preserved annotations. The resulting metrics measure agreement
with this selected AI-origin reference, not validated human accuracy. No
inter-rater reliability was measured from original independent annotation sets.
The reference is not a raw form export or a held-out test.
The [validation workflow](reports/validation_v2_workflow.md) documents these
records, optional direct-export imports and the retrospective holdout limitations.

The final two commands verify and analyze the separate `challenge_v1` follow-up.
The verifier checks the frozen plan, raw provider outputs, token accounting,
budget receipts and regenerated semantic judgments. It writes
`reports/challenge_v1/execution_verification.json`. The analyzer reads
saved target responses, automated semantic labels, wording ratings and budget
receipts; it does not make API calls. Results are written under
`reports/challenge_v1/`. Coverage, paired claim-level uncertainty, cue-family
comparisons, knowledge-conditioned diagnostics and true-statement controls
remain separate from the frozen original estimates. Missing assessments are
not replaced with labels. The new semantic labels are automated, not human
annotations or a validated ground-truth set.

The delivered follow-up is complete: 390 target responses and 390 valid
automated judgments, supported by 27 wording calls and 98 assessor calls.
The execution verifier passed. Additional observed usage-priced cost is
$0.4076007; the original study plus follow-up totals $1.7728766, with no
unresolved reservations. These are recorded-token estimates, not an invoice.

Both commands work in a relocated copy without API credentials. The analyzer's
`summary.json` records collection and assessment coverage. The collector's
`--status` option is also offline, but retains strict original-path checks;
use the analyzer for status after extracting the ZIP elsewhere.


Absolute paths in historical manifests identify the original collection
machine. Offline readers resolve their relative layout from the run directory
passed on the command line, including model subruns, aliases, the shared ledger
and predecessor stages. Keep the complete project layout after extraction.
Missing or inconsistent local evidence fails instead of falling back to an
original copy that happens to exist. Windows historical paths are understood
on other operating systems. The frozen manifests themselves are not rewritten.
The inference/resume commands retain their strict original-path checks; they
are not needed to reproduce the saved evidence and may make paid requests.

## Follow-up collection and assessment

The delivered responses are sufficient for offline analysis. The following
commands document collection or resumption in the original collection
environment; paid stages require the configured API key. The relocated
release uses the offline commands above. `--dry-run` validates inputs and costs without generation;
`--prepare` freezes the plan without network access. Do not edit frozen inputs
or reset a budget ledger to restart a completed experiment.

```sh
python scripts/run_challenge.py --config configs/challenge.toml --dry-run
python scripts/run_challenge.py --config configs/challenge.toml --prepare
python scripts/check_confidence_wording.py --dry-run
python scripts/check_confidence_wording.py
python scripts/run_challenge.py --config configs/challenge.toml
python scripts/assess_challenge.py --dry-run
python scripts/assess_challenge.py
python scripts/analyze_challenge.py --figures
```

The target plan is 30 knowledge questions, 270 false-claim prompts and 90
true-claim controls on `gpt-6-luna`. The nine cue variants receive 27 descriptive
ratings from `gpt-6.1-sol`; the same judge model assesses target responses with
the cue, condition and target-model identity withheld. Neither operation is
independent human validation. All 30 claims are retained regardless of their
knowledge-control results. The saved protocol fixes the comparison and
missing-data rules before target collection.

The three follow-up ledgers cap target collection at $0.50, wording ratings at
$0.25 and semantic assessment at $1.25. The original $1.3652759 ledger is
preserved; the combined maximum is $3.3652759, below the original $8 guard.
Costs use observed tokens and recorded tariffs, not an account invoice.

The nine hashes in `data/verification/main_design.json` protect the frozen
research inputs. `.gitattributes` disables Git newline conversion because it
would change these exact byte hashes, including the evaluator source hash.

## Build and verify the release

```sh
python scripts/package_release.py --output work/release/sycophancy-confidence.zip
python scripts/package_release.py --verify work/release/sycophancy-confidence.zip
python scripts/package_release.py --technical --output work/release/sycophancy-confidence-technical.zip
```

The builder includes source, tests, configs, data, reports and `submission/`
when present. It excludes environments, build/cache directories, scratch files,
temporary lock files and Git metadata. The exact five frozen `.run.lock` evidence
markers referenced by the validation manifest are retained. It checks frozen input hashes, rejects symlinks
and obvious key material, and writes a per-file SHA-256 inventory inside the
ZIP plus an archive checksum alongside it. This credential check is limited
to recognizable key patterns; inspect the staged file list before publishing.
The same inputs and Python/zlib runtime produce the same ZIP bytes: ordering,
timestamps and permissions are fixed. Rebuild after final deliverable edits.

`--technical` excludes `submission/` and creates a concise English README listing
each technical file. It retains the same frozen research inputs and validation
evidence, and uses the same checksum and credential checks as the full archive.

## Check the delivery language

The delivered documents, review forms, reports and display metadata are in
English. Original model responses and numerical results are unchanged.
The metadata changes are recorded in
[language_revision.json](data/validation_v2/language_revision.json).

The optional language audit requires `pypdf` for PDF text extraction:

```sh
python -m pip install pypdf
python scripts/audit_release_language.py
python scripts/audit_release_language.py --archive work/release/sycophancy-confidence.zip
```

The audit checks packaged text, decoded JSON strings, PDF text, and Office
XML including slide notes and embedded spreadsheets. It reports any remaining
Cyrillic and any formats it cannot inspect. Images require a separate visual
check; an automated character scan alone cannot establish translation quality.
Exit codes are 0 for a complete text scan, 1 for Cyrillic found, and 2 for
incomplete coverage. This is an optional release check, not an inference or
analysis dependency.

## Repository and licensing status

The project is stored in the
[private GitHub repository](https://github.com/Orehovich3rec/sycophancy-confidence).
The assessor must receive access before assessment. Keep `data/` and `reports/`
tracked because they contain the evidence required for offline reproduction.
`.gitignore` excludes local credentials and generated development clutter.

For the full release, the partial Figma design file is linked from `submission/README.md`. The full ZIP
contains its authoring scripts, status manifest and speaking script; it does
not embed an offline `.fig` file or imply that cloud slide creation succeeded.
The technical archive omits this entire `submission/` section. The main
PowerPoint provides 13 main slides and one follow-up appendix with a matching
script. The alternative deck has ten main slides and four backups.

No project license has been selected by the owner. This release does not
invent a license or grant redistribution permissions. Source pages and quoted
evidence retain their respective rights; citations are retained with the data.
