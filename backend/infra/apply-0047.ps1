# Apply migration 0047 to the production Supabase database.
#
# Run this from the repository root on the machine that has .supabase-keys/.
# It is safe to run twice: every statement in 0047 is guarded with
# `if exists` / `if not exists`, and each UPDATE carries a WHERE so a second
# run rewrites no rows.
#
# Why a script rather than a one-liner: `Get-Content -Raw` piped into
# `ConvertTo-Json` serialises on this PowerShell as {"query":{"value":"..."}}
# rather than {"query":"..."}, which the API rejects. ReadAllText avoids that.

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$root       = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$projectRef = 'onwijviiwtuwldjmqoam'
$tokenPath  = Join-Path $root '.supabase-keys\access-token.pem'
$sqlPath    = Join-Path $root 'backend\infra\migrations\0047_mcp_engine_replacement.sql'

$token = [System.IO.File]::ReadAllText($tokenPath).Trim()
$sql   = [System.IO.File]::ReadAllText($sqlPath)
$body  = @{ query = $sql } | ConvertTo-Json -Compress

Write-Host "Applying 0047 ($($sql.Length) chars) to project $projectRef ..."

try {
    $response = Invoke-RestMethod -Method Post `
        -Uri "https://api.supabase.com/v1/projects/$projectRef/database/query" `
        -Headers @{ Authorization = "Bearer $token" } `
        -ContentType 'application/json' `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
    Write-Host "OK. Migration applied." -ForegroundColor Green
    $response | ConvertTo-Json -Depth 4
}
catch {
    Write-Host "FAILED." -ForegroundColor Red
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        Write-Host $reader.ReadToEnd()
    }
    else {
        Write-Host $_.Exception.Message
    }
    exit 1
}
