"""Tests for scripts/bump_version.py, the parser.__version__ / VERSION /
CHANGELOG.md contract, and the --version flag on parser.parse_save and
parser.sync.

The bump-math and changelog-manipulation tests run against temp copies of a
small synthetic changelog so they don't depend on (or mutate) the repo's
real VERSION/CHANGELOG.md. A separate pair of tests checks that the real
files are internally consistent. Every call to bump_version.main() has its
stdout captured so the test suite's own output stays clean.
"""

import contextlib
import importlib.util
import io
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from parser import __version__
from parser import parse_save
from parser import sync

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUMP_SCRIPT = PROJECT_ROOT / "scripts" / "bump_version.py"

_spec = importlib.util.spec_from_file_location("bump_version", BUMP_SCRIPT)
bump_version = importlib.util.module_from_spec(_spec)
sys.modules["bump_version"] = bump_version
_spec.loader.exec_module(bump_version)  # type: ignore[union-attr]


def _run_main_quietly(argv: list[str]) -> int:
    """Call bump_version.main(argv) with stdout swallowed, returning its exit code."""
    with contextlib.redirect_stdout(io.StringIO()):
        return bump_version.main(argv)


SAMPLE_CHANGELOG = """# Changelog

Preamble text.

## [Unreleased]

## [0.1.0] - TBD

### Added

- First thing.
- Second thing.

[Unreleased]: https://github.com/ChrisPatten/pokeclaude/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ChrisPatten/pokeclaude/releases/tag/v0.1.0
"""

SAMPLE_CHANGELOG_WITH_UNRELEASED = """# Changelog

Preamble text.

## [Unreleased]

### Added

- A new thing that hasn't shipped yet.

## [0.1.0] - 2026-01-01

### Added

- First thing.

[Unreleased]: https://github.com/ChrisPatten/pokeclaude/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ChrisPatten/pokeclaude/releases/tag/v0.1.0
"""


class TempFilesMixin:
    def _write_temp_files(self, changelog_text: str, version_text: str = "0.1.0"):
        tmpdir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        version_path = tmpdir / "VERSION"
        changelog_path = tmpdir / "CHANGELOG.md"
        version_path.write_text(version_text + "\n", encoding="utf-8")
        changelog_path.write_text(changelog_text, encoding="utf-8")
        return version_path, changelog_path


# ---------------------------------------------------------------------------
# --version on the CLIs
# ---------------------------------------------------------------------------


class ParseSaveVersionTests(unittest.TestCase):
    def test_version_flag_prints_version_and_returns(self) -> None:
        buf = io.StringIO()
        with mock.patch("sys.argv", ["parse_save", "--version"]):
            with contextlib.redirect_stdout(buf):
                parse_save.main()  # must not raise / not require a save path

        self.assertEqual(buf.getvalue().strip(), f"parse_save {__version__}")


class SyncVersionTests(unittest.TestCase):
    def test_version_flag_prints_version_and_exits_zero(self) -> None:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with self.assertRaises(SystemExit) as ctx:
                sync.main(["--version"])  # no user_id given

        self.assertEqual(ctx.exception.code, 0)
        self.assertEqual(buf.getvalue().strip(), f"parser.sync {__version__}")


# ---------------------------------------------------------------------------
# scripts/bump_version.py
# ---------------------------------------------------------------------------


class SemverMathTests(unittest.TestCase):
    def test_parse_semver_valid(self):
        self.assertEqual(bump_version.parse_semver("1.2.3"), (1, 2, 3))
        self.assertEqual(bump_version.parse_semver("0.1.0"), (0, 1, 0))

    def test_parse_semver_rejects_garbage(self):
        for bad in ["1.2", "1.2.3.4", "v1.2.3", "1.2.x", "", "1.2.03"]:
            with self.assertRaises(bump_version.BumpError):
                bump_version.parse_semver(bad)

    def test_compute_new_version_patch(self):
        self.assertEqual(bump_version.compute_new_version("0.1.0", "patch"), "0.1.1")

    def test_compute_new_version_minor_resets_patch(self):
        self.assertEqual(bump_version.compute_new_version("0.1.5", "minor"), "0.2.0")

    def test_compute_new_version_major_resets_minor_and_patch(self):
        self.assertEqual(bump_version.compute_new_version("1.4.5", "major"), "2.0.0")

    def test_compute_new_version_explicit(self):
        self.assertEqual(bump_version.compute_new_version("0.1.0", "9.9.9"), "9.9.9")

    def test_compute_new_version_rejects_invalid_explicit(self):
        with self.assertRaises(bump_version.BumpError):
            bump_version.compute_new_version("0.1.0", "not-a-version")


