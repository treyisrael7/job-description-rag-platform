# JD ingestion stats - total, low_signal, embedded, pages, section_type breakdown
# Usage: .\scripts\chunk-stats.ps1
#        .\scripts\chunk-stats.ps1 -docId "uuid"

param([string]$docId)

$demoKey = "euo2ciunG6xxXmjbXj1q8X1P"
$userId = "11111111-1111-1111-1111-111111111111"
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

try {
    $resp = curl.exe -s -H "x-demo-key: $demoKey" "$api/documents/$docId/chunk-stats?user_id=$userId"
    $r = $resp | ConvertFrom-Json
    Write-Host "total_chunks:      $($r.total_chunks)"
    Write-Host "low_signal_chunks: $($r.low_signal_chunks)"
    Write-Host "embedded_chunks:   $($r.embedded_chunks)"
    Write-Host "pages_covered:     $($r.pages_covered)"
    Write-Host "avg_chunk_length:  $($r.avg_chunk_length)"
    Write-Host "min_chunk_length:  $($r.min_chunk_length)"
    Write-Host "max_chunk_length:  $($r.max_chunk_length)"
    if ($r.section_type_breakdown) {
        Write-Host "section_type_breakdown:" -ForegroundColor Cyan
        $r.section_type_breakdown.PSObject.Properties | ForEach-Object { Write-Host "  $($_.Name): $($_.Value)" }
    }
} catch {
    # Fallback to Python script if API unavailable
    $pyScript = Join-Path (Split-Path $PSScriptRoot) "scripts" "chunk-stats.py"
    Push-Location (Join-Path (Split-Path $PSScriptRoot) "apps\api"); try { python $pyScript $docId } finally { Pop-Location }
}
