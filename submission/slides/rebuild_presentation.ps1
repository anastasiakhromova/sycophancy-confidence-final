# Rebuilds the deck with the bundled artifact-tool, then invokes the unchanged
# bundled Python validators directly. This avoids a Windows runtime restriction
# that blocked Node spawnSync(Python) in the JS finalizer during the original build.
# The output is a new file. No paid API calls or model generation occur.
param(
    [string]$FinalFileName = 'presentation-rebuilt.pptx',
    [string]$RuntimeRoot = (Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies'),
    [string]$PresentationSkill = (Join-Path $env:USERPROFILE '.codex/plugins/cache/openai-primary-runtime/presentations/26.1013.11914/skills/presentations')
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$presentationNode = Join-Path $runtimeRoot 'node/bin/node.exe'
$presentationPython = Join-Path $runtimeRoot 'python/python.exe'
$presentationTools = Join-Path $presentationSkill 'container_tools'
if (-not (Test-Path -LiteralPath $presentationNode)) { throw 'Pass -RuntimeRoot from the local Codex workspace dependency loader.' }
if (-not (Test-Path -LiteralPath $presentationTools)) { throw 'Pass -PresentationSkill for the installed Presentations skill.' }
$presentationBuild = Join-Path $projectRoot 'build/presentation'
$finalPresentation = Join-Path (Join-Path $projectRoot 'submission') $FinalFileName
if ([IO.Path]::GetFileName($FinalFileName) -ne $FinalFileName) { throw 'Use a filename, not a directory path.' }
if (Test-Path -LiteralPath $finalPresentation) { throw 'Choose a new FinalFileName. The rebuild does not overwrite existing decks.' }
$localNodeModules = Join-Path $PSScriptRoot 'node_modules'
if (-not (Test-Path -LiteralPath $localNodeModules)) {
    New-Item -ItemType Junction -Path $localNodeModules -Target (Join-Path $runtimeRoot 'node/node_modules') | Out-Null
}
$env:PRESENTATION_EXPORT_ONLY = '1'
$env:PRESENTATION_SKILL_DIR = $presentationSkill
$env:PRESENTATION_PYTHON = $presentationPython
$env:RUNTIME_NODE_MODULES = Join-Path $runtimeRoot 'node/node_modules'
& $presentationNode (Join-Path $PSScriptRoot 'build_presentation.mjs')
if ($LASTEXITCODE -ne 0) { throw 'Draft export failed.' }
$buildStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$portableDeck = Join-Path $presentationBuild "portable-$buildStamp.pptx"
& $presentationPython -B (Join-Path $presentationTools 'materialize_literal_chart_workbooks.py') (Join-Path $presentationBuild 'candidate.pptx') $portableDeck --workspace $projectRoot --receipt (Join-Path $presentationBuild "snapshot-$buildStamp.json")
if ($LASTEXITCODE -ne 0) { throw 'Chart workbook materialization failed.' }
function Invoke-PresentationValidator([string]$ScriptName, [string[]]$ValidatorArguments) {
    $report = & $presentationPython -B (Join-Path $presentationTools $ScriptName) $portableDeck @ValidatorArguments
    $validatorExit = $LASTEXITCODE
    $report | Set-Content -LiteralPath (Join-Path $presentationBuild "$buildStamp-$ScriptName.json") -Encoding utf8
    if ($validatorExit -ne 0) { throw "Validator failed: $ScriptName" }
}
Invoke-PresentationValidator 'inspect_presentation_package_integrity.py' @('--fail-on-findings')
$layoutArguments = @('--fail-on-findings','--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit','--approved-font-family','Calibri')
foreach ($owner in @(3,4,5,7,8,11,12,14)) { $layoutArguments += @('--require-native-table-slide',"$owner") }
Invoke-PresentationValidator 'inspect_presentation_layout_geometry.py' $layoutArguments
Invoke-PresentationValidator 'native_quantitative_chart_gate.py' @('--expected-chart-slides','6','--target-application','portable','--require-embedded-workbook-slide','6')
Invoke-PresentationValidator 'native_chart_title_gate.py' @()
Invoke-PresentationValidator 'native_table_arithmetic_gate.py' @('--fail-on-findings')
Copy-Item -LiteralPath $portableDeck -Destination $finalPresentation
& $presentationNode (Join-Path $presentationTools 'render_presentation.mjs') --input $finalPresentation --output_dir (Join-Path $presentationBuild "render-$buildStamp")
if ($LASTEXITCODE -ne 0) { throw 'Final-file import/render failed.' }
Write-Output "Created $finalPresentation. Inspect the rendered slides before use."
