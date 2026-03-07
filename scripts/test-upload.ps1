# JD upload + ingest flow (S3) - optimized for Job Description PDFs
# Usage: Edit $pdfPath below, then run: .\scripts\test-upload.ps1
# Uses curl.exe (avoids PowerShell Invoke-RestMethod "connection closed" with Docker on Windows)

$demoKey = "euo2ciunG6xxXmjbXj1q8X1P"
$pdfPath = "C:\Users\Owner\Downloads\Thermo_Fisher_AI_Engineer_Job_Description.pdf"   # <-- EDIT: path to JD PDF

if (-not (Test-Path $pdfPath)) {
    Write-Error "PDF not found: $pdfPath"
    exit 1
}

$api = "http://127.0.0.1:8000"
$userId = "11111111-1111-1111-1111-111111111111"
$fileSize = (Get-Item $pdfPath).Length
# Write JSON to temp file (avoids PowerShell mangling + BOM; use ASCII to prevent UTF-8 BOM)
$presignBody = @{ user_id = $userId; filename = "test.pdf"; content_type = "application/pdf"; file_size_bytes = $fileSize } | ConvertTo-Json -Compress
$presignFile = [System.IO.Path]::GetTempFileName()
[System.IO.File]::WriteAllText($presignFile, $presignBody, [System.Text.UTF8Encoding]::new($false))

# Pre-flight: check API is reachable
$health = curl.exe -s -o NUL -w "%{http_code}" "$api/health"
if ($health -ne "200") {
    Write-Error "API not reachable (health=$health). Start with: docker compose up -d"
    exit 1
}

Write-Host "1. Presign..." -ForegroundColor Cyan
$presignResp = curl.exe -s -w "`n%{http_code}" -X POST -H "Content-Type: application/json" -H "x-demo-key: $demoKey" -d "@$presignFile" "$api/documents/presign"
Remove-Item $presignFile -Force -ErrorAction SilentlyContinue
$presignParts = $presignResp -split "`n"
$presignBodyResp = $presignParts[0..($presignParts.Count-2)] -join "`n"
$presignStatus = $presignParts[-1]
$r = $presignBodyResp | ConvertFrom-Json -ErrorAction SilentlyContinue
if (-not $r -or -not $r.upload_url) {
    Write-Host "Presign response (status=$presignStatus): $presignBodyResp" -ForegroundColor Red
    Write-Error "Presign failed. Check DEMO_KEY in .env matches script, or API logs."
    exit 1
}
Write-Host "   document_id: $($r.document_id)" -ForegroundColor Gray
Write-Host "   s3_key: $($r.s3_key)" -ForegroundColor Gray

Write-Host "2. Upload to S3 (presigned URL)..." -ForegroundColor Cyan
curl.exe -s -X PUT -H "Content-Type: application/pdf" --data-binary "@$pdfPath" $r.upload_url | Out-Null
Write-Host "   OK" -ForegroundColor Green

Write-Host "3. Confirm..." -ForegroundColor Cyan
$confirmFile = [System.IO.Path]::GetTempFileName()
[System.IO.File]::WriteAllText($confirmFile, (@{ user_id = $userId; document_id = $r.document_id; s3_key = $r.s3_key } | ConvertTo-Json -Compress), [System.Text.UTF8Encoding]::new($false))
curl.exe -s -X POST -H "Content-Type: application/json" -H "x-demo-key: $demoKey" -d "@$confirmFile" "$api/documents/confirm" | Out-Null
Remove-Item $confirmFile -Force -ErrorAction SilentlyContinue
Write-Host "   OK" -ForegroundColor Green

Write-Host "4. Ingest..." -ForegroundColor Cyan
$ingestFile = [System.IO.Path]::GetTempFileName()
[System.IO.File]::WriteAllText($ingestFile, (@{ user_id = $userId } | ConvertTo-Json -Compress), [System.Text.UTF8Encoding]::new($false))
$ingestResp = curl.exe -s -X POST -H "Content-Type: application/json" -H "x-demo-key: $demoKey" -d "@$ingestFile" "$api/documents/$($r.document_id)/ingest"
Remove-Item $ingestFile -Force -ErrorAction SilentlyContinue
$ingest = $ingestResp | ConvertFrom-Json
Write-Host "   $($ingest | ConvertTo-Json)" -ForegroundColor Green

$docIdFile = Join-Path $PSScriptRoot ".last-document-id"
$r.document_id | Set-Content -Path $docIdFile -NoNewline
Write-Host "`nDone. document_id saved for test-retrieve.ps1. Doc goes processing -> ready in a few seconds." -ForegroundColor Yellow
Write-Host "Run: .\scripts\test-retrieve.ps1 (JD retrieval test after doc is ready)" -ForegroundColor Gray
