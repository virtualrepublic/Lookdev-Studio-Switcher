"""The two stamps, and the embedded copy of the add-on.

Neither stamp can be *verified* in a clone or on a CI runner: both read files
in `_local/`, which is git-ignored and never present. `new-release.ps1` knows
that and degrades to a warning. So what is checked here is the machinery rather
than a particular file:

* `check_snapshots()` refuses in each of the three ways it is supposed to;
* the shape `toolchain_stamp()` produces is the shape `new-release.ps1`
  reproduces with Get-FileHash, and the two lists of inputs still agree;
* the copy of the add-on embedded in the installer is the add-on.

The last one is the only stamp-like comparison that sees anything real in a
clone, because both files are tracked.
"""

import ast
import hashlib
import os
import re
import unittest

from _support import cs, mm, read_bytes, read_text, repo_path


def snapshot(stamp, **extra):
    out = {"blend_file": "x.blend", "dumper_stamp": stamp}
    out.update(extra)
    return out


def the_real_dumper_digest():
    return mm.file_digest(repo_path("tools", "dump_scene.py"))


class StaleSnapshotsAreRefused(unittest.TestCase):
    """The check that replaced a traceback halfway through a release run.

    The generator reads snapshots, not scenes, so a changed dump_scene.py makes
    every existing snapshot stale -- and nothing said so. All three refusals
    are fatal and happen before anything is written.
    """

    def test_a_snapshot_without_a_stamp_is_refused(self):
        with self.assertRaises(SystemExit) as caught:
            mm.check_snapshots(snapshot(None), snapshot("a" * 64), "a.json",
                               "b.json")
        self.assertIn("no dumper stamp", str(caught.exception))

    def test_two_different_dumpers_are_refused(self):
        with self.assertRaises(SystemExit) as caught:
            mm.check_snapshots(snapshot("a" * 64), snapshot("b" * 64),
                               "a.json", "b.json")
        self.assertIn("different versions", str(caught.exception))

    def test_a_dumper_that_has_changed_since_is_refused(self):
        # Both snapshots agree with each other and neither agrees with the
        # dumper on disk: the case that shipped an installer built from data
        # the current dumper would never have written.
        stale = "c" * 64
        with self.assertRaises(SystemExit) as caught:
            mm.check_snapshots(snapshot(stale), snapshot(stale), "a.json",
                               "b.json")
        self.assertIn("has changed since", str(caught.exception))

    def test_matching_snapshots_pass(self):
        current = the_real_dumper_digest()
        self.assertIsNotNone(current, "tools/dump_scene.py is missing")
        mm.check_snapshots(snapshot(current), snapshot(current), "a.json",
                           "b.json")

    def test_the_refusal_names_the_files(self):
        with self.assertRaises(SystemExit) as caught:
            mm.check_snapshots(snapshot(None), snapshot(None),
                               "_local/snap_original.json",
                               "_local/snap_modified.json")
        self.assertIn("_local/snap_original.json", str(caught.exception))

    def test_the_stamp_never_shows_up_as_a_difference(self):
        # compare_scenes ignores it, so a new dumper does not report itself as
        # a change in every scene.
        before = snapshot("a" * 64, objects={})
        after = snapshot("b" * 64, objects={})
        self.assertEqual(cs.diff(before, after), [])


class TheToolchainStampKeepsItsShape(unittest.TestCase):
    """One value, two readers: Python writes it, PowerShell recomputes it.

    The combined stamp is the SHA-256 over `label:digest` lines joined with
    "\\n" -- a shape chosen because `new-release.ps1` has to be able to
    reproduce it with Get-FileHash and no bit fiddling. If the two sides ever
    disagree about the inputs or their order, the release check compares two
    unrelated numbers and refuses every release, or worse, stops meaning
    anything.
    """

    def a_few_files(self):
        import tempfile
        workdir = tempfile.TemporaryDirectory()
        self.addCleanup(workdir.cleanup)
        paths = {}
        for name, content in (("snap_a", b"{}"), ("snap_b", b"{ }"),
                              ("switcher", b"# add-on"),
                              ("workspace", b"\x00blend")):
            path = os.path.join(workdir.name, name)
            with open(path, "wb") as handle:
                handle.write(content)
            paths[name] = path
        return paths

    def test_the_wire_format_is_label_colon_digest_joined_by_newlines(self):
        paths = self.a_few_files()
        stamp, parts = mm.toolchain_stamp(paths["snap_a"], paths["snap_b"],
                                          paths["switcher"], paths["workspace"])
        joined = "\n".join("%s:%s" % pair for pair in parts)
        self.assertEqual(stamp,
                         hashlib.sha256(joined.encode("utf-8")).hexdigest())

    def test_every_part_is_a_lowercase_sha256(self):
        paths = self.a_few_files()
        _stamp, parts = mm.toolchain_stamp(paths["snap_a"], paths["snap_b"],
                                           paths["switcher"], paths["workspace"])
        for label, digest in parts:
            self.assertRegex(digest, r"^[0-9a-f]{64}$",
                             "%s is not a lowercase sha256" % label)

    def test_a_missing_input_becomes_a_dash_rather_than_an_error(self):
        # A clone has no workspace blend. The stamp must still compute, or the
        # generator could not run at all without _local/.
        paths = self.a_few_files()
        _stamp, parts = mm.toolchain_stamp(paths["snap_a"], paths["snap_b"],
                                           paths["switcher"], "nowhere.blend")
        self.assertEqual(dict(parts)["workspace"], "-")

    def test_a_changed_input_changes_the_stamp(self):
        paths = self.a_few_files()
        first, _parts = mm.toolchain_stamp(paths["snap_a"], paths["snap_b"],
                                           paths["switcher"], paths["workspace"])
        with open(paths["switcher"], "wb") as handle:
            handle.write(b"# add-on, edited")
        second, _parts = mm.toolchain_stamp(paths["snap_a"], paths["snap_b"],
                                            paths["switcher"], paths["workspace"])
        self.assertNotEqual(first, second)

    def test_the_labels_match_the_ones_the_release_script_hashes(self):
        """The drift that would break the check without anyone noticing.

        new-release.ps1 builds its own list of (label, path) pairs. Add an
        input on the Python side and forget the PowerShell side, and the two
        stamps stop being comparable.
        """
        script = read_text("tools", "new-release.ps1")
        block = re.search(r"\$stampInputs\s*=\s*@\((.*?)\n    \)", script, re.S)
        self.assertIsNotNone(block, "could not find $stampInputs")
        labels = re.findall(r"@\('([^']+)',", block.group(1))
        self.assertEqual(tuple(labels), mm.STAMP_PARTS)

    def test_the_release_script_reads_the_same_algorithm(self):
        script = read_text("tools", "new-release.ps1")
        self.assertIn("Get-FileHash", script)
        self.assertIn("-Algorithm SHA256", script)
        self.assertIn("SHA256]::HashData", script)


