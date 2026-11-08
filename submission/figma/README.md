# Figma research presentation — resume package

**The remote Figma presentation is incomplete.** The file, two pages, 23 foundation
variables and eight text styles were created successfully. No complete slide frame
or reusable component has a successful confirmation. A component creation call
and a tiny read-only call both stalled without a result. Metadata access separately
hit the Starter-plan MCP limit. No screenshot or visual QA can be claimed.

File: [User Confidence vs. LLM Truthfulness](https://www.figma.com/design/RdoATCF8bAmRx5ZTpTc6Hl).
Detailed evidence is in `manifest.json`. Do not present this link as a finished deck.
The submission's local editable research presentation is the usable presentation
while remote Figma access remains unavailable.

## Canonical source and safe continuation

1. Restore normal Figma MCP access. Inspect the existing file before any write,
   because the interrupted component write may have partially applied.
2. Read the mandatory `figma-use`, `figma-generate-library`, and
   `figma-generate-design` skills. Use the
   existing file key `RdoATCF8bAmRx5ZTpTc6Hl`; do not create a replacement file.
3. Inspect and repair any partial `Research / ...` components on `Design System`.
   `02_components_resume.js` preserves existing named components, so it does not
   silently discard user edits or overwrite an unknown partial state.
4. Execute `02_components_resume.js` through `use_figma`, then
   `03_slides_resume.js` in the same file. Save the returned IDs. The scripts use
   native text, vectors, shapes, auto-layout and component instances; they do not
   flatten slide screenshots. Font properties are assigned directly, avoiding
   per-text asynchronous style application.
5. Inspect all 13 frames at readable resolution, fix clipping/overlap, verify
   every chart value and limitation, and save screenshots and returned node IDs.
   Only then change the manifest status to complete.

The resume sources were syntax checked locally, **not executed or visually
verified remotely**. The `01*` files are historical attempts and are not the
canonical continuation path. The initial script's sample text is superseded by
the exact claim and `CONFIGURED MODEL` label in the canonical files.

## Slide structure

| Frame | Main message | Evidence status |
|---|---|---|
| 01_Title | User Confidence vs. LLM Truthfulness | Study title; author name omitted because not supplied |
| 02_Problem | Helpful versus agreeable | Illustrative question; no invented model answer |
| 03_Research_Question | Change confidence, measure behaviour | Actual research question |
| 04_Manipulation | Same claim; three cues | Exact prompts and geo_002 wording |
| 05_Knowledge_Baseline | Agreement does not establish knowledge | Clearly marked proposed control, not run |
| 06_Dataset | 150 claims across five domains | Real corpus; 88 easy / 62 medium rubric labels |
| 07_Pipeline | Fixed prompts to paired evidence | Actual workflow; future knowledge branch separated |
| 08_Models | Three configured IDs, one protocol | Actual configurations and request counts |
| 09_Metrics | Operationalize and audit sycophancy | Frozen automatic-label definitions |
| 10_Results | No main automatic acceptance labels | Real all-zero main chart; honest bootstrap caveat |
| 11_Statistics | Claim-paired inference | Real correction contrasts and 95% intervals |
| 12_Error_Analysis | Measurement affects the apparent result | Real pattern counts and AI-review findings |
| 13_Conclusion | No convincing general effect in this setting | Cautious synthesis and limitations |

There are **no fabricated result placeholders**. Data collection is complete for
the planned pilot/main/repeatability runs. A knowledge-only control would require
a newly authorized study; it cannot be filled from existing responses. An author
name still needs to be supplied before final submission. Independent human
adjudication was not performed and is not implied.

`speaking_script_en.md` provides a 600-second talk matching this 13-slide sequence.
