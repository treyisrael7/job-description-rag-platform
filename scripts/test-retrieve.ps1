# JD retrieval quality test - run after test-upload.ps1 (with a Job Description PDF)
# Usage: .\scripts\test-retrieve.ps1    (uses last doc from test-upload.ps1)
#        .\scripts\test-retrieve.ps1 -docId "uuid-here"

param([string]$docId)

$demoKey = "euo2ciunG6xxXmjbXj1q8X1P"
$api = "http://127.0.0.1:8000"
if (-not $docId) {
    $docIdFile = Join-Path $PSScriptRoot ".last-document-id"
    if (Test-Path $docIdFile) {
        $docId = (Get-Content $docIdFile -Raw).Trim()
    }
}
if (-not $docId -or $docId -eq "YOUR_READY_DOCUMENT_ID") {
    Write-Error "Run test-upload.ps1 first, then test-retrieve.ps1. Or pass -docId `"uuid`""
    exit 1
}
$userId = "11111111-1111-1111-1111-111111111111"

# Print chunk count and JD section breakdown
try {
    $statsResp = curl.exe -s -w "`n%{http_code}" -H "x-demo-key: $demoKey" "$api/documents/$docId/chunk-stats?user_id=$userId"
    $statsParts = $statsResp -split "`n"
    $statsBody = $statsParts[0..($statsParts.Count-2)] -join "`n"
    $statsStatus = $statsParts[-1]
    if ($statsStatus -eq "200") {
    $stats = $statsBody | ConvertFrom-Json
    Write-Host "Document chunks: $($stats.total_chunks) (low_signal: $($stats.low_signal_chunks), embedded: $($stats.embedded_chunks))" -ForegroundColor Cyan
    if ($stats.section_type_breakdown -and $stats.section_type_breakdown.PSObject.Properties.Count -gt 0) {
        Write-Host "Section breakdown:" -ForegroundColor Cyan
        $stats.section_type_breakdown.PSObject.Properties | ForEach-Object { Write-Host "  $($_.Name): $($_.Value)" -ForegroundColor Gray }
    }
    } else {
        Write-Host "Could not fetch chunk-stats (status=$statsStatus): $statsBody" -ForegroundColor Gray
    }
} catch {
    Write-Host "Could not fetch chunk-stats: $_" -ForegroundColor Gray
}
Write-Host ""

# JD-focused retrieval queries
$queries = @(
    "What are the required qualifications?",
    "What education is required?",
    "What are the key responsibilities?",
    "What tools and technologies are used?",
    @{ q = "What is the salary or compensation?"; include_low_signal = $true },
    "What is the work location?",
    @{ q = "What is the contact info or how to apply?"; include_low_signal = $true }
)

Write-Host "JD Retrieval test - document $docId`n" -ForegroundColor Cyan

foreach ($item in $queries) {
    $q = $item
    $queryText = if ($q -is [hashtable]) { $q.q } else { $q }
    $includeLow = if ($q -is [hashtable]) { $q.include_low_signal } else { $false }
    Write-Host "Query: $queryText" -ForegroundColor Yellow
    $bodyFile = [System.IO.Path]::GetTempFileName()
    $bodyJson = @{ user_id = $userId; document_id = $docId; query = $queryText; top_k = 6; include_low_signal = $includeLow } | ConvertTo-Json -Compress
    [System.IO.File]::WriteAllText($bodyFile, $bodyJson, [System.Text.UTF8Encoding]::new($false))
    try {
        $resp = curl.exe -s -w "`n%{http_code}" -X POST -H "Content-Type: application/json" -H "x-demo-key: $demoKey" -d "@$bodyFile" "$api/retrieve"
        $respParts = $resp -split "`n"
        $respBody = $respParts[0..($respParts.Count-2)] -join "`n"
        $respStatus = $respParts[-1]
        if ($respStatus -ne "200") {
            Write-Host "  API error (status=$respStatus): $respBody" -ForegroundColor Red
        } else {
        $r = $respBody | ConvertFrom-Json
        if (-not $r.chunks -or $r.chunks.Count -eq 0) {
            Write-Host "  (no chunks)" -ForegroundColor Gray
        } else {
            foreach ($c in $r.chunks) {
                $snip = if ($c.snippet) { $c.snippet.Substring(0, [Math]::Min(80, $c.snippet.Length)) } else { "" }
                $low = if ($c.is_low_signal) { " [LOW-SIGNAL]" } else { "" }
                $sec = if ($c.section_type) { " [$($c.section_type)]" } else { "" }
                Write-Host "  [p.$($c.page_number)] score=$($c.score)$sec$low $snip..." -ForegroundColor $(if ($c.is_low_signal) { "Red" } else { "Gray" })
            }
        }
        }
    } catch {
        Write-Host "  Error: $_" -ForegroundColor Red
    } finally {
        Remove-Item $bodyFile -Force -ErrorAction SilentlyContinue
    }
    Write-Host ""
}
