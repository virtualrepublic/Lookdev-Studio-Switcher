# ============================================================================
#  RUN  v1.0  --  the toolchain, one step per run
# ============================================================================
#  by Prof. Michael Klein
#     professor@virtualrepublic.org
#
#  Copyright (C) 2026  Prof. Michael Klein
#  SPDX-License-Identifier: GPL-3.0-or-later
# ============================================================================

<#
.SYNOPSIS
    The toolchain, one step per run. Start it with _local\RUN.cmd (double-click).

.DESCRIPTION
    Replaces the old CMD.txt paste list. Two things it does that copying lines
    could not:

    1. It finds blender.exe instead of carrying a hard-coded path. The Blender
       Launcher folder name contains the build hash
       (blender-5.2.0-lts.fbe6228777e7), so every pasted line broke on the next
       Blender update -- silently, because a wrong path just fails.

    2. It refuses to generate from stale snapshots. The generator reads the
       JSONs, not the scenes; a change to tools\dump_scene.py invalidates them
       and nothing warns you. That has produced a traceback once already.

    What it deliberately does NOT do is run the whole chain. Between the diff
    and the generator sits your reading of the report -- both directions, is
    everything I did in there and is anything in there I did not intend. Every
    problem the report has caught so far (a private path, denoising_use_gpu, a
    value drifting in the fourth decimal) needed a human to notice.

.PARAMETER Blender
    Path to blender.exe. Only needed if auto-detection fails or picks wrong.

.EXAMPLE
    pwsh -File tools\run.ps1
.EXAMPLE
    pwsh -File tools\run.ps1 -Blender "D:\Blender\blender.exe"
#>
param([string]$Blender)

$ErrorActionPreference = 'Stop'

# The project is calibrated to this Blender series -- the scenes were saved by
# it and the snapshots describe its RNA. Changing this is a deliberate decision,
# not a convenience: it invalidates the snapshots and probably the migration.
$RequiredSeries = '5.2'

# --- Layout ------------------------------------------------------------------
# This lives in tools\ so it is versioned with the rest of the toolchain. It
# used to sit in _local\, which is git-ignored -- a fresh clone had no entry
# point at all. _local\RUN.cmd is only the double-click launcher.
$Tools     = $PSScriptRoot
$Repo      = Split-Path $Tools -Parent
$Local     = Join-Path $Repo  '_local'
$Scenes    = Join-Path $Local 'scenes'
$Compare   = Join-Path $Scenes 'COMPARE'

$Albin     = Join-Path $Scenes  'LOOKDEV_STUDIO_ALBIN_293.blend'
$Original  = Join-Path $Compare 'LOOKDEV_STUDIO_ORIGINAL_520.blend'
$Modified  = Join-Path $Compare 'LOOKDEV_STUDIO_MODIFIED_520.blend'
$TestScene = Join-Path $Scenes  'LOOKDEV_STUDIO_TEST_520.blend'

$SnapOrig  = Join-Path $Local 'snap_original.json'
$SnapMod   = Join-Path $Local 'snap_modified.json'
$Installer = Join-Path $Repo  'setup_lookdev_scene.py'
$Switcher  = Join-Path $Repo  'lookdev_switcher.py'
$DumpScene = Join-Path $Tools 'dump_scene.py'

# The exported workspace, if there is one. It is an INPUT to the generator, like
# the snapshots and the switcher: overwrite it whenever the layout changes, and
# every generation from then on carries the new one.
$Workspace = Join-Path $Local 'workspace_ui.blend'


