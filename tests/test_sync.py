"""Tests for parser.sync — the deterministic save-sync CLI.

Everything runs against a tempdir passed via --users-dir / users_dir=, so
nothing here touches the real users/ directory. The real .srm parser is
mocked out (via unittest.mock.patch on parser.sync.parse_save) since
workstream A is still building out full parser output; these tests only
need parser.sync's own orchestration logic to be correct.
"""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from parser import sync


def _full_box_mon(pid, species_name, nickname=None, level=20, held_item="None", moves=None):
    """A hand-written, contract-shaped box Mon with every field populated."""
    return {
        "slot": 0,
        "pid": pid,
        "species_id": 7,
        "species_name": species_name,
        "nickname": nickname or species_name.upper(),
        "types": ["Water"],
        "ability": "Torrent",
        "level": level,
        "experience": level * 100,
        "nature": "Modest",
        "nature_effect": "SpAtk↑, Atk↓",
        "held_item": held_item,
        "moves": moves
        if moves is not None
        else [
            {"slot": 0, "move_id": 55, "name": "Water Gun", "type": "Water", "pp": 25, "pp_max": 25},
            {"slot": 1, "move_id": 33, "name": "Tackle", "type": "Normal", "pp": 35, "pp_max": 35},
        ],
        "is_egg": False,
    }


def _sample_parsed_save(location_name="Petalburg City", badges_count=1, money=500, boxes=None):
    """A hand-written stand-in for parser.parse_save.parse()'s output."""
    if boxes is None:
        boxes = [{"box_index": 1, "name": "BOX 1", "pokemon": []}]
    return {
        "trainer": {
            "name": "May",
            "gender": "female",
            "trainer_id": 1,
            "playtime": {"hours": 1, "minutes": 0, "seconds": 0},
            "money": money,
        },
        "badges": {"count": badges_count, "obtained": ["Stone Badge"][:badges_count]},
        "location": {"map_bank": 0, "map_id": 0, "name": location_name, "known": True},
        "party": [
            {
                "slot": 0,
                "pid": "0x1",
                "species_id": 1,
                "species_name": "Torchic",
                "nickname": "TORCHIC",
                "types": ["Fire"],
                "ability": "Blaze",
                "level": 5,
                "experience": 125,
                "nature": "Adamant",
                "nature_effect": "Atk↑, SpAtk↓",
                "held_item": "None",
                "moves": [{"slot": 0, "move_id": 1, "name": "Scratch", "type": "Normal", "pp": 35, "pp_max": 35}],
                "is_egg": False,
                "status": "none",
                "hp": {"current": 20, "max": 20},
                "stats": {"attack": 10, "defense": 9, "speed": 8, "sp_atk": 7, "sp_def": 7},
            }
        ],
        "boxes": boxes,
        "daycare": [],
        "inventory": {"pc": [], "items": [], "key_items": [], "balls": [], "tms_hms": [], "berries": []},
        "pokedex": {"seen": 10, "caught": 5},
        "save_metadata": {
            "save_slot": "A",
            "save_index": 1,
            "checksum_valid": True,
            "invalid_sections": [],
            "parsed_at": "2026-04-01T00:00:00Z",
        },
        "warnings": [],
    }


SAMPLE_MEMORY_MD = """# Memory

Some other content.

## Save History

| Sync # | Date | Location | Badges | MD5 Hash |
|--------|------|----------|--------|---------|
| 1 | 2026-04-01 | Fallarbor Town | 3 | aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa |
| 2 | 2026-04-02 | [TBD] | 3 | bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb |

## Something Else

More text that should not be parsed as table rows.
"""


class TempUserMixin:
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.users_dir = Path(self._tmp.name) / "users"
        self.user_id = "12345"
        self.user_dir = self.users_dir / self.user_id
        (self.user_dir / "memory").mkdir(parents=True)
        (self.user_dir / "saves").mkdir(parents=True)
        self.config = {
            "game": "sapphire",
            "gen": 3,
            "save_filename": "sapphire.srm",
            "device": {
                "host": "root@192.0.2.1",
                "save_path": "/mnt/SDCARD/saves/Pokemon Sapphire (USA).srm",
                "ssh_key": "trimui_key",
            },
        }
        (self.user_dir / "config.json").write_text(json.dumps(self.config))
        (self.user_dir / "trimui_key").write_text("fake-key")

    def _write_local_save(self, name="incoming.srm", content=b"fake save bytes"):
        path = Path(self._tmp.name) / name
        path.write_bytes(content)
        return path


