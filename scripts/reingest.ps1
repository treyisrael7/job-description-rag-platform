# Re-ingest a document (deletes chunks, re-runs ingestion)
# Usage: .\scripts\reingest.ps1
#        .\scripts\reingest.ps1 -docId "uuid"

param([string]$docId)

$demoKey = "euo2ciunG6xxXmjbXj1q8X1P"
$api = "http://127.0.0.1:8000"
if (-not $docId) {
    $docIdFile = Join-Path $PSScriptRoot ".last-document-id"
    if (Test-Path $docIdFile) {
        $docId = (Get-Content $docIdFile -Raw).Trim()
    }
}
if (-not $docId) {
    Write-Error "Run test-upload.ps1 first, or pass -docId `"uuid`""
    exit 1
}

$userId = "11111111-1111-1111-1111-111111111111"

Write-Host "Re-ingesting document $docId..." -ForegroundColor Cyan
$bodyFile = [System.IO.Path]::GetTempFileName()
[System.IO.File]::WriteAllText($bodyFile, (@{ user_id = $userId } | ConvertTo-Json -Compress), [System.Text.UTF8Encoding]::new($false))
try {
    $resp = curl.exe -s -X POST -H "Content-Type: application/json" -H "x-demo-key: $demoKey" -d "@$bodyFile" "$api/documents/$docId/reingest"
    $r = $resp | ConvertFrom-Json
    Write-Host "Status: $($r.status). Wait a few seconds, then run test-retrieve.ps1." -ForegroundColor Green
} catch {
    Write-Host "Error: $_" -ForegroundColor Red
    exit 1
} finally {
    Remove-Item $bodyFile -Force -ErrorAction SilentlyContinue
}
