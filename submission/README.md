# Submission package

## Files

- `../report.pdf` - eight-page English article compiled from `paper.tex` using the official Springer Nature `sn-jnl` class.
- `paper.tex` - editable standalone LaTeX source, with the unchanged official class and its licence embedded.
- `manuscript.json` - editable article content.
- `build_paper.py` - source generation, real LaTeX compilation and four-to-eight-page check.
- `paper_build.json` - compiler version, page count and source/output hashes.
- `defense_prep_en.md` - English preparation guide and 22 likely questions.
- `topic_proposal.txt` - approved custom-topic description.
- `template/` - official template source and provenance.

The previous presentation files and build sources have been removed. A replacement
presentation is in preparation. The defense guide remains useful for its research
explanations and questions; its old slide timetable is historical. Earlier build
references in dated verification reports describe the previous release.

Author name and any required student number were not supplied. Set `author` in
`manuscript.json` and rebuild before submission. The article currently leaves the
name blank.

## Results and review

The frozen primary experiment has 1,350 responses: 1,296 CORRECT, 54 UNCERTAIN
and zero automatically detected SYCOPHANTIC. The pilot contains 150 responses;
the repeated collection contains 450. Original responses and primary labels
remain unchanged. The pilot uses the same false-claim prompts, not a separate
knowledge-only baseline.

The separate `challenge_v1` follow-up uses 30 new source-checked claims,
three confidence-cue families, neutral knowledge questions and matched true
statements. All 390 Luna responses completed without retries or truncations;
target generation cost $0.0144362. Assessment coverage and results are in
`../reports/challenge_v1/results.md`. The 27-call Sol wording
diagnostic produced ordered LOW/NEUTRAL/HIGH confidence medians in all three
families. This is a model-based diagnostic, not a human manipulation check.
Blinded Sol semantic judgments cover all 390 responses: 30/30 knowledge answers
are CORRECT; false assertions have 265 CORRECT, two SYCOPHANTIC and three MIXED
responses; true controls have 89 ACCEPTED and one MIXED. The pooled HIGH-LOW
sycophancy difference is 0.00 percentage points, with a degenerate interval
[0.00, 0.00] and MIXED-case assignment bounds [-2.22, +1.11]. The interval does
not prove equivalence: the two positive labels occur on CH027 under family
A/LOW and family C/HIGH, and their opposite contrasts cancel within the claim.
The assignment bounds are not confidence intervals.
The correction ceiling persists at 98.15%. These automated judgments remain
separate from human validation and do not change the original study's labels.
The extension cost $0.4076007; combined observed usage-priced cost is $1.7728766.
The independent offline execution check passed, including regeneration of
all 390 judgments from saved assessor outputs.

The semantic review contains 241 selected responses and originated from AI
judgments. The author approved the existing judgments and reported independent
second-reviewer assessment before viewing the labels, with complete agreement.
Original reviewer exports are unavailable. The saved reference reuses the AI
judgments based on that report. Independence and full agreement are unverified;
these records do not establish measured inter-rater reliability.

The ten UNRESOLVED reference cases are excluded from reference-agreement/F1 calculations.
On the remaining 231 CORRECT references, v1 matches 171 (74.03%) and exploratory
v2 matches 189 (81.82%). V2's 42 abstentions are counted as nonmatches. Supported-class
macro F1 is 0.8507 and 0.9000; fixed four-class macro F1 with undefined terms set
to zero is 0.2127 and 0.2250. Other reference classes have no support, so
sycophancy recall remains unvalidated. See `../reports/reviewer_validation/summary.md`
and its JSON, tables and confusion matrices.

These are selected-sample diagnostics. V2 was developed using the earlier AI
judgments for these same items; author approval and reported second review do
not turn the sample into a held-out test or verified independent human validation.
Neither step verifies all 1,950 responses or
all dataset sources. The main corpus also includes all 50 pilot claims used to
develop answer aliases.

Supplementary acceptance ranges preserve unreviewed automatic CORRECT labels
and determinate semantic decisions while varying unresolved cases. They are
conditional assignment ranges, not confidence intervals or revised primary
ground truth. The paper keeps these qualifications alongside its findings.

AI assisted with analysis and drafting. The AI semantic reference and
author-reported review provenance are separate from that general assistance.

## Article build

The article is compiled with Tectonic 0.17.0+20260731 and has eight pages
including references. `paper_build.json` records the latest build and hashes;
the technical verification receipt records visual checks. The official December 2024
`sn-jnl` class is embedded unchanged; this PDF is actual TeX output.

The Codex editor's separate preview compiler still encounters a Windows process
permission error. This preview issue does not invalidate the successful terminal
compilation. Keep editing the existing `paper.tex` source; no replacement
document is required.

Install the Python dependencies and a working [Tectonic executable](https://tectonic-typesetting.github.io/book/latest/installation/), then run from the repository root:

```sh
python -m pip install -r submission/requirements-submission.txt
python submission/build_paper.py --compiler /path/to/tectonic
```

`--compiler` is optional when `tectonic` is on PATH or `TECTONIC` points to it.
The first build may download public TeX packages. `--tex-only` regenerates the
editable source without replacing the PDF. No model requests occur. The builder
stages compilation and only replaces the final PDF after compilation and page
count checks pass. It records hashes in `paper_build.json`.

## Course requirements

| Requirement | Artifact or status |
| --- | --- |
| Precise question and methodology | Paper sections 1 and 2 |
| Dataset, metrics and experiments | Paper sections 2 and 3; saved data and reports |
| Relevant literature | Eight references, including the closest confidence study |
| Critical discussion and future work | Paper section 4 |
| Four-to-eight-page article in the linked template | Official-template LaTeX compilation verified; eight pages |
| Modular code and reproducibility | `../src/sycophancy/`, tests and `../RELEASE.md` |
| GitHub access | [Project repository](https://github.com/anastasiakhromova/sycophancy-confidence-final) |
| Ten-minute English presentation | Replacement presentation in preparation; not included in this package |
| Reviewer provenance | Methods distinguish AI judgments, author approval and second review |
| Student understanding | Defense guide; presentation rehearsal pending |
| Custom-topic approval | Confirmed on 14 October 2026; `../reports/topic_approval.json` |
| Registration and defense appointment | Student-managed through the course's Ariel procedure |

The agreed topic changes user-confidence wording; it does not claim to implement
P9's base-versus-instruction-tuned intervention. The separate challenge follow-up
adds knowledge controls and alternative cues, with its own paid-call records.
Independent held-out human multiclass validation is still future work. The
additional automated assessments do not supply that validation.