class BootstrapHistoryTests(TempUserMixin, unittest.TestCase):
    def test_bootstrap_seeds_from_memory_md_table(self):
        (self.user_dir / "memory" / "MEMORY.md").write_text(SAMPLE_MEMORY_MD)

        history = sync._load_or_bootstrap_history(self.user_id, self.users_dir, self.config)

        self.assertEqual(len(history["syncs"]), 2)
        self.assertEqual(history["syncs"][0]["sync_number"], 1)
        self.assertEqual(history["syncs"][0]["location"], "Fallarbor Town")
        self.assertEqual(history["syncs"][0]["badges"], 3)
        self.assertEqual(history["syncs"][0]["md5"], "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        self.assertEqual(history["syncs"][0]["has_snapshot"], False)
        # "[TBD]" location normalizes to None.
        self.assertIsNone(history["syncs"][1]["location"])

        history_path = self.user_dir / "saves" / "history.json"
        self.assertTrue(history_path.exists())
        on_disk = json.loads(history_path.read_text())
        self.assertEqual(on_disk, history)

    def test_bootstrap_snapshots_existing_latest_save_when_md5_matches_last_row(self):
        (self.user_dir / "memory" / "MEMORY.md").write_text(SAMPLE_MEMORY_MD)
        latest = self.user_dir / "saves" / "sapphire.srm"
        latest.write_bytes(b"whatever bytes hash to bbbb...")

        parsed = _sample_parsed_save()
        with mock.patch("parser.sync._md5_file", return_value="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"):
            with mock.patch("parser.sync.parse_save", return_value=parsed) as mocked_parse:
                history = sync._load_or_bootstrap_history(self.user_id, self.users_dir, self.config)
                mocked_parse.assert_called_once()

        last = history["syncs"][-1]
        self.assertTrue(last["has_snapshot"])
        snapshot_path = self.user_dir / "saves" / "snapshots" / "002.json"
        self.assertTrue(snapshot_path.exists())
        self.assertEqual(json.loads(snapshot_path.read_text()), parsed)
        archive_files = list((self.user_dir / "saves" / "archive").glob("002_*bbbbbbbb*.srm"))
        self.assertEqual(len(archive_files), 1)

    def test_missing_memory_md_yields_empty_history(self):
        history = sync._load_or_bootstrap_history(self.user_id, self.users_dir, self.config)
        self.assertEqual(history, {"syncs": []})


class DoSyncLocalTests(TempUserMixin, unittest.TestCase):
    def test_first_local_sync_has_no_diff(self):
        local = self._write_local_save(content=b"save-v1")
        parsed = _sample_parsed_save(location_name="Petalburg City")

        with mock.patch("parser.sync.parse_save", return_value=parsed):
            result = sync.do_sync(self.user_id, self.users_dir, local_path=str(local))

        self.assertEqual(result["status"], "synced")
        self.assertEqual(result["sync_number"], 1)
        self.assertIsNone(result["previous_md5"])
        self.assertIsNone(result["diff"])
        # do_sync's return value is always the FULL save — compaction only
        # happens in main()'s stdout printing, never here.
        self.assertEqual(result["save"], parsed)

        latest = self.user_dir / "saves" / "sapphire.srm"
        self.assertTrue(latest.exists())
        self.assertEqual(latest.read_bytes(), b"save-v1")

        snapshot_path = self.user_dir / "saves" / "snapshots" / "001.json"
        self.assertEqual(json.loads(snapshot_path.read_text()), parsed)

        # "date" matches what was written into history.json for this sync,
        # and "snapshot" points at the full snapshot file just checked above.
        history = json.loads((self.user_dir / "saves" / "history.json").read_text())
        self.assertEqual(len(history["syncs"]), 1)
        self.assertTrue(history["syncs"][0]["has_snapshot"])
        self.assertEqual(result["date"], history["syncs"][0]["date"])
        self.assertTrue(result["snapshot"].endswith("001.json"))
        self.assertTrue(Path(result["snapshot"]).exists() or (self.user_dir / "saves" / "snapshots" / "001.json").exists())

        archive = list((self.user_dir / "saves" / "archive").glob("001_*.srm"))
        self.assertEqual(len(archive), 1)

        # No leftover tmp files.
        leftovers = list((self.user_dir / "saves").glob("pull_*"))
        self.assertEqual(leftovers, [])

    def test_second_sync_produces_a_diff_against_the_previous_snapshot(self):
        local1 = self._write_local_save("v1.srm", content=b"save-v1")
        parsed1 = _sample_parsed_save(location_name="Petalburg City", badges_count=1, money=500)
        with mock.patch("parser.sync.parse_save", return_value=parsed1):
            sync.do_sync(self.user_id, self.users_dir, local_path=str(local1))

        local2 = self._write_local_save("v2.srm", content=b"save-v2")
        parsed2 = _sample_parsed_save(location_name="Rustboro City", badges_count=2, money=800)
        with mock.patch("parser.sync.parse_save", return_value=parsed2):
            result2 = sync.do_sync(self.user_id, self.users_dir, local_path=str(local2))

        self.assertEqual(result2["status"], "synced")
        self.assertEqual(result2["sync_number"], 2)
        self.assertIsNotNone(result2["diff"])
        self.assertEqual(result2["diff"]["location"], {"from": "Petalburg City", "to": "Rustboro City"})
        self.assertEqual(result2["diff"]["money"], {"from": 500, "to": 800, "delta": 300})

    def test_unchanged_dedupes_against_last_history_entry(self):
        local1 = self._write_local_save("v1.srm", content=b"save-v1")
        parsed1 = _sample_parsed_save()
        with mock.patch("parser.sync.parse_save", return_value=parsed1):
            first = sync.do_sync(self.user_id, self.users_dir, local_path=str(local1))
        self.assertEqual(first["status"], "synced")

        # Same bytes -> same md5 -> unchanged, parse_save must not even be called.
        local_again = self._write_local_save("v1_again.srm", content=b"save-v1")
        with mock.patch("parser.sync.parse_save") as mocked_parse:
            result = sync.do_sync(self.user_id, self.users_dir, local_path=str(local_again))
            mocked_parse.assert_not_called()

        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(result["sync_number"], 1)
        self.assertEqual(result["date"], first["date"])

        # No leftover tmp files after the dedupe path either.
        leftovers = list((self.user_dir / "saves").glob("pull_*"))
        self.assertEqual(leftovers, [])

    def test_invalid_save_is_rejected_and_latest_save_is_untouched(self):
        # Seed a valid "current" latest save first.
        local1 = self._write_local_save("v1.srm", content=b"save-v1")
        parsed1 = _sample_parsed_save()
        with mock.patch("parser.sync.parse_save", return_value=parsed1):
            sync.do_sync(self.user_id, self.users_dir, local_path=str(local1))
        latest_before = (self.user_dir / "saves" / "sapphire.srm").read_bytes()

        bad_local = self._write_local_save("bad.srm", content=b"corrupted-bytes")
        bad_parsed = _sample_parsed_save()
        bad_parsed["save_metadata"]["checksum_valid"] = False
        with mock.patch("parser.sync.parse_save", return_value=bad_parsed):
            with self.assertRaises(sync.SyncError) as ctx:
                sync.do_sync(self.user_id, self.users_dir, local_path=str(bad_local))

        self.assertEqual(ctx.exception.payload["status"], "invalid_save")
        self.assertEqual(ctx.exception.exit_code, 3)

        # Latest save untouched.
        self.assertEqual((self.user_dir / "saves" / "sapphire.srm").read_bytes(), latest_before)

        # Rejected file kept under saves/, named by md5 prefix.
        rejected = list((self.user_dir / "saves").glob("rejected_*.srm"))
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].read_bytes(), b"corrupted-bytes")

        # History was not appended to.
        history = json.loads((self.user_dir / "saves" / "history.json").read_text())
        self.assertEqual(len(history["syncs"]), 1)

    def test_parser_exception_is_also_treated_as_invalid_save(self):
        local = self._write_local_save(content=b"garbage")
        with mock.patch("parser.sync.parse_save", side_effect=ValueError("bad sector checksum")):
            with self.assertRaises(sync.SyncError) as ctx:
                sync.do_sync(self.user_id, self.users_dir, local_path=str(local))

        self.assertEqual(ctx.exception.payload["status"], "invalid_save")
        self.assertIn("bad sector checksum", ctx.exception.payload["error"])
        self.assertEqual(ctx.exception.exit_code, 3)

    def test_missing_config_raises_clear_error(self):
        (self.user_dir / "config.json").unlink()
        with self.assertRaises(sync.SyncError) as ctx:
            sync.do_sync(self.user_id, self.users_dir, local_path=str(self._write_local_save()))
        self.assertEqual(ctx.exception.exit_code, 1)
        self.assertIn("config", ctx.exception.payload["error"].lower())


