param(
 [string]$RuntimeRoot = (Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies'),
 [string]$SkillDirectory = (Join-Path $env:USERPROFILE '.codex/plugins/cache/openai-primary-runtime/presentations/26.1013.11914/skills/presentations'),
 [string]$FinalFileName = 'research_presentation.pptx'
)
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
if([IO.Path]::GetFileName($FinalFileName) -ne $FinalFileName){throw 'FinalFileName must be a filename.'}
$finalDeck=Join-Path (Join-Path $projectRoot 'submission') $FinalFileName
if(Test-Path -LiteralPath $finalDeck){throw 'Choose a new FinalFileName; existing presentations are preserved.'}
$nodeExe=Join-Path $RuntimeRoot 'node/bin/node.exe'
$pythonExe=Join-Path $RuntimeRoot 'python/python.exe'
$skillTools=Join-Path $SkillDirectory 'container_tools'
$buildDir=Join-Path $projectRoot 'build/research-presentation'
$env:ARTIFACT_RUNTIME_ROOT=$RuntimeRoot
$env:PRESENTATION_SKILL_DIR=$SkillDirectory
$env:RUNTIME_NODE_MODULES=Join-Path $RuntimeRoot 'node/node_modules'
& $nodeExe (Join-Path $PSScriptRoot 'build_research_presentation.mjs')
if($LASTEXITCODE -ne 0){throw 'Export failed.'}
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$portableDeck=Join-Path $buildDir "portable-$stamp.pptx"
$snapshotReceipt=Join-Path $buildDir "chart-snapshot-$stamp.json"
& $pythonExe -B (Join-Path $skillTools 'materialize_literal_chart_workbooks.py') (Join-Path $buildDir 'candidate.pptx') $portableDeck --workspace $projectRoot --receipt $snapshotReceipt
if($LASTEXITCODE -ne 0){throw 'Chart workbook materialization failed.'}
function Invoke-ResearchValidator([string]$ScriptName,[string]$ReportName,[string[]]$ValidatorArguments){
 $result=& $pythonExe -B (Join-Path $skillTools $ScriptName) $portableDeck @ValidatorArguments
 $code=$LASTEXITCODE
 $result | Set-Content -LiteralPath (Join-Path $buildDir "$ReportName.json") -Encoding utf8
 if($code -ne 0){$result | Write-Output;throw "Validator failed: $ScriptName"}
}
Invoke-ResearchValidator 'inspect_presentation_package_integrity.py' 'integrity' @('--fail-on-findings')
Invoke-ResearchValidator 'inspect_presentation_layout_geometry.py' 'layout' @('--fail-on-findings','--expected-slide-size-emu','12192000,6858000','--expected-slide-count','14','--validate-bullet-geometry','--validate-heading-fit','--require-native-table-slide','8','--require-native-table-slide','11','--require-native-table-slide','12','--require-native-table-slide','14','--approved-font-family','Arial')
Invoke-ResearchValidator 'native_quantitative_chart_gate.py' 'native-chart' @('--expected-chart-slides','6,10','--target-application','portable','--require-embedded-workbook-slide','6','--require-embedded-workbook-slide','10')
Invoke-ResearchValidator 'native_chart_title_gate.py' 'chart-title' @()
Invoke-ResearchValidator 'native_table_arithmetic_gate.py' 'table-arithmetic' @('--fail-on-findings')
Copy-Item -LiteralPath $portableDeck -Destination $finalDeck
& $nodeExe (Join-Path $skillTools 'render_presentation.mjs') --input $finalDeck --output_dir (Join-Path $buildDir 'final-render')
if($LASTEXITCODE -ne 0){throw 'Final-file import/render failed.'}
$sourceHash=(Get-FileHash -LiteralPath $portableDeck -Algorithm SHA256).Hash
$finalHash=(Get-FileHash -LiteralPath $finalDeck -Algorithm SHA256).Hash
if($sourceHash -ne $finalHash){throw 'Final file differs from validated source.'}
[ordered]@{file=$finalDeck;sha256=$finalHash.ToLowerInvariant();slide_count=14;automated_checks='passed';rendered_slides=14;native_chart_count=4;native_table_count=4;native_powerpoint_open_verified=$false;visual_review='pending';validation_method='Unchanged bundled validators invoked directly because Node spawnSync(Python) was blocked in the original Windows environment.'} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $buildDir 'final-qa.json') -Encoding utf8
Write-Output "Created $finalDeck. Inspect all final-render slides before delivery."