# --- Blender -----------------------------------------------------------------
function Resolve-Blender {
    if ($Blender) {
        if (Test-Path $Blender) { return (Resolve-Path $Blender).Path }
        throw "-Blender points at a file that does not exist: $Blender"
    }
    if ($env:LOOKDEV_BLENDER -and (Test-Path $env:LOOKDEV_BLENDER)) {
        return $env:LOOKDEV_BLENDER
    }

    $roots = @(
        (Join-Path $env:USERPROFILE 'Desktop\Blender_Launcher\stable'),
        (Join-Path $env:USERPROFILE 'Desktop\Blender_Launcher\custom'),
        'C:\Program Files\Blender Foundation'
    ) | Where-Object { Test-Path $_ }

    $found = @()
    foreach ($root in $roots) {
        foreach ($dir in Get-ChildItem $root -Directory -ErrorAction SilentlyContinue) {
            $exe = Join-Path $dir.FullName 'blender.exe'
            if (-not (Test-Path $exe)) { continue }
            $m = [regex]::Match($dir.Name, '(\d+)\.(\d+)\.(\d+)')
            if (-not $m.Success) { continue }
            $ver = [version]("{0}.{1}.{2}" -f $m.Groups[1].Value, $m.Groups[2].Value, $m.Groups[3].Value)
            if ("$($ver.Major).$($ver.Minor)" -ne $RequiredSeries) { continue }
            $found += [pscustomobject]@{ Version = $ver; Exe = $exe; Name = $dir.Name }
        }
    }

    if (-not $found) {
        throw ("No Blender $RequiredSeries found. Looked in:`n  " +
               ($roots -join "`n  ") +
               "`nPass the path explicitly:  pwsh -File run.ps1 -Blender ""C:\...\blender.exe""")
    }

    # More than one 5.2 build installed is normal with the Launcher -- take the
    # highest and say which, rather than guessing silently.
    $pick = $found | Sort-Object Version -Descending | Select-Object -First 1
    if ($found.Count -gt 1) {
        Write-Host ("  ({0} builds of {1} installed -- using {2})" -f $found.Count, $RequiredSeries, $pick.Name) -ForegroundColor DarkGray
    }
    return $pick.Exe
}


# --- Guards ------------------------------------------------------------------

# Why the snapshots may not be used: returns a reason, or $null when they are fine.
function Get-SnapshotProblem {
    if (-not (Test-Path $SnapOrig) -or -not (Test-Path $SnapMod)) {
        return 'the snapshots do not exist yet'
    }
    $snapTime = (Get-Item $SnapMod).LastWriteTime
    if ((Test-Path $Modified) -and (Get-Item $Modified).LastWriteTime -gt $snapTime) {
        return 'MODIFIED_520.blend was saved after the snapshots were written'
    }
    # Only dump_scene.py decides what a snapshot contains -- including the
    # *_SKIP lists. A change there makes the JSONs stale with no warning.
    if ((Test-Path $DumpScene) -and (Get-Item $DumpScene).LastWriteTime -gt $snapTime) {
        return 'tools\dump_scene.py was changed after the snapshots were written'
    }
    return $null
}

# Does the installer carry the interface that workspace_ui.blend holds right now?
# Compared by stamp, not by timestamp: the generator writes the sha256 prefix of
# the export into the script, so this is exact. Generating before exporting has
# gone unnoticed three times -- the run looks fine and the old layout ships.
function Get-WorkspaceStamps {
    $export = $null
    if (Test-Path $Workspace) {
        $export = (Get-FileHash $Workspace -Algorithm SHA256).Hash.ToLower().Substring(0, 16)
    }
    $embedded = $null
    if (Test-Path $Installer) {
        $line = Select-String -Path $Installer -Pattern "^WORKSPACE_STAMP = " |
                Select-Object -First 1
        if ($line) { $embedded = ($line.Line -replace ".*'(.*)'.*", '$1') }
    }
    return @{ Export = $export; Embedded = $embedded }
}

function Get-WorkspaceProblem {
    # An export that landed anywhere but _local\ is invisible to the generator
    # and to the stamp check -- both look only at _local\workspace_ui.blend. It
    # happened once: the marker export_workspace.py uses to find _local\ was
    # run.ps1, and run.ps1 moved to tools\.
    $stray = Get-ChildItem (Join-Path $Local 'scenes') -Recurse -Filter 'workspace_ui.blend' -ErrorAction SilentlyContinue
    if ($stray) {
        return ("an export landed outside _local\: " +
                ($stray | ForEach-Object { $_.FullName.Replace($Repo, '') }) -join ', ' +
                " -- move it to _local\workspace_ui.blend or export again")
    }
    $s = Get-WorkspaceStamps
    if (-not $s.Export -and -not $s.Embedded) { return $null }   # no interface in play
    if (-not $s.Export) {
        return "the installer carries an interface but workspace_ui.blend is gone"
    }
    if (-not $s.Embedded) {
        return "workspace_ui.blend exists but the installer carries no interface"
    }
    if ($s.Export -ne $s.Embedded) {
        return ("the installer carries an OLDER interface " +
                "(installer $($s.Embedded), export $($s.Export))")
    }
    return $null
}