class ScpPullFailureTests(TempUserMixin, unittest.TestCase):
    def test_scp_failure_is_reported_as_pull_failed(self):
        failed = subprocess.CompletedProcess(args=["scp"], returncode=1, stdout="", stderr="ssh: connect timed out")
        with mock.patch("parser.sync.subprocess.run", return_value=failed) as mocked_run:
            with self.assertRaises(sync.SyncError) as ctx:
                sync.do_sync(self.user_id, self.users_dir, local_path=None)
            mocked_run.assert_called_once()

        self.assertEqual(ctx.exception.payload["status"], "pull_failed")
        self.assertIn("connect timed out", ctx.exception.payload["error"])
        self.assertEqual(ctx.exception.exit_code, 2)

        # No leftover tmp files after a failed pull.
        leftovers = list((self.user_dir / "saves").glob("pull_*"))
        self.assertEqual(leftovers, [])

    def test_scp_command_leaves_remote_path_unquoted_and_uses_expected_flags(self):
        # Modern OpenSSH scp (9.0+, incl. macOS default) uses SFTP and does
        # NOT forward the remote path through a shell — quoting it makes the
        # quotes part of the literal filename and scp fails with "No such
        # file or directory". The path must be passed unquoted as a single
        # argv item.
        ok = subprocess.CompletedProcess(args=["scp"], returncode=0, stdout="", stderr="")
        with mock.patch("parser.sync.subprocess.run", return_value=ok) as mocked_run:
            dest = self.user_dir / "saves" / "tmp_target.srm"
            sync._scp_pull(self.config, self.user_dir, dest)

        args = mocked_run.call_args[0][0]
        self.assertEqual(args[0], "scp")
        self.assertIn("-q", args)
        self.assertIn("-i", args)
        self.assertIn(str(self.user_dir / "trimui_key"), args)
        self.assertIn("-o", args)
        self.assertIn("ConnectTimeout=10", args)
        self.assertIn("BatchMode=yes", args)
        remote_arg = args[-2]
        expected_remote = f"root@192.0.2.1:{self.config['device']['save_path']}"
        self.assertEqual(remote_arg, expected_remote)
        self.assertNotIn("'", remote_arg)

    def test_scp_failure_uses_only_last_stderr_lines(self):
        noisy_stderr = (
            "Warning: the post-quantum key exchange method requires...\n"
            "(a bunch more banner noise)\n"
            "(even more banner noise)\n"
            "(yet more banner noise)\n"
            "\n"
            "scp: /mnt/SDCARD/saves/Pokemon Sapphire (USA).srm: No such file or directory\n"
        )
        failed = subprocess.CompletedProcess(args=["scp"], returncode=1, stdout="", stderr=noisy_stderr)
        with mock.patch("parser.sync.subprocess.run", return_value=failed):
            with self.assertRaises(sync.SyncError) as ctx:
                sync.do_sync(self.user_id, self.users_dir, local_path=None)

        self.assertEqual(ctx.exception.payload["status"], "pull_failed")
        self.assertIn("No such file or directory", ctx.exception.payload["error"])
        self.assertNotIn("post-quantum", ctx.exception.payload["error"])


