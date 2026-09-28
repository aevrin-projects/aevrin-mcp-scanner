# Apply one migration file to the production Supabase database.
#
#   powershell -ExecutionPolicy Bypass -File .\backend\infra\apply-migration.ps1 `
#     .\backend\infra\migrations\0048_registry.sql
#
# Run from the repository root on the machine that has .supabase-keys/. The
# token is read from that file and sent only to api.supabase.com; it is never
# printed. Migrations in this repository are written to be safe to re-run
# (`if not exists`, guarded updates), so applying one twice is harmless.
#
# Why a script rather than a one-liner: `Get-Content -Raw` piped into
# `ConvertTo-Json` serialises on Windows PowerShell 5.1 as
# {"query":{"value":"..."}} rather than {"query":"..."}, which the API
# rejects. ReadAllText avoids that.
#
# Order matters. A migration that adds columns the next build writes must be
# applied BEFORE that build deploys; /health reports the gap and the deploy
# rolls back otherwise. Read the migration's header before running it.

param(
    [Parameter(Mandatory = $true)]
    [string]$MigrationPath
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$root       = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$projectRef = 'onwijviiwtuwldjmqoam'
$tokenPath  = Join-Path $root '.supabase-keys\access-token.pem'
$sqlPath    = (Resolve-Path $MigrationPath).Path

# Only files from this repository's migration directory. The script sends
# whatever it reads to production as SQL, so a mistyped path must fail here
# rather than execute something else.
$migrations = (Resolve-Path (Join-Path $root 'backend\infra\migrations')).Path
if (-not $sqlPath.StartsWith($migrations, [System.StringComparison]::OrdinalIgnoreCase) -or
    -not $sqlPath.EndsWith('.sql', [System.StringComparison]::OrdinalIgnoreCase)) {
    Write-Host "Refusing: $sqlPath is not a .sql file in backend\infra\migrations." -ForegroundColor Red
    exit 1
}

$token = [System.IO.File]::ReadAllText($tokenPath).Trim()
$sql   = [System.IO.File]::ReadAllText($sqlPath)
$body  = @{ query = $sql } | ConvertTo-Json -Compress
$name  = Split-Path -Leaf $sqlPath

Write-Host "Applying $name ($($sql.Length) chars) to project $projectRef ..."

try {
    $response = Invoke-RestMethod -Method Post `
        -Uri "https://api.supabase.com/v1/projects/$projectRef/database/query" `
        -Headers @{ Authorization = "Bearer $token" } `
        -ContentType 'application/json' `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
    Write-Host "OK. $name applied." -ForegroundColor Green
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
