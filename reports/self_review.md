# Engineering and research self-review

Collection checks below were recorded on 2026-10-06. Review provenance has since been clarified. No additional paid generation is needed for the requested runs.

## Verification

- Current full offline suite: 664 passed in 78.89 seconds; 192 third-party Matplotlib/pyparsing deprecation warnings. Test clients never make paid calls. Historical checks before the AI-review, supplemental and portability additions were 616 full-suite tests and 28 focused main-report tests.
- Version 0.2.0 builds and installs; isolated analysis/diagnostics/plot imports succeed; pip check reports no broken requirements. Exact research dependencies are locked.
- All 1,950 real response identities, requested/provider model IDs, low/512/omitted-sampling settings, budget receipt references and stage counts passed final_audit.json. All nine pre-main file hashes remain unchanged.
- Baseline 150, main 1,350, robustness 450; every call completed without retry or truncation. Input tokens total 79,203; output 74,629, including 2,332 reasoning tokens. Costs are computed once per receipt; reasoning is not charged twice. Total $1.3652759; no unsettled reservations or reserve overruns.
- Seven PNG/PDF pairs were produced; unavailable OR and human-confusion results are explicit panels, not fabricated values. Figure labels identify provisional automatic outcomes.
- A scan of project source/config/data/report text found no project-key patterns. Keys are read at runtime, not stored in source or configuration. Windows needed workspace temporary/cache directories and a scratch-only ACL workaround for testing; these are host constraints, not inference dependencies.

## Research interpretation

The 50-claim baseline has a correction ceiling. The expanded main study has no primary SYCOPHANTIC labels, so GEE logistic effects are not identifiable. Zero-event bootstrap intervals and no-discordance tests cannot establish equivalence. Main correction differences rely on imperfect lexical labels: the initial AI audit judges 50/54 non-CORRECT cases apparent factual repairs and leaves four mixed cases unresolved. That audit excluded all 1,296 CORRECT labels; the later AI review included 171 of them. Original independently entered human annotations are unavailable; the later author approval and reported second review are described below.

The repeatability signal (+2 pp HIGH–LOW SYCOPHANTIC; 95% CI 0 to 6 pp) is concentrated in one claim, with only 50 independent claim clusters. All five positive labels are mixed date-line replies, while one false Indian-Ocean endorsement is missed into UNCERTAIN. Post-hoc AI diagnostics describe these failures without relabeling the primary experiment. The same-50-claim main Luna comparison is included to avoid changing claim composition.

The original human annotation CSV fields remain blank. Main review: 225 rows, including every non-CORRECT reply; targeted robustness review: 16 rows. The later confusion matrix and macro F1 compare evaluators with a selected AI-origin reference; they do not establish validated human accuracy. Review-exclusion sensitivity selects response forms and is not a validation substitute.

Limits: one model family; hand-curated easy/medium facts; agent source verification; proxy difficulty; no independent knowledge control; no human confidence-manipulation check; exploratory main analysis after a pilot; wording/length differences; mutable provider aliases. Actual generation and observed data are reproducible through saved manifests and analysis commands, but future provider outputs are not guaranteed identical.

Stage 3 documents are complete: the [eight-page paper](../submission/paper.pdf),
[LaTeX source](../submission/paper.tex), [13-slide presentation](../submission/presentation.pptx),
[timed English script](../submission/speaking_script_en.md) and
[English defense preparation](../submission/defense_prep_en.md). The paper's
[build record](../submission/paper_build.json) identifies the fallback PDF renderer
and unverified TeX compilation. Final archive creation and repository publication
are separate release actions; the prepared documents do not imply human validation.

## Additional AI review, 2026-10-06

At the user's request, all 241 prepared sample rows have now been read by AI
reviewers with explicit per-row judgments, reasons and verbatim evidence. The
241 judgments pass coverage, identity, reference-text and evidence validation.
The 24-row coordinator check agreed on every row, and all ten unresolved cases
were additionally read. This is not human reliability evidence. The resulting
231 CORRECT / 10 UNRESOLVED assessments are secondary and do not alter primary
study estimates. Human CSV hashes remain unchanged. The new summary utility
passed eight focused offline tests; no paid API calls were made for this review.

## Author approval and reported second review

The author reviewed and approved the existing AI semantic judgments after seeing
them. This was acceptance of those judgments, not de novo independent labeling.
The author reports that a second reviewer independently assessed the responses
before seeing the existing judgments and found full agreement after comparison.
Original independently entered reviewer exports are unavailable. The saved
second-review rows were transcribed from the author's agreement summary by
reference to the AI judgments; they are not independently preserved annotations.
No inter-rater reliability was measured from original independent annotation sets.

The evaluator metrics describe agreement with the selected AI-origin reference,
not validated human accuracy or population performance. The unresolved judgments
remain unresolved, and the reference cannot establish sycophancy recall.

AI tools assisted analysis, drafting and semantic assessment. The project
author remains accountable for the study, its interpretation and the final text.

## Portable analysis and release verification, 2026-10-06

Offline readers now rebase the frozen collection's model, aliases, ledger and
predecessor paths onto the run directory supplied by the caller. Baseline and
robustness budget audits use the same resolution. No existence-based fallback
to the original machine is allowed. The collection manifests and evaluator
1.2 remain unchanged; paid run/resume identity checks remain strict.

The complete offline suite passed **664 tests in 78.89 seconds**, with 192
third-party Matplotlib/pyparsing deprecation warnings. New regressions retain
the original alongside a relocated copy and verify copy-specific responses,
aliases, model manifests, budget receipts and predecessor evidence. Lexical
path tests cover Windows and POSIX historical paths. A task-local test launcher
used inherited ACLs only in its Windows scratch directory because Python's
0700 temporary-directory ACL excluded this host's restricted process identity.

A clean candidate ZIP was extracted into a separate directory. Baseline and
main-plus-robustness analysis ran from outside that project with **5,000
bootstrap draws**, followed by the AI-review summary. All three commands
exited successfully while the original project remained present. All **1,950
primary labels matched** (150 baseline, 1,350 main, 450 robustness), and 32
frozen/raw evidence files retained their hashes in both source and copy. The
six baseline/main/robustness/GEE/sensitivity analysis JSON outputs also matched
their original parsed values exactly. The
copied AI review reconfirmed unchanged human fields. The supplemental analysis
also completed successfully in the extracted copy. No paid calls occurred.
Matplotlib could not save its host-global font cache, but generated the figures
successfully; this warning did not change the analysis.

`scripts/package_release.py` checks the nine frozen input hashes, uses an
explicit source/evidence/deliverable allowlist, excludes development clutter,
and generates a SHA-256 file inventory plus archive checksum. Packaging tests
verify reproducibility, exclusion rules, frozen-input rejection and tamper
detection. `.gitattributes` preserves exact line endings. `RELEASE.md` supplies
portable setup and reproduction commands. The final archive must include the
completed document edits; no owner-selected license is invented.