class DiffModeTests(TempUserMixin, unittest.TestCase):
    def test_diff_mode_uses_last_two_snapshots_by_default(self):
        parsed1 = _sample_parsed_save(location_name="Petalburg City", money=100)
        parsed2 = _sample_parsed_save(location_name="Rustboro City", money=200)
        with mock.patch("parser.sync.parse_save", return_value=parsed1):
            sync.do_sync(self.user_id, self.users_dir, local_path=str(self._write_local_save("v1.srm", b"1")))
        with mock.patch("parser.sync.parse_save", return_value=parsed2):
            sync.do_sync(self.user_id, self.users_dir, local_path=str(self._write_local_save("v2.srm", b"2")))

        result = sync.do_diff(self.user_id, self.users_dir, None, None)

        self.assertEqual(result["status"], "diff")
        self.assertEqual(result["from"], 1)
        self.assertEqual(result["to"], 2)
        self.assertEqual(result["diff"]["location"], {"from": "Petalburg City", "to": "Rustboro City"})

    def test_diff_mode_with_explicit_from_to(self):
        parsed1 = _sample_parsed_save(money=100)
        parsed2 = _sample_parsed_save(money=200)
        parsed3 = _sample_parsed_save(money=300)
        with mock.patch("parser.sync.parse_save", return_value=parsed1):
            sync.do_sync(self.user_id, self.users_dir, local_path=str(self._write_local_save("v1.srm", b"1")))
        with mock.patch("parser.sync.parse_save", return_value=parsed2):
            sync.do_sync(self.user_id, self.users_dir, local_path=str(self._write_local_save("v2.srm", b"2")))
        with mock.patch("parser.sync.parse_save", return_value=parsed3):
            sync.do_sync(self.user_id, self.users_dir, local_path=str(self._write_local_save("v3.srm", b"3")))

        result = sync.do_diff(self.user_id, self.users_dir, 1, 3)

        self.assertEqual(result["from"], 1)
        self.assertEqual(result["to"], 3)
        self.assertEqual(result["diff"]["money"], {"from": 100, "to": 300, "delta": 200})

    def test_diff_mode_requires_at_least_two_snapshots(self):
        parsed1 = _sample_parsed_save()
        with mock.patch("parser.sync.parse_save", return_value=parsed1):
            sync.do_sync(self.user_id, self.users_dir, local_path=str(self._write_local_save("v1.srm", b"1")))

        with self.assertRaises(sync.SyncError) as ctx:
            sync.do_diff(self.user_id, self.users_dir, None, None)
        self.assertEqual(ctx.exception.exit_code, 1)

    def test_diff_mode_without_any_history_raises_clear_error(self):
        with self.assertRaises(sync.SyncError) as ctx:
            sync.do_diff(self.user_id, self.users_dir, None, None)
        self.assertEqual(ctx.exception.exit_code, 1)


