param(
    [Parameter(Mandatory=$true)][string]$Email,
    [ValidateRange(1,65535)][int]$Port=8000,
    [switch]$Transformer,
    [switch]$Background
)
$ErrorActionPreference='Stop'
if ($Email -notmatch '^[A-Za-z0-9._%+-]+@gmail\.com$') { throw 'Enter your Gmail address.' }
$running=$false
try {
    $health=Invoke-RestMethod "http://127.0.0.1:$Port/api/status" -TimeoutSec 2
    $running=$health.authentication -eq $true
} catch {}
if ($running) { throw 'Stop the existing Folio server first, then rerun this helper to apply email settings.' }
$appPassword=Read-Host 'Google App Password (not your normal Google password)' -AsSecureString
$previous=@{}
$keys=@('FOLIO_SMTP_HOST','FOLIO_SMTP_PORT','FOLIO_SMTP_SECURITY','FOLIO_SMTP_USERNAME','FOLIO_SMTP_PASSWORD','FOLIO_SMTP_FROM')
foreach ($key in $keys) { $previous[$key]=[Environment]::GetEnvironmentVariable($key,'Process') }
try {
    $credential=New-Object System.Net.NetworkCredential -ArgumentList '',$appPassword
    $env:FOLIO_SMTP_HOST='smtp.gmail.com'
    $env:FOLIO_SMTP_PORT='587'
    $env:FOLIO_SMTP_SECURITY='starttls'
    $env:FOLIO_SMTP_USERNAME=$Email
    $env:FOLIO_SMTP_FROM=$Email
    $env:FOLIO_SMTP_PASSWORD=$credential.Password.Replace(' ','')
    if (-not $env:FOLIO_SMTP_PASSWORD) { throw 'An App Password is required for Gmail delivery.' }
    & (Join-Path $PSScriptRoot 'start.ps1') -Port $Port -Transformer:$Transformer -Background:$Background
} finally {
    foreach ($key in $keys) { [Environment]::SetEnvironmentVariable($key,$previous[$key],'Process') }
    $credential=$null
    $appPassword.Dispose()
}
