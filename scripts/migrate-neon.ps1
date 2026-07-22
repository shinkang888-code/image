# Apply Lexi IPlant Neon schema
# Usage: .\scripts\migrate-neon.ps1
param(
  [string]$DatabaseUrl = $env:DATABASE_URL
)
$ErrorActionPreference = "Stop"
if (-not $DatabaseUrl) { throw "Set DATABASE_URL first (neonctl connection-string)" }
$sqlFile = Join-Path (Split-Path -Parent $PSScriptRoot) "sql\001_iplant.sql"
Write-Host "Applying $sqlFile"
if (Get-Command psql -ErrorAction SilentlyContinue) {
  psql $DatabaseUrl -f $sqlFile
} else {
  Write-Host "psql not found — paste sql/001_iplant.sql in Neon SQL Editor"
  Get-Content $sqlFile
}
