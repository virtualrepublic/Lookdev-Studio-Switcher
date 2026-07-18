<#
.SYNOPSIS
    Commit, tag and ZIP-snapshot a new version in one step.

.DESCRIPTION
    Run from the repository root. Stages all tracked changes, commits them,
    creates an annotated git tag vX.Y.Z, and writes a clean ZIP of the tagged
    tree into _BACKUP_\ (built from git, so only tracked files are included --
    no .blend, no snapshots).

.EXAMPLE
    pwsh tools\new-release.ps1 -Version 1.1.0 -Message "FRAME uses 200mm"
#>
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][string]$Message
)

$ErrorActionPreference = 'Stop'

# Must be at the repo root (where .git lives).
if (-not (Test-Path '.git')) {
    throw "Run this from the repository root (the folder that contains .git)."
}

$tag = "v$Version"
if (git tag --list $tag) {
    throw "Tag $tag already exists. Pick a new version number."
}

Write-Host "==> Staging and committing..." -ForegroundColor Cyan
git add -A
# Only commit if there is something staged; a docs-only retag is still allowed.
if (git diff --cached --quiet) {
    Write-Host "    (nothing to commit -- tagging the current HEAD)" -ForegroundColor Yellow
} else {
    git commit -m "$Version - $Message"
}

Write-Host "==> Tagging $tag..." -ForegroundColor Cyan
git tag -a $tag -m "$tag - $Message"

Write-Host "==> Writing ZIP snapshot..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path '_BACKUP_' | Out-Null
$zip = "_BACKUP_\lookdev-switcher_$tag.zip"
git archive --format=zip -o $zip $tag

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "  Commit : $(git rev-parse --short HEAD)"
Write-Host "  Tag    : $tag"
Write-Host "  Backup : $zip"
Write-Host ""
Write-Host "Remember to add the changes to CHANGELOG.md before releasing." -ForegroundColor Yellow
