# Research presentation source

The deck uses `@oai/artifact-tool` JavaScript, native PowerPoint charts, editable tables and connected diagram shapes. `content_spec.json` records the study content. `validation_update.mjs` applies the current validation results consistently to both presentation variants and their notes. Rebuilding requires `reports/reviewer_validation/summary.json`. The builder also generates `../research_speaking_script_en.md` with a 600-second plan.

The local design uses Arial because neither Inter nor Aptos was available in the rendering runtime. It uses ivory `#F5F3EC`, ink `#171916`, and lime `#C7F83E`.

## Rebuild

The bundled Codex artifact runtime and presentations skill are prerequisites. They are external tools, not vendored in this repository. The saved PPTX does not require them to open or edit.

On Windows PowerShell:

```powershell
./rebuild_research_presentation.ps1 -RuntimeRoot 'PATH/TO/dependencies' -SkillDirectory 'PATH/TO/skills/presentations' -FinalFileName 'research_presentation-rebuilt.pptx'
```

The defaults locate the original bundle under the current user's profile. Specify the parameters for another location or bundle version. The command refuses to overwrite an existing deck. It exports a draft, embeds snapshots of complete chart data, runs the unchanged bundled integrity/layout/chart/table validators, then imports and renders the output. Check every rendered slide after rebuilding.

For direct JavaScript export, set `ARTIFACT_RUNTIME_ROOT` and `PRESENTATION_SKILL_DIR`, then run `build_research_presentation.mjs` with the bundled Node executable. A direct export only creates a draft in `build/research-presentation`; use the PowerShell workflow for validation and final output.

The separate Python validator calls handle a Windows environment limitation that blocked nested Python processes inside the JavaScript finalizer. No validator code is changed. No paid API calls occur.

## Evidence boundaries

There are 13 main slides in the requested order. The knowledge-only baseline is proposed and unrun. Primary charts show zero frozen automatic sycophancy labels and explicitly describe the degenerate empirical intervals. The AI semantic reference is separate from the frozen primary labels. The author approved it and reports independent second-reviewer agreement on all 241 items. Original reviewer exports are unavailable, so independence, full agreement and inter-rater reliability are unverified. Reference agreement uses 231 determinate CORRECT references and excludes ten unresolved references. Version two abstentions count as nonmatches in overall reference agreement. These selected development examples do not establish population accuracy or sycophancy recall. All source paths in notes are relative to the project root.
