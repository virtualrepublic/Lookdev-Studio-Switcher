<#
.SYNOPSIS
    Commit, tag, ZIP-snapshot and (optionally) publish a new version in one step.

.DESCRIPTION
    Run from the repository root. Stages all tracked changes, commits them,
    creates an annotated git tag vX.Y.Z, and writes a clean ZIP of the tagged
    tree into _BACKUP_\ (built from git, so only tracked files are included --
    no .blend, no snapshots).

    Because that ZIP comes from git, it cannot contain the master scene
    _local\scenes\COMPARE\LOOKDEV_STUDIO_MODIFIED_520.blend -- the one file the
    repository is not allowed to hold, and the one file the project cannot be
    rebuilt without. It is therefore archived separately into _BACKUP_\scenes\,
    named after the tag, with a MANIFEST.txt recording tag, date and SHA-256.
    If the hash matches an earlier release the scene did not change (a panel-only
    release) and only a manifest line is written -- no second copy.

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
#
# Then cut at <!-- release-notes-end -->, if the entry has one. One file, two
# readers: someone on the Releases page wants to know what changed, whether they
# must reconvert, and how to run it. The reasoning below that marker -- why a
# property was where it was, which operator pushed which undo step -- is for
# whoever maintains this, and it made the 1.3.0 page 7000 characters long.
# Entries without the marker are published whole, so older ones still work.
function Get-ChangelogNotes([string]$version) {
    if (-not (Test-Path 'CHANGELOG.md')) { return $null }
    $text = Get-Content 'CHANGELOG.md' -Raw
    $pattern = '(?ms)^\#\#\s*\[' + [regex]::Escape($version) + '\][^\n]*\n(.*?)(?=^\#\#\s)'
    $m = [regex]::Match($text, $pattern)
    if (-not $m.Success) { return $null }
    $body = $m.Groups[1].Value.TrimEnd()
    $cut = $body.IndexOf('<!-- release-notes-end -->')
    if ($cut -ge 0) {
        $body = $body.Substring(0, $cut)
    } else {
        Write-Host "!!  CHANGELOG entry for $version has no <!-- release-notes-end -->" -ForegroundColor Yellow
        Write-Host "    marker -- publishing the whole entry, maintainer notes and all." -ForegroundColor Yellow
    }
    $body = $body -replace '\s*-{3,}\s*$', ''    # drop a trailing horizontal rule
    return $body.Trim()
}

# Must be at the repo root (where .git lives).
if (-not (Test-Path '.git')) {
    throw "Run this from the repository root (the folder that contains .git)."
}