class TheEmbeddedAddOnIsTheAddOn(unittest.TestCase):
    """The one stamp-like check that sees something real in a clone.

    Both files are tracked, so this runs on any checkout. It is the check
    behind the open item in CLAUDE.md -- verified by comparison rather than by
    a checkbox somebody once ticked.
    """

    def sources(self):
        installer = read_bytes("setup_lookdev_scene.py")
        switcher = read_bytes("lookdev_switcher.py")
        found = re.search(rb"TOOL_SOURCE = r'''(.*?)'''", installer, re.S)
        self.assertIsNotNone(found, "no TOOL_SOURCE block in the installer")
        return found.group(1), switcher

    def normalise(self, data):
        """Compare content, not line endings.

        make_migration.py writes the installer in text mode, so on Windows the
        embedded block carries CRLF while lookdev_switcher.py is LF -- one byte
        per line apart, no content difference. git stores both as LF, so a
        byte-for-byte comparison passes in CI and fails on a freshly generated
        working copy. Which would be a test that reports where it ran.
        """
        return data.replace(b"\r\n", b"\n")

    def test_the_embedded_copy_is_the_add_on(self):
        embedded, switcher = self.sources()
        self.assertEqual(self.normalise(embedded), self.normalise(switcher),
                         "the installer carries a different version of the "
                         "add-on -- regenerate it")

    def test_they_agree_on_the_version(self):
        # The release script refuses when bl_info and the header line disagree.
        # This catches the same drift a push earlier.
        embedded, switcher = self.sources()
        pattern = rb'"version"\s*:\s*\((\d+),\s*(\d+),\s*(\d+)\)'
        self.assertEqual(re.search(pattern, embedded).groups(),
                         re.search(pattern, switcher).groups())

    def test_the_add_on_can_still_be_embedded(self):
        # read_tool refuses a source that would break out of the r'''...'''
        # it is embedded in. Checked against the real file, because the failure
        # would only show up at the next generation otherwise.
        source = mm.read_tool(repo_path("lookdev_switcher.py"))
        self.assertNotIn("'''", source)
        self.assertFalse(source.endswith("\\"))

    def test_the_add_on_parses(self):
        # It is executed by Blender, never by the tests -- but a syntax error
        # would be embedded into the installer and shipped.
        source = read_text("lookdev_switcher.py")
        ast.parse(source)

    def test_the_installer_parses(self):
        source = read_text("setup_lookdev_scene.py")
        ast.parse(source)


class TheInstallerCarriesAToolchainStamp(unittest.TestCase):
    """Was a known gap until 2026-08-15; now a plain check.

    `new-release.ps1` recomputes the TOOLCHAIN STAMP from the installer header
    and refuses to release a file that was not regenerated after the toolchain
    moved. The installer used to carry no such line -- it predated the check --
    so the release script printed "predates the check" and released anyway.
    It was marked as an expected failure here until the regeneration that
    carried the phase-order fix for defect 13 gave it one.

    What this cannot do is verify the stamp. That needs the snapshots and the
    exported interface in `_local/`, which no clone has. It checks that the
    line is there and well formed, so a regeneration that loses it is caught
    before the release script has to notice.
    """

    HEADER = re.compile(r"(?m)^#\s+TOOLCHAIN STAMP\s+([0-9a-f]{64})\s*$")

    def test_the_installer_has_a_stamp(self):
        text = read_text("setup_lookdev_scene.py")
        self.assertIsNotNone(self.HEADER.search(text),
                             "no TOOLCHAIN STAMP in the installer header")

    def test_the_generator_would_write_one(self):
        # The gap is in the shipped file, not in the generator. Freshly
        # generated output carries the header the release script looks for.
        from _support import generate
        source = generate([], stamp="f" * 64,
                          stamp_parts=[("make_migration", "a" * 64)])
        self.assertIsNotNone(self.HEADER.search(source))

    def test_the_release_script_looks_for_exactly_that_line(self):
        script = read_text("tools", "new-release.ps1")
        self.assertIn(r"^#\s+TOOLCHAIN STAMP\s+([0-9a-f]{64})\s*$", script)


if __name__ == "__main__":
    unittest.main()
