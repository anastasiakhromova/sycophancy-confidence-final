# Evaluator v2 validation: current status and next steps

The technical workflow is ready: a separate v2 evaluator, two blinded forms, import of independent assessments, confusion matrices, per-class metrics, reviewer-agreement calculations when original exports are supplied, and a separate recalculation of effects. **241 author-approved AI judgments** and **241 reference rows transcribed from a reported second-review agreement summary** are saved. The quantitative v1/v2 comparison against this selected AI-origin reference is in a [separate report](reviewer_validation/summary.md). No new API requests were made; primary data and v1 labels are preserved.

**The author approved the existing AI semantic judgments; this was not de novo independent annotation.** Confirmation is saved for each of the 241 responses: 225 main and 16 robustness. The [assessment file](../data/author_review/confirmed_labels.jsonl) is linked to the [confirmation record](user_review_statement.json).

**The author reports independent second review of 241 responses before disclosure of the existing labels, followed by complete agreement.** The [transcribed reference rows](../data/second_review/reported_labels.jsonl) and [reported procedure](second_review_statement.json) are saved separately. Original reviewer exports are unavailable: the rows were transcribed from the author's agreement summary, not independently preserved annotations. They reproduce the AI semantic judgments, including ten UNRESOLVED cases. No inter-rater reliability was measured from two original annotation sets. `evaluator_v2/human_validation.json` describes the earlier form-import workflow; current reference-agreement metrics are in `reviewer_validation/summary.json`.

Across 231 determinate responses, v1 agrees on 171/231 (74.03%) and v2 on 189/231 (81.82%). The 42 v2 abstentions remain in the denominator and count as mismatches. F1 for the supported CORRECT class is 0.8507 and 0.9000, respectively; macro F1 over four fixed classes, with absent classes scored zero, is 0.2127 and 0.2250. These are agreement metrics against a selected AI-origin reference, not validated human accuracy. This sample cannot establish SYCOPHANTIC recall or accuracy across the full response population.

## For reviewers

Open the [start page](review_v2/index.html) in a browser. The `reports/review_v2/` folder can be shared on its own: the English forms are self-contained and do not require Python. Do not share the coordinator manifest, AI assessments or comparison reports with reviewers before they finish annotating.

1. Enter your own reviewer ID. Read the instructions for the five classes.
2. Assess every response independently. A quotation and comment help resolve disputed cases.
3. You can stop at any time. Download a partial JSON file and later import it into the same form.
4. Measuring reviewer agreement requires two actual reviewers to annotate overlapping responses independently. Different IDs used by one person do not establish independence.
5. Give the coordinator the latest JSON file for each packet and reviewer. Missing assessments must remain missing and must not be filled with AI labels.

If opening HTML from disk does not preserve the draft, run this command from the project root:

```sh
python scripts/serve_review.py reports/review_v2 --port 8765
```

Then open `http://127.0.0.1:8765/` in a browser. The server is accessible only on this computer and does not accept file writes; the browser saves assessments locally and exports them as JSON.

## For coordinators: method and limits of inference

Packet A contains 241 responses previously reviewed by AI: 225 main and 16 robustness. These examples were used to develop the v2 rules; comparisons on them are development diagnostics, not test-set accuracy estimates.

Packet B contains 198 main responses across 22 claim groups. It excludes all pilot claim groups and all groups represented in the earlier AI review. Another 36 responses from the same groups in other stages were also excluded from v2 development. The split was created retrospectively: the corpus and its aggregates had already been available. B therefore cannot be described as a prospective independent test. All 198 responses had the original CORRECT label; the sample is not representative across classes and does not guarantee that sycophancy recall can be estimated.

Before the first analysis of B, SHA-256 hashes of the v2 source, v1 source, aliases, coordinator manifest and packets were frozen in `data/validation_v2/evaluator_lock.json`. The rules are not retuned on B after its disclosure. Any future changes require an explicitly new post-hoc version and a new independent review.

The five classes distinguish three different phenomena: UNCERTAIN means the model itself avoids a determinate answer; MIXED means incompatible endorsement and correction; UNRESOLVED means the evaluator abstains from deciding. The new scheme is not equivalent to the three original classes. v2 remains a heuristic, so improvements on individual cases do not establish improved overall accuracy.

## Import and reproduction

Install the environment as described in [RELEASE.md](../RELEASE.md). The prepared packets are already included; do not rerun `prepare`, which deliberately refuses to overwrite existing work. To rebuild the standard English review forms from the saved packets, run:

```sh
python scripts/build_review_forms.py
```

The active review forms are in `reports/review_v2/`.

Without human annotation exports:

```sh
python scripts/validate_evaluator.py analyze --bootstrap 5000
python scripts/analyze_reported_review.py --figures
```

With actual exports (replace the paths and include every current file):

```sh
python scripts/validate_evaluator.py analyze --bootstrap 5000 --human work/human/reviewer01-a.json --human work/human/reviewer01-b.json --human work/human/reviewer02-a.json --human work/human/reviewer02-b.json --output-dir reports/evaluator_v2_human
```

Keep original exports separately, for example in the local `work/human/` folder, which is excluded from Git and release ZIP files. Reports include reviewer pseudonyms and comparisons; check the agreed disclosure scope before publishing. Import validates packet membership, record SHA-256 hashes, allowed classes, exact quotations and the reviewer declaration. It does not prove a person's identity or independence. Supply one latest version for each reviewer/packet pair.

The script compares v1 and v2 with each reviewer separately, calculates agreement and Cohen's kappa on the overlap between two sets of annotations, and lists conflicts. There is no automatic consensus. Disagreements require separate, documented human adjudication; raw labels are retained. Metrics on incomplete or selected samples describe only those samples. Without human SYCOPHANTIC labels, recall for that class is undefined.

## Automatic results

| Stage | N | CORRECT v2 | MIXED v2 | UNRESOLVED v2 |
|---|---:|---:|---:|---:|
| Baseline | 150 | 142 | 0 | 8 |
| Main | 1350 | 1196 | 5 | 149 |
| Robustness | 450 | 384 | 6 | 60 |

v2 SYCOPHANTIC and UNCERTAIN counts are zero in all three stages. These are detector results, not proof that the corresponding phenomena are absent. In total, 217 responses remained UNRESOLVED and 11 received MIXED. Among the 241 development responses, 31 previous UNCERTAIN labels changed to CORRECT, and all five previous SYCOPHANTIC labels changed to MIXED. However, 13 previous CORRECT labels in this sample became UNRESOLVED: v2 sacrifices coverage and cannot be considered demonstrably more accurate.

The [separate report](evaluator_v2/comparison.md) and [machine-readable results](evaluator_v2/comparison.json) provide label transitions, rates by model/condition, paired contrasts and confidence intervals. Bootstrap resampling selects whole claim groups, preserving conditions and repetitions; exact tests are calculated separately by repetition with Holm correction within each model/outcome combination. MIXED and UNRESOLVED remain in the denominators. These results are exploratory and do not replace the frozen primary conclusions.
