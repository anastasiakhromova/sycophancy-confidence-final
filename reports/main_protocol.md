# Main analysis plan recorded before collection

Date: 2026-10-06. This plan follows the completed 50-claim pilot; it is not a preregistration preceding that pilot.

- Corpus: 150 source-reviewed false claims, 30 per domain; 88 easy and 62 medium proxy difficulty judgments. Original 50 pilot claims are retained, 100 are added for broader topical coverage. Source verification is by agents, not independent human review.
- Conditions: identical low/neutral/high template version 2.0, fixed proposition, assessment instruction, and 1–3 sentence answer request. Residual cue length and wording differences remain.
- Models: gpt-6-luna, gpt-6.1-sol, gpt-6-astra via Responses API; reasoning.effort=low, max_output_tokens=512; no sampling overrides, tools, retrieval, conversation carryover or generation seed.
- Collection: 450 responses per model, 1,350 total. Each model has its own shuffled, durable run with experiment seed 20261006. Up to three models run concurrently, using one serialized $8 ledger shared with baseline and robustness.
- Primary estimand: sycophancy HIGH−LOW per model. Correction is secondary; UNCERTAIN is descriptive and includes unmatched or ambiguous automatic labels. Primary labels use the evaluator code and answer-alias registry frozen in the collection manifest before generation.
- Paired tests: complete claim/model/repetition triplets, Cochran Q, exact two-sided McNemar for each pair, Holm within model/outcome families. Claim-cluster bootstrap: 5,000 draws, pointwise 95% percentile intervals. Zero-event bootstrap intervals can degenerate and do not establish equivalence.
- GEE: sycophancy ~ confidence * model, binomial logit, exchangeable working correlation, robust covariance, claim clusters. Reference levels: LOW and gpt-6-luna. Per-model confidence fits are also reported. Constant outcomes, separation, sparse event clusters, insufficient clusters and convergence problems suppress inference.
- Domain/difficulty contrasts are exploratory descriptive breakdowns. Difficulty is not a direct measure of model knowledge; there is no independent knowledge-only control.
- Human validation: 225 responses selected by seeded stratification over model/condition/domain/automatic label. Blind annotation CSV preserves original response text and leaves labels/annotator IDs blank. No human agreement metric is reported until genuine labels are supplied. Unweighted validation metrics on the stratified audit sample do not estimate natural class prevalence.
- Robustness after complete main collection and cost review: seeded random subset of 50 claims, 3 repetitions, gpt-6-luna, seed 20261007, same generation settings. This measures repeatability under provider nondeterminism, not a temperature intervention. Repetitions remain clustered by claim.
- Qualitative selection: deterministic first observed case per pattern, first cross-model label disagreement, first non-CORRECT example per domain. Absence of a category is reported explicitly.

No final paper, slides, dashboard or submission package belongs to this stage.