class ChangelogSectionMoveTests(unittest.TestCase):
    def test_bump_moves_unreleased_into_new_dated_section(self):
        new_text = bump_version.bump_changelog(
            SAMPLE_CHANGELOG_WITH_UNRELEASED, "0.2.0", "2026-03-01"
        )
        _, sections, _ = bump_version.parse_changelog(new_text)
        versions = [s.version for s in sections]
        self.assertEqual(versions, ["Unreleased", "0.2.0", "0.1.0"])

        unreleased = sections[0]
        self.assertTrue(bump_version.unreleased_is_empty(unreleased.body))

        new_section = sections[1]
        self.assertEqual(new_section.date, "2026-03-01")
        self.assertIn("A new thing that hasn't shipped yet.", new_section.body)

    def test_bump_refuses_when_unreleased_is_empty(self):
        with self.assertRaises(bump_version.BumpError):
            bump_version.bump_changelog(SAMPLE_CHANGELOG, "0.2.0", "2026-03-01")

    def test_bump_allow_empty_overrides_refusal(self):
        new_text = bump_version.bump_changelog(
            SAMPLE_CHANGELOG, "0.2.0", "2026-03-01", allow_empty=True
        )
        _, sections, _ = bump_version.parse_changelog(new_text)
        self.assertEqual([s.version for s in sections], ["Unreleased", "0.2.0", "0.1.0"])

    def test_bump_refuses_duplicate_version(self):
        with self.assertRaises(bump_version.BumpError):
            bump_version.bump_changelog(
                SAMPLE_CHANGELOG_WITH_UNRELEASED, "0.1.0", "2026-03-01", allow_empty=True
            )


class CompareLinkTests(unittest.TestCase):
    def test_links_after_first_bump(self):
        new_text = bump_version.bump_changelog(
            SAMPLE_CHANGELOG_WITH_UNRELEASED, "0.2.0", "2026-03-01"
        )
        self.assertIn(
            "[Unreleased]: https://github.com/ChrisPatten/pokeclaude/compare/v0.2.0...HEAD",
            new_text,
        )
        self.assertIn(
            "[0.2.0]: https://github.com/ChrisPatten/pokeclaude/compare/v0.1.0...v0.2.0",
            new_text,
        )
        self.assertIn(
            "[0.1.0]: https://github.com/ChrisPatten/pokeclaude/releases/tag/v0.1.0",
            new_text,
        )

    def test_links_with_only_unreleased_and_one_release(self):
        links, order = bump_version.rewrite_links(
            [bump_version.Section("Unreleased", "", ""), bump_version.Section("0.1.0", "TBD", "")]
        )
        self.assertEqual(order, ["Unreleased", "0.1.0"])
        self.assertEqual(
            links["Unreleased"], "https://github.com/ChrisPatten/pokeclaude/compare/v0.1.0...HEAD"
        )
        self.assertEqual(
            links["0.1.0"], "https://github.com/ChrisPatten/pokeclaude/releases/tag/v0.1.0"
        )


class ReleaseCurrentTests(unittest.TestCase):
    def test_release_current_dates_tbd_section(self):
        new_text = bump_version.release_current_changelog(SAMPLE_CHANGELOG, "0.1.0", "2026-05-05")
        _, sections, _ = bump_version.parse_changelog(new_text)
        target = next(s for s in sections if s.version == "0.1.0")
        self.assertEqual(target.date, "2026-05-05")
        # Unreleased must be untouched (still empty, still first).
        self.assertEqual(sections[0].version, "Unreleased")
        self.assertTrue(bump_version.unreleased_is_empty(sections[0].body))

    def test_release_current_refuses_when_not_tbd(self):
        with self.assertRaises(bump_version.BumpError):
            bump_version.release_current_changelog(
                SAMPLE_CHANGELOG_WITH_UNRELEASED, "0.1.0", "2026-05-05"
            )

    def test_release_current_refuses_missing_version(self):
        with self.assertRaises(bump_version.BumpError):
            bump_version.release_current_changelog(SAMPLE_CHANGELOG, "9.9.9", "2026-05-05")