class CompactStdoutTests(TempUserMixin, unittest.TestCase):
    """Box Mons in stdout's "save.boxes" are compacted; everything else
    (snapshots on disk, do_sync's return value, party/daycare) stays full."""

    def _boxes_with_two_mons(self):
        return [
            {
                "box_index": 1,
                "name": "BOX 1",
                "pokemon": [
                    _full_box_mon("0xB1", "Magikarp"),  # default nickname -> dropped
                    _full_box_mon("0xB2", "Feebas", nickname="Lucky"),  # custom -> kept
                ],
            }
        ]

    def _run_main(self, argv):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exit_code = sync.main(argv)
        return exit_code, json.loads(buf.getvalue().strip())

    def test_stdout_boxes_are_compact_by_default(self):
        local = self._write_local_save(content=b"save-v1")
        parsed = _sample_parsed_save(boxes=self._boxes_with_two_mons())
        argv = [self.user_id, "--local", str(local), "--users-dir", str(self.users_dir)]

        with mock.patch("parser.sync.parse_save", return_value=parsed):
            exit_code, payload = self._run_main(argv)

        self.assertEqual(exit_code, 0)
        box_mons = payload["save"]["boxes"][0]["pokemon"]
        self.assertEqual(len(box_mons), 2)

        magikarp = box_mons[0]
        self.assertEqual(
            set(magikarp.keys()),
            {
                "slot", "pid", "species_name", "level", "types", "ability",
                "nature", "nature_effect", "held_item", "moves", "is_egg",
            },
        )
        self.assertNotIn("nickname", magikarp)  # equals species_name.upper()
        self.assertNotIn("species_id", magikarp)
        self.assertNotIn("experience", magikarp)
        self.assertEqual(magikarp["moves"], ["Water Gun", "Tackle"])  # names only

        feebas = box_mons[1]
        self.assertEqual(feebas["nickname"], "Lucky")  # non-default -> kept

        # Party stays fully detailed (moves are still dicts, extra fields present).
        party_mon = payload["save"]["party"][0]
        self.assertIn("species_id", party_mon)
        self.assertIn("hp", party_mon)
        self.assertIsInstance(party_mon["moves"][0], dict)

    def test_full_flag_prints_uncompacted_boxes(self):
        local = self._write_local_save(content=b"save-v1")
        parsed = _sample_parsed_save(boxes=self._boxes_with_two_mons())
        argv = [self.user_id, "--local", str(local), "--users-dir", str(self.users_dir), "--full"]

        with mock.patch("parser.sync.parse_save", return_value=parsed):
            exit_code, payload = self._run_main(argv)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["save"]["boxes"], self._boxes_with_two_mons())

    def test_snapshot_on_disk_and_do_sync_return_value_are_always_full(self):
        local = self._write_local_save(content=b"save-v1")
        parsed = _sample_parsed_save(boxes=self._boxes_with_two_mons())

        with mock.patch("parser.sync.parse_save", return_value=parsed):
            result = sync.do_sync(self.user_id, self.users_dir, local_path=str(local))

        # do_sync itself never compacts.
        self.assertEqual(result["save"]["boxes"], self._boxes_with_two_mons())

        # Neither does the snapshot file on disk.
        snapshot_on_disk = json.loads(Path(result["snapshot"]).read_text())
        self.assertEqual(snapshot_on_disk["boxes"], self._boxes_with_two_mons())

    def test_compaction_measured_against_real_fixture_via_local(self):
        """Sanity-check the byte-size win against the real .srm fixture."""
        fixture = Path(__file__).parent / "fixtures" / "sapphire.srm"
        if not fixture.exists():
            self.skipTest("tests/fixtures/sapphire.srm not present")

        argv_full = [self.user_id, "--local", str(fixture), "--users-dir", str(self.users_dir), "--full"]
        _, full_payload = self._run_main(argv_full)
        full_bytes = len(json.dumps(full_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

        # Re-sync the same bytes into a second, independent user dir so the
        # compact run isn't short-circuited by the "unchanged" dedupe path.
        users_dir_2 = self.users_dir.parent / "users2"
        (users_dir_2 / self.user_id).mkdir(parents=True)
        (users_dir_2 / self.user_id / "config.json").write_text(json.dumps(self.config))
        argv_compact = [self.user_id, "--local", str(fixture), "--users-dir", str(users_dir_2)]
        _, compact_payload = self._run_main(argv_compact)
        compact_bytes = len(json.dumps(compact_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

        self.assertLess(compact_bytes, full_bytes)


class MainCliTests(TempUserMixin, unittest.TestCase):
    def test_main_local_sync_prints_one_json_object_and_exits_zero(self):
        local = self._write_local_save(content=b"save-v1")
        parsed = _sample_parsed_save()
        argv = [self.user_id, "--local", str(local), "--users-dir", str(self.users_dir)]

        import contextlib
        import io

        buf = io.StringIO()
        with mock.patch("parser.sync.parse_save", return_value=parsed):
            with contextlib.redirect_stdout(buf):
                exit_code = sync.main(argv)

        self.assertEqual(exit_code, 0)
        lines = [line for line in buf.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        payload = json.loads(lines[0])
        self.assertEqual(payload["status"], "synced")
        # Compact JSON: no indentation/space-after-separator noise.
        self.assertIn('{"status":"synced"', lines[0])
        self.assertNotIn("\n  ", lines[0])

    def test_main_invalid_save_exits_three_with_json_on_stdout(self):
        local = self._write_local_save(content=b"garbage")
        bad_parsed = _sample_parsed_save()
        bad_parsed["save_metadata"]["checksum_valid"] = False
        argv = [self.user_id, "--local", str(local), "--users-dir", str(self.users_dir)]

        import contextlib
        import io

        buf = io.StringIO()
        err_buf = io.StringIO()
        with mock.patch("parser.sync.parse_save", return_value=bad_parsed):
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err_buf):
                exit_code = sync.main(argv)

        self.assertEqual(exit_code, 3)
        payload = json.loads(buf.getvalue().strip())
        self.assertEqual(payload["status"], "invalid_save")
        # main() also prints a short human-readable error to stderr (the CLI's
        # own behavior) — captured here so the test suite's own console output
        # stays clean, not because the print itself is a bug.
        self.assertIn("checksum_valid is False", err_buf.getvalue())


if __name__ == "__main__":
    unittest.main()
