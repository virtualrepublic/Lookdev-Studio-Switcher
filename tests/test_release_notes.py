"""Release notes are cut at the next version, not at any "## ". Needs pwsh.

Defect 12 in docs/MAINTAINING.md. Symptom: the v1.0.0 notes were cut off at
their own "## Setup" sub-heading and two lines were published as the release
page.

This is the one defect that is not Python. `Get-ChangelogNotes` lives in
tools/new-release.ps1, and testing a Python re-implementation of its regex
would test the re-implementation -- a copy is green by construction. So the
real function is pulled out of the real file through the PowerShell parser and
run by PowerShell.

Why the AST and not dot-sourcing: new-release.ps1 executes at the top level and
throws unless it is started in a repository root with a matching tag. Loading
it to reach one function would run all of that.

pwsh is preinstalled on GitHub's ubuntu runners. When it is missing these tests
skip locally and fail in CI (CI=true), because a skipped test that reads as a
pass is the failure this whole suite exists to avoid.
"""

import os
import re
import shutil
import subprocess
import tempfile
import unittest

from _support import repo_path

RELEASE_SCRIPT = repo_path("tools", "new-release.ps1")

# Parse new-release.ps1, lift out the one function, run it against whatever
# CHANGELOG.md is in the current directory. The markers fence the return value
# off from Write-Host warnings, which the function emits on the way past.
DRIVER = r"""
param([string]$ReleaseScript, [string]$Version)
$ErrorActionPreference = 'Stop'
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ReleaseScript, [ref]$null, [ref]$errors)
if ($errors.Count) { throw "new-release.ps1 does not parse: $($errors[0].Message)" }
$found = $ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -eq 'Get-ChangelogNotes'
}, $true)
if ($found.Count -ne 1) {
    throw "expected one Get-ChangelogNotes in new-release.ps1, found $($found.Count)"
}
Invoke-Expression $found[0].Extent.Text
$notes = Get-ChangelogNotes $Version
Write-Output '<<BEGIN>>'
if ($null -ne $notes) { Write-Output $notes }
Write-Output '<<END>>'
"""

# The same lift, but the notes are written to a file with Set-Content -Encoding
# utf8 -- which is what new-release.ps1 does before handing the path to
# `gh release create --notes-file`. Going through stdout instead would measure
# the console's encoding, not the release path's.
DRIVER_TO_FILE = r"""
param([string]$ReleaseScript, [string]$Version, [string]$Out)
$ErrorActionPreference = 'Stop'
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ReleaseScript, [ref]$null, [ref]$errors)
if ($errors.Count) { throw "new-release.ps1 does not parse: $($errors[0].Message)" }
$found = $ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -eq 'Get-ChangelogNotes'
}, $true)
Invoke-Expression $found[0].Extent.Text
$notes = Get-ChangelogNotes $Version
Set-Content -Path $Out -Value $notes -Encoding utf8
"""

FIXTURE = """# Changelog

## [2.0.0] - 2026-09-01
What changed for you in 2.0.0.
<!-- release-notes-end -->
Maintainer reasoning that must never reach the release page.

## [1.0.0] - 2026-07-18
The first release.

## Setup

This sub-heading belongs to the 1.0.0 entry. Cutting here published two lines.

The last line of the oldest entry.

[2.0.0]: https://example.invalid/2.0.0
[1.0.0]: https://example.invalid/1.0.0
"""


def find_powershell():
    return shutil.which("pwsh") or shutil.which("powershell")


class PowerShellTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.shell = find_powershell()
        if cls.shell:
            return
        if os.environ.get("CI"):
            raise AssertionError(
                "no pwsh on PATH. In CI this is a failure, not a skip: these "
                "tests are the only cover defect 12 has, and a silent skip "
                "would report a green build that checked nothing.")
        raise unittest.SkipTest(
            "no pwsh or powershell on PATH -- defect 12 is NOT covered by this "
            "run. Install PowerShell 7 to check it locally.")

    def notes_for(self, version, changelog, directory=None):
        """Run the real Get-ChangelogNotes against a CHANGELOG in a temp dir."""
        with tempfile.TemporaryDirectory() as workdir:
            if changelog is not None:
                with open(os.path.join(workdir, "CHANGELOG.md"), "w",
                          encoding="utf-8") as handle:
                    handle.write(changelog)
            driver = os.path.join(workdir, "driver.ps1")
            with open(driver, "w", encoding="utf-8") as handle:
                handle.write(DRIVER)
            result = subprocess.run(
                [self.shell, "-NoProfile", "-NonInteractive", "-File", driver,
                 "-ReleaseScript", RELEASE_SCRIPT, "-Version", version],
                cwd=directory or workdir, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0,
                         "the driver failed:\n%s\n%s"
                         % (result.stdout, result.stderr))
        output = result.stdout.replace("\r\n", "\n")
        self.assertIn("<<BEGIN>>", output, output)
        body = output.split("<<BEGIN>>", 1)[1].split("<<END>>", 1)[0]
        return body.strip("\n")


class AnEntryIsCutAtTheNextVersion(PowerShellTestCase):

    def test_a_sub_heading_does_not_end_the_entry(self):
        notes = self.notes_for("1.0.0", FIXTURE)
        self.assertIn("## Setup", notes)
        self.assertIn("This sub-heading belongs to the 1.0.0 entry", notes)
        self.assertIn("The last line of the oldest entry.", notes)

    def test_the_next_version_heading_does_end_it(self):
        notes = self.notes_for("2.0.0", FIXTURE)
        self.assertNotIn("The first release.", notes)
        self.assertNotIn("## [1.0.0]", notes)

    def test_the_entry_heading_itself_is_not_part_of_the_notes(self):
        notes = self.notes_for("1.0.0", FIXTURE)
        self.assertFalse(notes.startswith("## [1.0.0]"), notes[:40])


class TheMarkerCutsTheMaintainerHalf(PowerShellTestCase):

    def test_everything_below_the_marker_is_dropped(self):
        notes = self.notes_for("2.0.0", FIXTURE)
        self.assertIn("What changed for you in 2.0.0.", notes)
        self.assertNotIn("Maintainer reasoning", notes)
        self.assertNotIn("release-notes-end", notes)

    def test_an_entry_without_a_marker_is_published_whole(self):
        # Documented behaviour, not an oversight: older entries have no marker
        # and must still publish. The function warns on the way past.
        notes = self.notes_for("1.0.0", FIXTURE)
        self.assertIn("The last line of the oldest entry.", notes)


class MissingThings(PowerShellTestCase):

    def test_an_unknown_version_yields_nothing(self):
        self.assertEqual(self.notes_for("9.9.9", FIXTURE), "")

    def test_a_missing_changelog_yields_nothing(self):
        self.assertEqual(self.notes_for("2.0.0", None), "")

    def test_a_version_is_matched_whole_not_as_a_prefix(self):
        # "1.0" must not match the "[1.0.0]" heading: the regex escapes the
        # version, but the dot in it is still a metacharacter without that.
        self.assertEqual(self.notes_for("1.0", FIXTURE), "")