class ExtractNotesTests(unittest.TestCase):
    def test_extract_notes_returns_section_body(self):
        notes = bump_version.extract_notes(SAMPLE_CHANGELOG, "0.1.0")
        self.assertIn("First thing.", notes)
        self.assertIn("Second thing.", notes)
        self.assertNotIn("## [0.1.0]", notes)
        self.assertNotIn("[Unreleased]:", notes)

    def test_extract_notes_missing_version_raises(self):
        with self.assertRaises(bump_version.BumpError):
            bump_version.extract_notes(SAMPLE_CHANGELOG, "9.9.9")

    def test_extract_notes_empty_section_returns_empty_string(self):
        notes = bump_version.extract_notes(SAMPLE_CHANGELOG, "Unreleased")
        self.assertEqual(notes, "")


class CliEndToEndTests(TempFilesMixin, unittest.TestCase):
    def test_main_bump_writes_files_and_prints_next_steps(self):
        version_path, changelog_path = self._write_temp_files(
            SAMPLE_CHANGELOG_WITH_UNRELEASED, "0.1.0"
        )
        exit_code = _run_main_quietly(
            [
                "minor",
                "--version-file",
                str(version_path),
                "--changelog-file",
                str(changelog_path),
            ]
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(version_path.read_text(encoding="utf-8").strip(), "0.2.0")
        new_changelog = changelog_path.read_text(encoding="utf-8")
        self.assertIn("## [0.2.0] -", new_changelog)

    def test_main_dry_run_does_not_write_files(self):
        version_path, changelog_path = self._write_temp_files(
            SAMPLE_CHANGELOG_WITH_UNRELEASED, "0.1.0"
        )
        original_version = version_path.read_text(encoding="utf-8")
        original_changelog = changelog_path.read_text(encoding="utf-8")

        exit_code = _run_main_quietly(
            [
                "minor",
                "--dry-run",
                "--version-file",
                str(version_path),
                "--changelog-file",
                str(changelog_path),
            ]
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(version_path.read_text(encoding="utf-8"), original_version)
        self.assertEqual(changelog_path.read_text(encoding="utf-8"), original_changelog)

    def test_main_release_current(self):
        version_path, changelog_path = self._write_temp_files(SAMPLE_CHANGELOG, "0.1.0")
        exit_code = _run_main_quietly(
            [
                "--release-current",
                "--version-file",
                str(version_path),
                "--changelog-file",
                str(changelog_path),
            ]
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(version_path.read_text(encoding="utf-8").strip(), "0.1.0")
        new_changelog = changelog_path.read_text(encoding="utf-8")
        self.assertRegex(new_changelog, r"## \[0\.1\.0\] - \d{4}-\d{2}-\d{2}")

    def test_main_refuses_empty_unreleased_without_flag(self):
        version_path, changelog_path = self._write_temp_files(SAMPLE_CHANGELOG, "0.1.0")
        exit_code = _run_main_quietly(
            [
                "minor",
                "--version-file",
                str(version_path),
                "--changelog-file",
                str(changelog_path),
            ]
        )
        self.assertEqual(exit_code, 1)
        # Nothing should have been written on failure.
        self.assertEqual(version_path.read_text(encoding="utf-8").strip(), "0.1.0")

    def test_main_extract_notes(self):
        version_path, changelog_path = self._write_temp_files(SAMPLE_CHANGELOG, "0.1.0")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exit_code = bump_version.main(
                [
                    "--extract-notes",
                    "0.1.0",
                    "--version-file",
                    str(version_path),
                    "--changelog-file",
                    str(changelog_path),
                ]
            )
        self.assertEqual(exit_code, 0)
        self.assertIn("First thing.", buf.getvalue())


class RepoConsistencyTests(unittest.TestCase):
    """Sanity checks against the real, committed VERSION and CHANGELOG.md."""

    def test_parser_version_matches_version_file(self):
        version_text = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(__version__, version_text)
        # And it should actually look like a version, not the fallback.
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")

    def test_changelog_has_section_for_current_version(self):
        current_version = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        changelog_text = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        pattern = re.compile(rf"^## \[{re.escape(current_version)}\]", re.MULTILINE)
        self.assertRegex(changelog_text, pattern)


if __name__ == "__main__":
    unittest.main()
