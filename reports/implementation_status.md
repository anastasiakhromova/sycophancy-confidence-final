# Implementation status

Updated 2026-10-24. The original study and the separate challenge follow-up
are complete. The extension adds knowledge controls, true statements and three
confidence-cue families; all 390 target responses have valid automated
assessments. Results are recorded in `challenge_v1/results.md`. Executable checks are recorded in
[final_technical_verification.json](final_technical_verification.json) and
[final_reproduction_verification.json](final_reproduction_verification.json).
Earlier audit receipts retain their original dates and scope.

The delivery now uses English throughout its documents, forms, reports and
display metadata. The [language revision](../data/validation_v2/language_revision.json)
records translated metadata and preserves the original review provenance.
The full test suite passed 946 tests. The final verification receipt records
the execution details. Original-study offline reproduction preserved all 1,950
primary labels, all 59 validation sources and all nine pre-main hashes.

## Collected experiments

- Baseline: 50 claims x 3 conditions, 150 gpt-6-luna responses; cost $0.0029286.
- Main: 150 claims x 3 conditions x 3 models, 1,350 responses; cost $1.3526112.
- Robustness: 50 claims x 3 conditions x 3 repetitions on Luna, 450 responses;
  cost $0.0097361.

All 1,950 original-study requests completed without retries or truncations. Observed usage
priced at the frozen tariffs totals $1.3652759 against an $8 guard; this is not
a provider invoice. The three main models used the same Responses API settings:
reasoning effort low, max_output_tokens 512, no temperature/top_p, tools or
retrieval. Follow-up requests and their costs are recorded separately.

The main corpus contains 150 claims, 30 per domain, with 88 easy and 62 medium
rubric judgments. Source checking was performed by agents; independent human
verification of all factual sources is not claimed. Nine pre-main input hashes
and 59 validation-source hashes protect the frozen evidence.

## Separate challenge follow-up

The fixed design uses 30 new source-checked claims, six per domain, selected
for plausible confusions and scope distinctions. Their empirical difficulty
is measured from responses, not assumed from the selection rationale.
The 390-response Luna plan contains 30 neutral knowledge questions, 270
false-claim prompts across three confidence levels and three cue families,
and 90 matched true-statement controls using the original cue family.
All claims remain in the planned analysis regardless of the knowledge outcome.
All 390 target responses completed without retries or truncations. Their
observed usage-priced cost is $0.0144362.

The 27-call Sol wording diagnostic is complete, with 27 valid ratings.
Confidence medians are 60/70/100 for family A, 20/50/100 for B and 25/50/99 for C.
All families have the intended order; all agreement-pressure ratings are zero.
This is a single-model wording diagnostic, not human construct validation.

Target responses are assessed by Sol with cue, condition and target-model
identity withheld. Saved reasons and quotations support inspection, but
automated judgments are not human ground truth. Missing judgments retain
missing status. Paired claim-level estimates, cue-family comparisons,
knowledge-conditioned results and mixed-case bounds are written to
[the separate report](challenge_v1/results.md).

Observed labels are 30/30 CORRECT knowledge answers; 265 CORRECT, two
SYCOPHANTIC and three MIXED false-claim responses; and 89 ACCEPTED plus one
MIXED true control. False-claim correction is 98.15%, so the correction ceiling
persists. The pooled HIGH-minus-LOW sycophancy difference is 0.00 percentage
points, with a degenerate 95% claim-cluster interval [0.00, 0.00]. This does not
establish equivalence: the two positive labels concern the same claim CH027
under family A/LOW and family C/HIGH, so their opposite contrasts cancel within
the claim when pooled. MIXED-case assignment bounds are [-2.22, +1.11]
percentage points; they are not confidence intervals. The knowledge-conditioned
analysis retains all 30 claims and gives the same contrast.

The independent offline [execution verifier](challenge_v1/execution_verification.json)
passed all checks. It regenerated 390 labels from 98 saved assessor responses
and reconciled the frozen inputs, target outputs, token counts and costs.
This verifies saved execution evidence, not human annotation accuracy.

The follow-up has separate caps of $0.50 for target responses, $0.25 for
wording ratings and $1.25 for semantic assessment. With original spending,
the maximum authorized total is $3.3652759, below $8. The historical budget
ledger and all original experimental labels remain unchanged.
Actual additional usage-priced cost is $0.4076007: $0.0144362 for targets,
$0.0162620 for wording and $0.3769025 for assessment. Combined observed cost is
$1.7728766, with no unresolved reservations.

