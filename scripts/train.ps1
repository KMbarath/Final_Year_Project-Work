param([switch]$Transformer)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:HF_HOME = Join-Path (Get-Location) '.cache/huggingface'
$pythonPath = Join-Path (Get-Location) '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { $pythonPath = 'python' }
if (-not (Test-Path -LiteralPath 'data/synthetic/documents.csv')) {
    & $pythonPath -m training.baseline --generate-demo
} else {
    & $pythonPath -m training.baseline
}
if ($LASTEXITCODE -ne 0) { throw 'Baseline training failed.' }
if ($Transformer) {
    & $pythonPath -m training.transformer
    if ($LASTEXITCODE -ne 0) { throw 'Transformer training failed.' }
}
& $pythonPath -m training.evaluate