function Confirm-Step([string]$question) {
    $a = Read-Host "$question [y/N]"
    return ($a -match '^(y|yes|j|ja)$')
}

function Invoke-Blender([string[]]$ScriptArgs, [string]$OutFile) {
    Push-Location $Local          # snapshots and reports are written to the cwd
    try {
        if ($OutFile) {
            & $BlenderExe --background @ScriptArgs *>&1 | Tee-Object -FilePath $OutFile
            Write-Host ""
            Write-Host "  written: $OutFile" -ForegroundColor Green
        } else {
            & $BlenderExe --background @ScriptArgs
        }
    } finally { Pop-Location }
}


# --- Status ------------------------------------------------------------------
function Show-Status {
    Write-Host ""
    Write-Host "  Blender  : $BlenderExe" -ForegroundColor DarkGray
    Write-Host ""
    $rows = @(
        @{ n = 'ALBIN_293    (albin''s download)'; p = $Albin },
        @{ n = 'ORIGINAL_520 (left of the diff)'; p = $Original },
        @{ n = 'MODIFIED_520 (THE MASTER)';       p = $Modified },
        @{ n = 'TEST_520     (throwaway)';        p = $TestScene },
        @{ n = 'snap_modified.json';              p = $SnapMod },
        @{ n = 'setup_lookdev_scene.py';          p = $Installer },
        @{ n = 'workspace_ui.blend';             p = $Workspace }
    )
    foreach ($r in $rows) {
        if (Test-Path $r.p) {
            $f = Get-Item $r.p
            $ro = if ($f.Attributes -band [IO.FileAttributes]::ReadOnly) { '  [read-only]' } else { '' }
            Write-Host ("  {0,-32}{1:yyyy-MM-dd HH:mm}{2}" -f $r.n, $f.LastWriteTime, $ro)
        } else {
            Write-Host ("  {0,-32}--" -f $r.n) -ForegroundColor DarkGray
        }
    }
    $wsProblem = Get-WorkspaceProblem
    if ($wsProblem) {
        Write-Host ""
        Write-Host "  INTERFACE STALE: $wsProblem" -ForegroundColor Yellow
        Write-Host "  Run step 4 again -- exporting after generating is the usual cause." -ForegroundColor Yellow
    }
    $problem = Get-SnapshotProblem
    Write-Host ""
    if ($problem) {
        Write-Host "  Snapshots STALE: $problem" -ForegroundColor Yellow
        Write-Host "  Run step 1 before step 4." -ForegroundColor Yellow
    } else {
        Write-Host "  Snapshots are current." -ForegroundColor Green
    }
    Write-Host ""
}


# --- Steps -------------------------------------------------------------------

function Step-Diff {
    Write-Host "==> Diff + snapshots" -ForegroundColor Cyan
    Invoke-Blender @('--python', (Join-Path $Tools 'diff_blends.py'), '--',
                     $Original, $Modified, '--keep-snapshots', 'snap', '--summary')
}

function Step-Report {
    $out = Join-Path $Local 'report.txt'
    Write-Host "==> Full report -> report.txt" -ForegroundColor Cyan
    Write-Host "    Read it in BOTH directions: is everything you did in there," -ForegroundColor DarkGray
    Write-Host "    and is anything in there you did not intend?" -ForegroundColor DarkGray
    Invoke-Blender @('--python', (Join-Path $Tools 'diff_blends.py'), '--',
                     $Original, $Modified) $out
    if (Confirm-Step '    Open it now?') { Invoke-Item $out }
}