## Primary findings and their limits

Frozen v1 labels remain unchanged: baseline 150 CORRECT; main 1,296 CORRECT and
54 UNCERTAIN; robustness 434 CORRECT, 11 UNCERTAIN and 5 SYCOPHANTIC. Main
sycophancy odds ratios cannot be estimated with zero positive labels. Robustness
HIGH-LOW sycophancy differs by +2.00 percentage points, with claim-cluster 95% CI
[0.00, 6.00]. All five positive labels concern one date-line claim. Mixed
endorsement/repair and missed corrections limit the interpretation. The data do
not establish a general confidence effect or equivalence between conditions.

All 241 selected review responses received a separate AI semantic assessment:
231 CORRECT and 10 UNRESOLVED. Reasons and evidence remain in the saved review.
The primary labels were not overwritten. The exploratory v2 comparison is
separate and contains 1,722 CORRECT, 11 MIXED and 217 UNRESOLVED across all 1,950
responses. The supplemental report gives post-hoc assignment ranges and
zero-event diagnostics.

## Recorded review and evaluator comparison

**The author approved the existing AI semantic judgments.** Confirmation is
saved for 241 responses: 225 main and 16 robustness. This approval is not a
separate set of independently produced human labels.

**The author reports that a second reviewer independently assessed 241 responses
before seeing the existing labels and agreed with all judgments.** The reported
procedure is saved in `data/second_review/`; the author's approval is in
`data/author_review/`.

Original second-review exports are unavailable. The item-level reference was
transcribed from the author's complete-agreement summary, not independently
preserved annotations. It reproduces all 241 AI-origin judgments, including
10 UNRESOLVED cases. Inter-rater reliability was not measured from two original
annotation sets; these records do not establish validated human accuracy.

The reproducible [comparison](reviewer_validation/summary.md) excludes the ten
UNRESOLVED references and evaluates 231 determinate CORRECT references:

- v1: 171/231 matches, reference agreement 74.03%.
- v2: 189/231 matches, reference agreement 81.82%; its 42 abstentions count as mismatches.
- Fixed-four-class macro F1 (absent classes scored zero): v1 0.2127, v2 0.2250.
- F1 over reference-present classes (only CORRECT): v1 0.8507, v2 0.9000.

These metrics describe agreement with the selected AI-origin reference, not
validated human accuracy. The development examples are not a held-out population sample.
Verified positive SYCOPHANTIC references are absent, so sensitivity for that
class cannot be measured. The original form-import workflow remains available
separately. The current confusion-matrix figure is generated from the recorded
review reference, with denominator and abstentions stated explicitly.

## Documents

The [paper](../submission/paper.pdf) is an eight-page PDF compiled successfully
with Tectonic from the official Springer Nature sn-jnl class embedded in the
existing [LaTeX source](../submission/paper.tex). All eight pages were visually
checked. [Build metadata](../submission/paper_build.json) records the source,
review-summary and PDF hashes. The desktop editor's compiler launch is blocked
by a local Windows process-permission error; the exported PDF was independently
compiled and verified.

The [research deck](../submission/research_presentation.pptx) has 13 main
slides and one follow-up appendix. The
[alternative deck](../submission/presentation.pptx) has ten main slides and
four backups. Both have matching English scripts and ten-minute speaking plans. The presentation build and verification
receipts record current slide counts and visual checks. Native PowerPoint opening and live
speech timing have not been tested. Knowledge-only controls belong to the
separate follow-up, not the original 150-response pilot.

## Reproduction and handoff

The release builder creates full and technical-only archives with per-file
SHA-256 inventories. The technical archive excludes submission materials and
contains a concise English file index. Both retain all frozen dependencies,
including the five historical run-lock markers.

Reproduction operates on the selected extracted copy, without falling back to
original absolute paths. Analysis regenerates current budget reports while
preserving protected historical cost receipts byte-for-byte. Run the final
review comparison after the primary plotting commands to restore the current
review confusion matrix. Installation and commands are in [RELEASE.md](../RELEASE.md).

The topic has been approved by the instructor. Before handoff, the author must
supply their name for the paper and ensure the assessor can access the private
GitHub repository. The English talk still needs a live rehearsal. No additional
paid experiment is required to reproduce the delivered results.
