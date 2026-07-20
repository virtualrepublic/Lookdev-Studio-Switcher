<#
.SYNOPSIS
    Commit, tag, ZIP-snapshot and (optionally) publish a new version in one step.

.DESCRIPTION
    Run from the repository root. Stages all tracked changes, commits them,
    creates an annotated git tag vX.Y.Z, and writes a clean ZIP of the tagged
    tree into _BACKUP_\ (built from git, so only tracked files are included --
    no .blend, no snapshots).

    With -Publish it also does the GitHub side, which this script used to leave
    manual and which has been forgotten before:
      B. push the current branch and the tag to origin
      C. create the GitHub Release (a Release is a different object than a tag;
         the notes come from the matching CHANGELOG.md section)
      D. upload setup_lookdev_scene.py as the release asset -- the one file
         users download and run; every prior release carries it

    Guards before doing anything: refuses to release if setup_lookdev_scene.py
    does not already contain this version's bl_info tuple, i.e. it was not
    regenerated after the version bump.

.EXAMPLE
    # Local only: commit + tag + ZIP. Review, then re-run with -Publish.
    pwsh tools\new-release.ps1 -Version 1.2.0 -Message "Set Render Path button"

.EXAMPLE
    # Full release: local step + push + GitHub Release + asset upload.
    pwsh tools\new-release.ps1 -Version 1.2.0 -Message "Set Render Path button" -Publish
#>
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][string]$Message,
    [switch]$Publish
)

$ErrorActionPreference = 'Stop'

# Native commands (git/gh) do not throw on a non-zero exit; check it explicitly.
function Assert-LastExit([string]$what) {
    if ($LASTEXITCODE -ne 0) { throw "$what failed (exit $LASTEXITCODE)." }
}

# Pull the release notes for a version out of CHANGELOG.md: everything under the
# "## [X.Y.Z] ..." heading up to the next "## " heading, trailing rule stripped.
function Get-ChangelogNotes([string]$version) {
    if (-not (Test-Path 'CHANGELOG.md')) { return $null }
    $text = Get-Content 'CHANGELOG.md' -Raw
    $pattern = '(?ms)^\#\#\s*\[' + [regex]::Escape($version) + '\][^\n]*\n(.*?)(?=^\#\#\s)'
    $m = [regex]::Match($text, $pattern)
    if (-not $m.Success) { return $null }
    $body = $m.Groups[1].Value.TrimEnd()
    $body = $body -replace '\s*-{3,}\s*$', ''    # drop a trailing horizontal rule
    return $body.Trim()
}

# Must be at the repo root (where .git lives).
if (-not (Test-Path '.git')) {
    throw "Run this from the repository root (the folder that contains .git)."
}

$tag = "v$Version"
if (git tag --list $tag) {
    throw "Tag $tag already exists. Pick a new version number."
}

# The release asset must be the regenerated, version-bumped installer, not a
# stale copy. Refuse early if setup_lookdev_scene.py lacks this bl_info tuple.
$asset = 'setup_lookdev_scene.py'
$parts = $Version.Split('.')
if ($parts.Count -eq 3) {
    $tuple = "($($parts[0]), $($parts[1]), $($parts[2]))"
    if (-not (Select-String -Path $asset -SimpleMatch -Pattern $tuple -Quiet)) {
        throw "$asset does not contain bl_info version $tuple -- re-embed the " +
              "version-bumped switcher before releasing."
    }
}

Write-Host "==> Staging and committing..." -ForegroundColor Cyan
git add -A
git diff --cached --quiet                       # exit 0 = nothing staged
if ($LASTEXITCODE -eq 0) {
    Write-Host "    (nothing to commit -- tagging the current HEAD)" -ForegroundColor Yellow
} else {
    git commit -m "$Version - $Message"
    Assert-LastExit 'git commit'
}

Write-Host "==> Tagging $tag..." -ForegroundColor Cyan
git tag -a $tag -m "$tag - $Message"
Assert-LastExit 'git tag'

Write-Host "==> Writing ZIP snapshot..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path '_BACKUP_' | Out-Null
$zip = "_BACKUP_\lookdev-switcher_$tag.zip"
git archive --format=zip -o $zip $tag
Assert-LastExit 'git archive'

if ($Publish) {
    # B. Push the current branch and the tag.
    $branch = (git rev-parse --abbrev-ref HEAD).Trim()
    Assert-LastExit 'git rev-parse'
    Write-Host "==> Pushing $branch and $tag to origin..." -ForegroundColor Cyan
    git push origin $branch
    Assert-LastExit 'git push (branch)'
    git push origin $tag
    Assert-LastExit 'git push (tag)'

    # gh is required for C and D. If it is missing the code is already safe on
    # origin -- fail loudly with what to finish by hand.
    gh auth status 1>$null 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "gh is unavailable or not logged in. Branch and tag are pushed; " +
              "finish with: gh release create $tag --verify-tag " +
              "--title `"$tag - $Message`" --notes-file <notes>; " +
              "gh release upload $tag $asset"
    }

    # C. Create the GitHub Release. Notes from the CHANGELOG, else the message.
    Write-Host "==> Creating GitHub Release $tag..." -ForegroundColor Cyan
    $notes = Get-ChangelogNotes $Version
    if ([string]::IsNullOrWhiteSpace($notes)) {
        Write-Host "    (no CHANGELOG section for $Version -- using -Message)" -ForegroundColor Yellow
        $notes = $Message
    }
    $notesFile = New-TemporaryFile
    Set-Content -Path $notesFile.FullName -Value $notes -Encoding utf8
    gh release create $tag --verify-tag --title "$tag - $Message" --notes-file $notesFile.FullName
    $createExit = $LASTEXITCODE
    Remove-Item $notesFile.FullName -ErrorAction SilentlyContinue
    if ($createExit -ne 0) { throw "gh release create failed (exit $createExit)." }

    # D. Attach the installer as the downloadable asset (--clobber = re-runnable).
    Write-Host "==> Uploading asset $asset..." -ForegroundColor Cyan
    gh release upload $tag $asset --clobber
    Assert-LastExit 'gh release upload'
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "  Commit : $(git rev-parse --short HEAD)"
Write-Host "  Tag    : $tag"
Write-Host "  Backup : $zip"
if ($Publish) {
    Write-Host "  Pushed : origin/$branch + $tag"
    Write-Host "  Release: $(gh release view $tag --json url --jq '.url' 2>$null)"
    Write-Host "  Asset  : $asset"
} else {
    Write-Host ""
    Write-Host "Local only. Review, then re-run with -Publish to push, create the" -ForegroundColor Yellow
    Write-Host "Release and upload the asset. (CHANGELOG.md must be updated first.)" -ForegroundColor Yellow
}