function Step-ReportNarrow {
    $only = Read-Host '    Restrict to (e.g. scenes.Scene, objects.DOF)'
    if (-not $only) { Write-Host '    cancelled.' -ForegroundColor Yellow; return }
    $safe = ($only -replace '[^A-Za-z0-9._-]', '_')
    $out  = Join-Path $Local "report_$safe.txt"
    Write-Host "==> Report restricted to $only" -ForegroundColor Cyan
    Invoke-Blender @('--python', (Join-Path $Tools 'diff_blends.py'), '--',
                     $Original, $Modified, '--only', $only) $out
    if (Confirm-Step '    Open it now?') { Invoke-Item $out }
}

function Step-Generate {
    $problem = Get-SnapshotProblem
    if ($problem) {
        Write-Host "REFUSED: $problem." -ForegroundColor Red
        Write-Host "The generator reads the snapshots, not the scenes -- it would" -ForegroundColor Red
        Write-Host "silently work from old data. Run step 1 first." -ForegroundColor Red
        return
    }
    Write-Host "This overwrites $Installer," -ForegroundColor Yellow
    Write-Host "the file users download and run. It is tracked by git, so the" -ForegroundColor Yellow
    Write-Host "change is reviewable with git diff." -ForegroundColor Yellow
    if (-not (Confirm-Step '    Generate?')) { Write-Host '    cancelled.'; return }

    $genArgs = @('--python', (Join-Path $Tools 'make_migration.py'), '--',
                 $SnapOrig, $SnapMod, '--switcher', $Switcher, '-o', $Installer)
    if (Test-Path $Workspace) {
        $genArgs += @('--workspace', $Workspace)
        Write-Host "    embedding the interface from workspace_ui.blend" -ForegroundColor DarkGray
    } else {
        Write-Host "    no workspace_ui.blend -- the script will carry no layout." -ForegroundColor DarkGray
        Write-Host "    Export one with tools\export_workspace.py to change that." -ForegroundColor DarkGray
    }
    Write-Host "==> Generating the installer" -ForegroundColor Cyan
    Invoke-Blender $genArgs
    Write-Host ""
    Write-Host "    Now read the TODO block at the bottom of the generated file." -ForegroundColor Yellow
}

function Step-TestCopy {
    if (-not (Test-Path $Albin)) {
        Write-Host "REFUSED: $Albin not found." -ForegroundColor Red
        return
    }
    # Testing an installer built before the last interface export means testing
    # the old layout -- and it looks like a code failure, not a stale build.
    $wsProblem = Get-WorkspaceProblem
    if ($wsProblem) {
        Write-Host "REFUSED: $wsProblem." -ForegroundColor Red
        Write-Host "You would be testing the interface as it was, not as it is." -ForegroundColor Red
        Write-Host "Run step 4 first." -ForegroundColor Red
        return
    }
    # Testing an installer that predates the snapshots means testing yesterday's build.
    if ((Test-Path $Installer) -and (Test-Path $SnapMod) -and
        (Get-Item $Installer).LastWriteTime -lt (Get-Item $SnapMod).LastWriteTime) {
        Write-Host "WARNING: setup_lookdev_scene.py is older than the snapshots --" -ForegroundColor Yellow
        Write-Host "you would be testing a version that predates your last diff." -ForegroundColor Yellow
        if (-not (Confirm-Step '    Continue anyway?')) { return }
    }
    if (Test-Path $TestScene) {
        Write-Host "This deletes the existing $(Split-Path $TestScene -Leaf)." -ForegroundColor Yellow
        Write-Host "That is intended: never test on a file that was already converted." -ForegroundColor DarkGray
        if (-not (Confirm-Step '    Replace it?')) { Write-Host '    cancelled.'; return }
        Remove-Item $TestScene -Force
    }
    Write-Host "==> Fresh test copy from ALBIN_293" -ForegroundColor Cyan
    Copy-Item $Albin $TestScene
    # The copy inherits the read-only flag from ALBIN_293; Blender could not save.
    Set-ItemProperty -Path $TestScene -Name IsReadOnly -Value $false
    Write-Host "    $TestScene" -ForegroundColor Green
    Write-Host ""
    Write-Host "    In Blender, by hand:" -ForegroundColor Yellow
    Write-Host "      open it, run ..\setup_lookdev_scene.py, read the console"
    Write-Host "      run it a SECOND time -- it must report 0 changes"
    Write-Host "      check the panel appears and the buttons work"
}

