# Grounded Q&A test - run after test-upload.ps1
# Usage: .\scripts\test-ask.ps1
#        .\scripts\test-ask.ps1 -docId "uuid-here" -question "What is the salary?"

param([string]$docId, [string]$question)

$demoKey = "euo2ciunG6xxXmjbXj1q8X1P"
$api = "http://127.0.0.1:8000"
if (-not $docId) {
    $docIdFile = Join-Path $PSScriptRoot ".last-document-id"
    if (Test-Path $docIdFile) {
        $docId = (Get-Content $docIdFile -Raw).Trim()
    }
}
if (-not $docId -or $docId -eq "YOUR_READY_DOCUMENT_ID") {
    Write-Error "Run test-upload.ps1 first, then test-ask.ps1. Or pass -docId `"uuid`""
    exit 1
}
$userId = "11111111-1111-1111-1111-111111111111"

if (-not $question) {
    $question = "What are the key responsibilities?"
}

$bodyFile = [System.IO.Path]::GetTempFileName()
$bodyJson = @{ user_id = $userId; document_id = $docId; question = $question } | ConvertTo-Json -Compress
[System.IO.File]::WriteAllText($bodyFile, $bodyJson, [System.Text.UTF8Encoding]::new($false))

try {
    $resp = curl.exe -s -w "`n%{http_code}" -X POST -H "Content-Type: application/json" -H "x-demo-key: $demoKey" -d "@$bodyFile" "$api/ask"
    $respParts = $resp -split "`n"
    $respBody = $respParts[0..($respParts.Count-2)] -join "`n"
    $respStatus = $respParts[-1]
    if ($respStatus -ne "200") {
        Write-Host "API error (status=$respStatus): $respBody" -ForegroundColor Red
        exit 1
    }
    $r = $respBody | ConvertFrom-Json
    Write-Host "Question: $question" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Answer:" -ForegroundColor Cyan
    Write-Host $r.answer -ForegroundColor White
    Write-Host ""
    if ($r.citations -and $r.citations.Count -gt 0) {
        Write-Host "Citations ($($r.citations.Count)):" -ForegroundColor Gray
        foreach ($c in $r.citations) {
            $snip = if ($c.snippet) { $c.snippet.Substring(0, [Math]::Min(100, $c.snippet.Length)) + "..." } else { "" }
            Write-Host "  [$($c.chunk_id)] p.$($c.page_number): $snip" -ForegroundColor DarkGray
        }
    } else {
        Write-Host "Citations: (none)" -ForegroundColor Gray
    }
} catch {
    Write-Host "Error: $_" -ForegroundColor Red
    exit 1
} finally {
    Remove-Item $bodyFile -Force -ErrorAction SilentlyContinue
}
