param([switch]$Transformer, [ValidateRange(1,65535)][int]$Port = 8000, [switch]$Background, [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
# Some local development shells inject a dead loopback proxy.  It prevents the
# explicitly configured translation provider from reaching its HTTPS endpoint.
foreach ($proxyVariable in 'HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy') {
    if ((Get-Item "Env:$proxyVariable" -ErrorAction SilentlyContinue).Value -match '^https?://127\.0\.0\.1:9/?$') {
        Remove-Item "Env:$proxyVariable" -ErrorAction SilentlyContinue
    }
}
$env:HF_HOME = Join-Path (Get-Location) '.cache/huggingface'
$pythonCandidates = @((Join-Path (Get-Location) '.venv/Scripts/python.exe'), (Get-Command python -ErrorAction SilentlyContinue).Source)
$venvConfig = Join-Path (Get-Location) '.venv/pyvenv.cfg'
if (Test-Path -LiteralPath $venvConfig) {
    $baseLine = Get-Content -LiteralPath $venvConfig | Where-Object { $_ -match '^home = ' } | Select-Object -First 1
    if ($baseLine) { $pythonCandidates += Join-Path ($baseLine.Substring(7)) 'python.exe' }
}
$pythonPath = $null
foreach ($candidate in ($pythonCandidates | Select-Object -Unique)) {
    if (-not $candidate -or -not (Test-Path -LiteralPath $candidate)) { continue }
    try {
        & $candidate -c "import fastapi, uvicorn, sklearn, pymupdf, multipart" 2>$null
        if ($LASTEXITCODE -eq 0) { $pythonPath = $candidate; break }
    } catch { continue }
}
if (-not $pythonPath) { throw 'Install project dependencies first: python -m pip install -e ".[training,dev]"' }
Write-Host "Using Python: $pythonPath"
if ($pythonPath -ne $pythonCandidates[0]) {
    Write-Warning 'The project virtual environment is incomplete. Using the installed Python environment; no environment files were changed.'
}
if (-not $env:FOLIO_PUBLIC_URL) { $env:FOLIO_PUBLIC_URL = "http://127.0.0.1:$Port" }
$voicePath = Join-Path (Get-Location) 'artifacts/voices/en_US-lessac-medium.onnx'
& $pythonPath -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('piper') else 1)"
$voiceInstalled = $LASTEXITCODE -eq 0
if ($voiceInstalled -and -not $env:FOLIO_PIPER_MODEL -and (Test-Path -LiteralPath $voicePath)) {
    $env:FOLIO_PIPER_MODEL = $voicePath
}
$embeddingCache = Join-Path (Get-Location) '.cache/huggingface/hub/models--BAAI--bge-small-en-v1.5'
& $pythonPath -c "import importlib.util,sys; sys.exit(0 if all(importlib.util.find_spec(m) for m in ['sentence_transformers','faiss']) else 1)"
$semanticInstalled = $LASTEXITCODE -eq 0
if ($semanticInstalled -and -not $env:FOLIO_EMBEDDING_MODEL -and (Test-Path -LiteralPath $embeddingCache)) {
    $env:FOLIO_EMBEDDING_MODEL = 'BAAI/bge-small-en-v1.5'
}
if ($Transformer) {
    $env:FOLIO_CLASSIFIER_BACKEND = 'transformer'
    $env:FOLIO_CLASSIFIER = Join-Path (Get-Location) 'artifacts/minilm'
}
if ($CheckOnly) { Write-Host "Folio startup preflight passed. No server was launched."; return }
if ($Background) {
    $url = "http://127.0.0.1:$Port"
    $alreadyRunning = $false
    try {
        $health = Invoke-RestMethod "$url/api/status" -TimeoutSec 2
        $alreadyRunning = $health.authentication -eq $true
    } catch {}
    if ($alreadyRunning) {
        Write-Host "Folio is already running at $url"
        return
    }
    $runtimeFolder = Join-Path (Get-Location) 'artifacts/server'
    New-Item -ItemType Directory -Force -Path $runtimeFolder | Out-Null
    $logStamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $stdoutPath = Join-Path $runtimeFolder "$logStamp.stdout.log"
    $stderrPath = Join-Path $runtimeFolder "$logStamp.stderr.log"
    $serverProcess = Start-Process -FilePath $pythonPath -ArgumentList @('-m','uvicorn','folio.api:app','--host','127.0.0.1','--port',"$Port") -WorkingDirectory (Get-Location).Path -WindowStyle Hidden -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        $serverProcess.Refresh()
        if ($serverProcess.HasExited) {
            throw "Folio exited during startup. Check $stderrPath"
        }
        try {
            $health = Invoke-RestMethod "$url/api/status" -TimeoutSec 2
            if ($health.authentication -eq $true) {
                $serverProcess.Id | Set-Content -LiteralPath (Join-Path $runtimeFolder "server-$Port.pid")
                Write-Host "Folio is running at $url (PID $($serverProcess.Id)). Logs: $runtimeFolder"
                return
            }
        } catch {}
        Start-Sleep -Milliseconds 500
    }
    throw "Folio startup has not completed. Check $stderrPath"
}
Write-Host "Keep this terminal open while using Folio. Use -Background to run it independently."
& $pythonPath -m uvicorn folio.api:app --host 127.0.0.1 --port $Port
if ($LASTEXITCODE -ne 0) { throw "Folio stopped with exit code $LASTEXITCODE." }