class TheNotesReachGitHubIntact(PowerShellTestCase):
    """Non-ASCII survives the trip to the Releases page.

    Every other test here reads the notes off stdout, and stdout on Windows is
    whatever the console encoding happens to be -- so those tests compare ASCII
    fragments and could not see a mangled em dash or a dropped arrow if they
    tried. The release path is a different one: Set-Content -Encoding utf8 into
    a temporary file, then `gh release create --notes-file`. This goes through
    that path and compares against CHANGELOG.md itself.

    The instructions users follow contain arrows -- "Scripting -> Open -> Run
    Script" -- and a page that renders them as blanks reads like a mistake in
    the instructions rather than in the pipeline.

    The check is in two halves, because the write itself sits in the middle of
    new-release.ps1's publish block and cannot be lifted out the way
    Get-ChangelogNotes can:

      * this driver writes with the same encoding and shows that the encoding
        preserves everything in CHANGELOG.md;
      * test_the_release_script_writes_the_notes_as_utf8 pins the encoding the
        real script actually asks for.

    Either half alone would be satisfiable while the release page still came
    out wrong, so neither is dropped.
    """

    # Deliberately not the same regex new-release.ps1 uses: this one reads the
    # source of truth so the two can be compared. Sharing it would compare the
    # pipeline with itself.
    ENTRY = r"(?ms)^## \[%s\][^\n]*\n(.*?)(?=^## \[|\Z)"

    def source_body(self, version):
        """The half of the entry that is meant to be published."""
        with open(repo_path("CHANGELOG.md"), encoding="utf-8") as handle:
            text = handle.read()
        found = re.search(self.ENTRY % re.escape(version), text)
        self.assertIsNotNone(found, "no entry for %s" % version)
        body = found.group(1)
        marker = body.find("<!-- release-notes-end -->")
        return body[:marker] if marker >= 0 else body

    def published(self, version):
        with tempfile.TemporaryDirectory() as workdir:
            driver = os.path.join(workdir, "driver.ps1")
            out = os.path.join(workdir, "notes.txt")
            with open(driver, "w", encoding="utf-8") as handle:
                handle.write(DRIVER_TO_FILE)
            result = subprocess.run(
                [self.shell, "-NoProfile", "-NonInteractive", "-File", driver,
                 "-ReleaseScript", RELEASE_SCRIPT, "-Version", version,
                 "-Out", out],
                cwd=repo_path(), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            with open(out, encoding="utf-8") as handle:
                return handle.read()

    def versions(self):
        with open(repo_path("CHANGELOG.md"), encoding="utf-8") as handle:
            return re.findall(r"(?m)^## \[(\d+\.\d+\.\d+)\]", handle.read())

    def test_no_character_is_lost_or_replaced(self):
        for version in self.versions():
            published = self.published(version)
            self.assertNotIn("�", published,
                             "%s: the notes contain a replacement character" % version)
            wanted = {c for c in self.source_body(version) if ord(c) > 127}
            missing = wanted - set(published)
            self.assertEqual(missing, set(),
                             "%s: dropped on the way to the release page: %r"
                             % (version, sorted(missing)))

    def test_the_current_version_keeps_its_arrows(self):
        # Named separately because it is the one users act on: the four-step
        # instruction block. A count, not a set, so a partial loss shows too.
        version = self.versions()[0]
        published = self.published(version)
        self.assertEqual(published.count("→"),
                         self.source_body(version).count("→"),
                         "%s: arrows in the instructions were lost" % version)

    def test_the_release_script_writes_the_notes_as_utf8(self):
        """The half this driver cannot demonstrate: what the real script asks for.

        `gh release create --notes-file` puts the file's bytes on the page. An
        -Encoding of ascii or default here would turn every arrow into a
        question mark, and nothing else in this suite would notice.
        """
        with open(RELEASE_SCRIPT, encoding="utf-8") as handle:
            script = handle.read()
        found = re.search(r"Set-Content -Path \$notesFile\.FullName[^\n]*",
                          script)
        self.assertIsNotNone(found, "the notes file is no longer written here")
        self.assertIn("-Encoding utf8", found.group(0))

    def test_the_file_carries_no_byte_order_mark(self):
        # gh puts the file's bytes on the page as they are. A BOM would show up
        # as a stray character before the first word.
        self.assertFalse(self.published(self.versions()[0]).startswith("﻿"))


class TheRealChangelog(PowerShellTestCase):
    """Against CHANGELOG.md as it is, not a fixture.

    The fixtures prove the function behaves; this proves the file it is pointed
    at still works with it. A release publishes whatever comes out of here.
    """

    def versions(self):
        import re
        with open(repo_path("CHANGELOG.md"), encoding="utf-8") as handle:
            return re.findall(r"(?m)^## \[(\d+\.\d+\.\d+)\]", handle.read())

    def test_there_are_versions_to_check(self):
        self.assertTrue(self.versions())

    def test_every_entry_yields_notes(self):
        for version in self.versions():
            notes = self.notes_for(version, None, directory=repo_path())
            self.assertTrue(
                notes.strip(),
                "CHANGELOG.md entry for %s produces empty release notes -- "
                "the release would publish the one-line -Message instead"
                % version)

    def test_no_entry_leaks_the_maintainer_half(self):
        for version in self.versions():
            notes = self.notes_for(version, None, directory=repo_path())
            self.assertNotIn("release-notes-end", notes,
                             "%s: the marker itself is in the notes" % version)


if __name__ == "__main__":
    unittest.main()