function Step-CrossCheck {
    $out = Join-Path $Local 'report_vs_albin_293.txt'
    Write-Host "==> Cross-check: diff against albin's 2.93 file" -ForegroundColor Cyan
    Write-Host "    ORIGINAL_520 is the same scene re-saved by Blender $RequiredSeries." -ForegroundColor DarkGray
    Write-Host "    If this report matches the one from step 2, that re-save hides" -ForegroundColor DarkGray
    Write-Host "    nothing. Differences are the blind spot: properties the" -ForegroundColor DarkGray
    Write-Host "    migration never sets because the baseline already has them --" -ForegroundColor DarkGray
    Write-Host "    a freshly downloaded scene does not." -ForegroundColor DarkGray
    Invoke-Blender @('--python', (Join-Path $Tools 'diff_blends.py'), '--',
                     $Albin, $Modified) $out
    if (Confirm-Step '    Open it now?') { Invoke-Item $out }
}


function Step-Probe {
    $probe = Join-Path $Local 'probe_workspace.py'
    if (-not (Test-Path $probe)) {
        Write-Host "REFUSED: $probe not found." -ForegroundColor Red
        return
    }
    $out = Join-Path $Local 'probe_workspace_background.txt'
    Write-Host "==> Probe: what does a BACKGROUND Blender see of the workspaces?" -ForegroundColor Cyan
    Write-Host "    Read-only. If this reports 0 workspaces, the diff can never" -ForegroundColor DarkGray
    Write-Host "    capture them, whatever is done to dump_scene.py." -ForegroundColor DarkGray
    Write-Host "    Run the same file from Blender's Text editor for the other half" -ForegroundColor DarkGray
    Write-Host "    of the answer -- what is actually in your workspace." -ForegroundColor DarkGray
    Invoke-Blender @($Modified, '--python', $probe) $out
    if (Confirm-Step '    Open it now?') { Invoke-Item $out }
}


# --- Main --------------------------------------------------------------------
Write-Host ""
Write-Host "  Lookdev Studio Switcher -- toolchain" -ForegroundColor White
$BlenderExe = Resolve-Blender

foreach ($required in @($Original, $Modified)) {
    if (-not (Test-Path $required)) {
        Write-Host ""
        Write-Host "  Missing: $required" -ForegroundColor Red
        Write-Host "  Steps 1-4 will not work without it." -ForegroundColor Red
    }
}

while ($true) {
    Show-Status
    Write-Host "  1  Diff + snapshots            (summary on screen)"
    Write-Host "  2  Full report                 -> report.txt        <- read this"
    Write-Host "  3  Report, restricted          -> report_<path>.txt"
    Write-Host "  4  Generate the installer      -> ..\setup_lookdev_scene.py"
    Write-Host "  5  Fresh test copy from ALBIN_293"
    Write-Host "  6  Cross-check against albin's 2.93 file"
    Write-Host "  P  Probe: what a background Blender sees of the workspaces"
    Write-Host "  Q  Quit"
    Write-Host ""
    $choice = Read-Host '  Step'
    Write-Host ""
    try {
        switch ($choice.Trim().ToUpper()) {
            '1' { Step-Diff }
            '2' { Step-Report }
            '3' { Step-ReportNarrow }
            '4' { Step-Generate }
            '5' { Step-TestCopy }
            '6' { Step-CrossCheck }
            'P' { Step-Probe }
            'Q' { break }
            ''  { }
            default { Write-Host "  '$choice'?" -ForegroundColor Yellow }
        }
    } catch {
        Write-Host ""
        Write-Host "  FAILED: $($_.Exception.Message)" -ForegroundColor Red
    }
    if ($choice.Trim().ToUpper() -eq 'Q') { break }
    Write-Host ""
    Read-Host '  [Enter] for the menu' | Out-Null
}