$tag = "v$Version"
# The script's own closing line tells you to review the local result and then
# re-run with -Publish. A blanket refusal on an existing tag made that
# impossible: the first run creates the tag, the second is turned away, and the
# only way out is deleting the tag by hand. So an existing tag is fatal only
# when it points somewhere other than HEAD -- that is a genuine collision, a
# version number already used for different code.
$tagExists = [bool](git tag --list $tag)
if ($tagExists) {
    $tagged = (git rev-list -n 1 $tag).Trim()
    $head   = (git rev-parse HEAD).Trim()
    if ($tagged -ne $head) {
        throw "Tag $tag already exists and points at $($tagged.Substring(0,7)), " +
              "not at HEAD $($head.Substring(0,7)). Pick a new version number."
    }
    Write-Host "==> $tag already exists on HEAD -- resuming this release." -ForegroundColor Yellow
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

# The switcher states its version twice: in the header line and in bl_info.
# They drifted once -- the header read "v1.2" while bl_info said (1, 2, 3) --
# and since the header is the first thing anyone reads, a current file looked
# stale. Both must agree with the version being released.
$switcher = 'lookdev_switcher.py'
if (Test-Path $switcher) {
    $text = Get-Content $switcher -Raw
    $hdr = [regex]::Match($text, '(?m)^#\s+LOOKDEV SWITCHER\s+v(\d+\.\d+\.\d+)\s*$')
    $bli = [regex]::Match($text, '"version"\s*:\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)')
    if (-not $hdr.Success) {
        throw "$switcher has no '#  LOOKDEV SWITCHER  vX.Y.Z' header line to check."
    }
    if (-not $bli.Success) {
        throw "$switcher has no readable bl_info version tuple."
    }
    $headerVersion = $hdr.Groups[1].Value
    $blinfoVersion = "{0}.{1}.{2}" -f $bli.Groups[1].Value, $bli.Groups[2].Value, $bli.Groups[3].Value
    if ($headerVersion -ne $blinfoVersion) {
        throw ("$switcher disagrees with itself: header says v$headerVersion, " +
               "bl_info says $blinfoVersion. Bump both.")
    }
    if ($headerVersion -ne $Version) {
        throw ("$switcher is at $headerVersion but you are releasing $Version. " +
               "Bump the header and bl_info, then regenerate the installer.")
    }
}

# The bl_info check above catches "forgot to regenerate after a version bump".
# It cannot catch "toolchain changed, version unchanged" -- and that is the one
# that ships silently: a fix in make_migration.py with the installer left as it
# was looks perfectly healthy. So the generator writes a SHA-256 over every
# input into the header, and it is recomputed here.
#
# Hashes, not timestamps: git sets every file's mtime to the checkout time, so
# a timestamp check greets a fresh clone with a false alarm.
$stampMatch = [regex]::Match((Get-Content $asset -Raw),
                             '(?m)^#\s+TOOLCHAIN STAMP\s+([0-9a-f]{64})\s*$')
if (-not $stampMatch.Success) {
    Write-Host "!!  $asset carries no toolchain stamp -- it predates the check." -ForegroundColor Yellow
    Write-Host "    Regenerate it to get one. Releasing without the check." -ForegroundColor Yellow
} else {
    # Same order and shape as make_migration.py's toolchain_stamp().
    $stampInputs = @(
        @('make_migration', 'tools\make_migration.py'),
        @('snap_original',  '_local\snap_original.json'),
        @('snap_modified',  '_local\snap_modified.json'),
        @('switcher',       'lookdev_switcher.py'),
        @('workspace',      '_local\workspace_ui.blend')
    )
    $missing = @($stampInputs | Where-Object { -not (Test-Path -LiteralPath $_[1]) } |
                 ForEach-Object { $_[1] })
    if ($missing.Count -gt 0) {
        # _local\ is git-ignored, so a clone has no snapshots. Cannot verify,
        # and must not pretend to.
        Write-Host "!!  Cannot check the toolchain stamp -- not here:" -ForegroundColor Yellow
        $missing | ForEach-Object { Write-Host "      $_" -ForegroundColor Yellow }
        Write-Host "    Releasing without the check." -ForegroundColor Yellow
    } else {
        $lines = foreach ($p in $stampInputs) {
            '{0}:{1}' -f $p[0], (Get-FileHash -LiteralPath $p[1] -Algorithm SHA256).Hash.ToLower()
        }
        $bytes = [Text.Encoding]::UTF8.GetBytes(($lines -join "`n"))
        $now = (([Security.Cryptography.SHA256]::HashData($bytes) |
                 ForEach-Object { $_.ToString('x2') }) -join '')
        if ($now -ne $stampMatch.Groups[1].Value) {
            # Name the input that moved -- the header carries each one short.
            $moved = foreach ($line in $lines) {
                $label, $hash = $line -split ':', 2
                if (-not (Select-String -Path $asset -SimpleMatch -Quiet `
                          -Pattern ("{0} {1}" -f $label, $hash.Substring(0, 12)))) { $label }
            }
            # Written out rather than packed into the exception: PowerShell
            # reflows a multi-line throw into one wrapped, colour-coded blob,
            # and the one line that matters -- which input moved -- disappears
            # into it.
            Write-Host ""
            Write-Host "  $asset was not regenerated after the toolchain changed." -ForegroundColor Red
            Write-Host "    stamp in the file : $($stampMatch.Groups[1].Value.Substring(0,16))" -ForegroundColor Red
            Write-Host "    stamp right now   : $($now.Substring(0,16))" -ForegroundColor Red
            Write-Host "    changed since     : $($moved -join ', ')" -ForegroundColor Red
            Write-Host "  Regenerate it (run.ps1 step 2), then release." -ForegroundColor Red
            Write-Host ""
            throw "Stale $asset -- see above."
        }
        Write-Host "    toolchain stamp ok ($($now.Substring(0,16)))" -ForegroundColor DarkGray
    }
}

# The master scene is git-ignored by design (it carries albin's geometry), so the
# ZIP further down cannot hold it. Check for it now rather than after the tag
# exists: a missing scene does not invalidate the release, but that version's
# scene would be unrecoverable, and by then the tag cannot be taken back.
$sceneSrc  = '_local\scenes\COMPARE\LOOKDEV_STUDIO_MODIFIED_520.blend'
$sceneDir  = '_BACKUP_\scenes'
$sceneMani = Join-Path $sceneDir 'MANIFEST.txt'
$sceneOk   = Test-Path $sceneSrc
if (-not $sceneOk) {
    Write-Host "!!  Master scene not found:" -ForegroundColor Yellow
    Write-Host "!!    $sceneSrc" -ForegroundColor Yellow
    Write-Host "!!  Releasing anyway -- but $tag will carry no scene archive." -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "==> Staging and committing..." -ForegroundColor Cyan
git add -A
git diff --cached --quiet                       # exit 0 = nothing staged
if ($LASTEXITCODE -eq 0) {
    Write-Host "    (nothing to commit -- tagging the current HEAD)" -ForegroundColor Yellow
} elseif ($tagExists) {
    # Committing here would move HEAD past the tag, and the tag would then
    # name something other than what is about to be published -- the reviewed
    # result and the released result would silently differ.
    throw "$tag already exists on HEAD, but there are new changes to commit. " +
          "Either release them under a new version, or drop the tag " +
          "(git tag -d $tag) and run this again from the top."
} else {
    git commit -m "$Version - $Message"
    Assert-LastExit 'git commit'
}

if ($tagExists) {
    Write-Host "==> Tag $tag is already on this commit -- keeping it." -ForegroundColor Cyan
} else {
    Write-Host "==> Tagging $tag..." -ForegroundColor Cyan
    git tag -a $tag -m "$tag - $Message"
    Assert-LastExit 'git tag'
}

Write-Host "==> Writing ZIP snapshot..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path '_BACKUP_' | Out-Null
$zip = "_BACKUP_\lookdev-switcher_$tag.zip"
git archive --format=zip -o $zip $tag
Assert-LastExit 'git archive'

Write-Host "==> Archiving the master scene..." -ForegroundColor Cyan
$sceneNote = 'none (scene not found)'
if ($sceneOk) {
    New-Item -ItemType Directory -Force -Path $sceneDir | Out-Null
    if (-not (Test-Path $sceneMani)) {
        Set-Content -Path $sceneMani -Encoding utf8 -Value @(
            '# The master scene, one entry per release.',
            '#',
            '# The repository cannot hold this file: it is a derivative of a scene',
            '# that is not ours to redistribute, so .gitignore blocks it. Without',
            '# it the project cannot be rebuilt -- the generated installer is',
            '# derived from the diff against it. Hence this archive.',
            '#',
            '# A line with "= vX.Y.Z" means the scene was byte-identical to that',
            '# release (a panel-only change), so no second copy was stored.',
            '#',
            '# tag        date              sha-256                                                           file',
            '# ------------------------------------------------------------------------------------------------------')
    }
    $hash  = (Get-FileHash $sceneSrc -Algorithm SHA256).Hash
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm'
    $prior = $null
    $hit = Select-String -Path $sceneMani -SimpleMatch -Pattern $hash | Select-Object -First 1
    if ($hit) { $prior = ($hit.Line.Trim() -split '\s+')[0] }

    if ($prior) {
        # Same bytes as an earlier release: a panel-only change. Record it, but
        # do not store the file twice.
        Add-Content -Path $sceneMani -Encoding utf8 `
            -Value ('{0,-10} {1}  {2}  = {3} (scene unchanged)' -f $tag, $stamp, $hash, $prior)
        $sceneNote = "unchanged since $prior -- not copied"
        Write-Host "    scene is byte-identical to $prior -- manifest line only" -ForegroundColor Yellow
    } else {
        $sceneDst = Join-Path $sceneDir "LOOKDEV_STUDIO_MODIFIED_520_$tag.blend"
        Copy-Item $sceneSrc $sceneDst -Force
        Add-Content -Path $sceneMani -Encoding utf8 `
            -Value ('{0,-10} {1}  {2}  {3}' -f $tag, $stamp, $hash, (Split-Path $sceneDst -Leaf))
        $mb = [math]::Round((Get-Item $sceneDst).Length / 1MB, 1)
        $sceneNote = "$sceneDst ($mb MB)"
        Write-Host "    $sceneDst ($mb MB)"
    }
} else {
    Write-Host "    skipped -- $sceneSrc not found" -ForegroundColor Yellow
}

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
Write-Host "  Scene  : $sceneNote"
if ($Publish) {
    Write-Host "  Pushed : origin/$branch + $tag"
    Write-Host "  Release: $(gh release view $tag --json url --jq '.url' 2>$null)"
    Write-Host "  Asset  : $asset"
} else {
    Write-Host ""
    Write-Host "Local only. Review, then re-run with -Publish to push, create the" -ForegroundColor Yellow
    Write-Host "Release and upload the asset. (CHANGELOG.md must be updated first.)" -ForegroundColor Yellow
}
