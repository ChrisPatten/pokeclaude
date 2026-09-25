"""sync.py — deterministic save-sync CLI.

    python3 -m parser.sync <user_id>                       # scp pull + sync
    python3 -m parser.sync <user_id> --local <path.srm>    # local file instead of scp (.srm or .sav)
    python3 -m parser.sync <user_id> --diff [--from N] [--to M]
    python3 -m parser.sync <user_id> --local <path.srm> --full   # uncompacted save

Replaces the old prose-driven sync (an LLM reading an MD5 out of a markdown
table and shelling out to scp) with a script that owns every deterministic
step: pulling, hashing, deduping, parsing, archiving, snapshotting, and
diffing. The LLM only ever sees this command's single JSON object on stdout.

Stdout is compact JSON, and (unless --full) box Mons in the "synced" payload's
"save.boxes" are trimmed to a small summary shape (no move ids/pp/types-per-
move/experience/species_id) since boxes otherwise dominate the payload's
byte count. snapshots/NNN.json on disk, and every diff, always use the FULL
parser output — "snapshot" in the synced payload points at that file.

See scratchpad/CONTRACT.md for the exact CLI/storage/JSON contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Optional

from . import __version__, diff as diff_module
from .parse_save import SUPPORTED_GENERATIONS, parse as parse_save

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_USERS_DIR = PROJECT_ROOT / "users"


class SyncError(Exception):
    """Carries the exact JSON payload and exit code to surface to the CLI."""

    def __init__(self, payload: dict, exit_code: int):
        super().__init__(payload.get("error") or payload.get("status"))
        self.payload = payload
        self.exit_code = exit_code


# ---------------------------------------------------------------------------
# Atomic file helpers
# ---------------------------------------------------------------------------


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_" + path.name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.remove(tmp_name)
        except OSError:
            pass
        raise


def _atomic_write_text(path: Path, text: str) -> None:
    _atomic_write_bytes(path, text.encode("utf-8"))


def _atomic_write_json(path: Path, obj: Any) -> None:
    _atomic_write_text(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def _md5_file(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _save_suffix(save_filename: Optional[str]) -> str:
    """Archive/rejected copies keep the save's own extension (.srm, .sav)."""
    return Path(save_filename or "").suffix or ".srm"


def _make_tmp_path(saves_dir: Path) -> Path:
    saves_dir.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="pull_", suffix=".srm.tmp", dir=str(saves_dir))
    os.close(fd)
    return Path(name)


def _load_snapshot(saves_dir: Path, sync_number: int) -> Optional[dict]:
    path = saves_dir / "snapshots" / f"{sync_number:03d}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _relative_to_project(path: Path) -> str:
    """Best-effort path relative to the project root, for stdout payloads.

    Falls back to the absolute path when the target isn't under the project
    root (e.g. tests pointing --users-dir at a tempdir).
    """
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# Stdout compaction — boxes are ~80% of a synced payload's bytes and are
# rarely what the LLM needs at a glance. snapshots/NNN.json and diffs always
# use the FULL parser output; only the printed stdout "save.boxes" is
# compacted, unless --full is passed.
# ---------------------------------------------------------------------------


def _compact_box_mon(mon: dict) -> dict:
    compact: dict[str, Any] = {
        "slot": mon.get("slot"),
        "pid": mon.get("pid"),
        "species_name": mon.get("species_name"),
    }
    nickname = mon.get("nickname")
    default_nickname = (mon.get("species_name") or "").upper()
    if nickname and nickname != default_nickname:
        compact["nickname"] = nickname
    compact.update(
        {
            "level": mon.get("level"),
            "types": mon.get("types"),
            "ability": mon.get("ability"),
            "nature": mon.get("nature"),
            "nature_effect": mon.get("nature_effect"),
            "held_item": mon.get("held_item"),
            "moves": [m.get("name") for m in (mon.get("moves") or [])],
            "is_egg": mon.get("is_egg"),
        }
    )
    # Gen 1 has no abilities or natures; drop the always-null keys.
    for key in ("ability", "nature", "nature_effect"):
        if compact[key] is None:
            del compact[key]
    return compact


def _compact_save_for_stdout(save: dict) -> dict:
    """Return a shallow copy of ``save`` with box Mons compacted.

    Party and daycare are left untouched — boxes are the bulk of the bytes
    and the least likely to matter for a given sync's summary.
    """
    compact = dict(save)
    compact["boxes"] = [
        {
            **{k: v for k, v in box.items() if k != "pokemon"},
            "pokemon": [_compact_box_mon(m) for m in (box.get("pokemon") or [])],
        }
        for box in (save.get("boxes") or [])
    ]
    return compact


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def _load_config(user_dir: Path) -> dict:
    config_path = user_dir / "config.json"
    if not config_path.exists():
        raise SyncError(
            {"status": "error", "error": f"Missing config file: {config_path}"}, 1
        )
    try:
        with open(config_path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise SyncError(
            {"status": "error", "error": f"Invalid JSON in {config_path}: {exc}"}, 1
        ) from exc


def _config_gen(config: dict) -> Optional[int]:
    """The save generation from config.json ("gen"), or None to auto-detect.

    Accepts an int or numeric string. An unsupported value is a config error.
    """
    gen = config.get("gen")
    if gen is None:
        return None
    try:
        gen = int(gen)
    except (TypeError, ValueError):
        raise SyncError({"status": "error", "error": f"config.json has an invalid gen: {gen!r}"}, 1)
    if gen not in SUPPORTED_GENERATIONS:
        supported = ", ".join(str(g) for g in SUPPORTED_GENERATIONS)
        raise SyncError(
            {"status": "error", "error": f"config.json gen {gen} is not supported (supported: {supported})"},
            1,
        )
    return gen


# ---------------------------------------------------------------------------
# scp pull
# ---------------------------------------------------------------------------


def _scp_pull(config: dict, user_dir: Path, dest_path: Path) -> None:
    device = config.get("device") or {}
    host = device.get("host")
    save_path = device.get("save_path")
    ssh_key = device.get("ssh_key")
    if not host or not save_path or not ssh_key:
        raise SyncError(
            {
                "status": "pull_failed",
                "error": "config.json is missing device.host, device.save_path, or device.ssh_key",
            },
            2,
        )

    key_path = user_dir / ssh_key
    # The remote path may contain spaces and parentheses. Modern OpenSSH scp
    # (9.0+, including the macOS default) speaks SFTP by default, which does
    # NOT forward the path through a remote shell — so it must be passed
    # unquoted as a single argv item ("host:/path with spaces (x).srm").
    # Single-quoting it (the legacy scp/rcp-protocol behavior) makes the
    # quotes part of the literal filename and scp fails with "No such file
    # or directory". No local shell is involved either way, since we invoke
    # scp via an argument list.
    remote = f"{host}:{save_path}"
    cmd = [
        "scp",
        "-q",  # suppress ssh banners/warnings (e.g. PQ key-exchange notices)
        "-i",
        str(key_path),
        "-o",
        "ConnectTimeout=10",
        "-o",
        "BatchMode=yes",
        remote,
        str(dest_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SyncError({"status": "pull_failed", "error": f"scp failed to run: {exc}"}, 2) from exc

    if proc.returncode != 0:
        detail = _last_stderr_lines(proc.stderr) or f"scp exited with code {proc.returncode}"
        raise SyncError({"status": "pull_failed", "error": detail}, 2)


def _last_stderr_lines(stderr: Optional[str], max_lines: int = 3) -> str:
    """Return the last few non-empty lines of stderr, joined by newlines.

    scp (and the ssh banners it can print before its own error) may emit
    multi-line noise; the actual failure reason is almost always the last
    line or two, so we surface just that instead of the whole blob.
    """
    lines = [line.strip() for line in (stderr or "").splitlines() if line.strip()]
    return "\n".join(lines[-max_lines:])


# ---------------------------------------------------------------------------
# history.json bootstrap (from MEMORY.md's "## Save History" table)
# ---------------------------------------------------------------------------


def _parse_save_history_table(text: str) -> list[dict]:
    """Robustly parse the "## Save History" markdown table from MEMORY.md.

    Columns: Sync # | Date | Location | Badges | MD5 Hash. The location
    column may say "[TBD]", which is normalized to None. Rows that don't
    parse as a real data row (header, separator, malformed) are skipped.
    """
    heading_re = re.compile(r"^##\s+Save History\s*$", re.MULTILINE)
    match = heading_re.search(text)
    if not match:
        return []

    rows: list[dict] = []
    in_table = False
    for line in text[match.end():].splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            in_table = True
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cells) < 5:
                continue
            sync_num_str, date_str, location_str, badges_str, md5_str = cells[:5]
            try:
                sync_number = int(sync_num_str)
            except ValueError:
                # Header row ("Sync #") or separator row ("---") — skip.
                continue
            location = None if location_str.strip().lower() == "[tbd]" else location_str.strip()
            try:
                badges = int(badges_str)
            except ValueError:
                badges = None
            rows.append(
                {
                    "sync_number": sync_number,
                    "date": date_str.strip(),
                    "location": location,
                    "badges": badges,
                    "md5": md5_str.strip().lower(),
                    "has_snapshot": False,
                }
            )
        elif in_table:
            break  # table ended

    rows.sort(key=lambda r: r["sync_number"])
    return rows


def _load_or_bootstrap_history(user_id: str, users_dir: Path, config: dict) -> dict:
    user_dir = users_dir / user_id
    saves_dir = user_dir / "saves"
    history_path = saves_dir / "history.json"

    if history_path.exists():
        with open(history_path, encoding="utf-8") as f:
            return json.load(f)

    history: dict = {"syncs": []}
    memory_path = user_dir / "memory" / "MEMORY.md"
    if memory_path.exists():
        history["syncs"] = _parse_save_history_table(memory_path.read_text(encoding="utf-8"))

    if history["syncs"]:
        last = history["syncs"][-1]
        latest_path = saves_dir / config.get("save_filename", "")
        if config.get("save_filename") and latest_path.exists():
            try:
                current_md5 = _md5_file(latest_path)
            except OSError:
                current_md5 = None
            if current_md5 and current_md5 == last["md5"]:
                try:
                    parsed = parse_save(str(latest_path), gen=_config_gen(config))
                except Exception as exc:  # noqa: BLE001 - best-effort bootstrap
                    print(
                        f"warning: could not parse existing save during bootstrap: {exc}",
                        file=sys.stderr,
                    )
                else:
                    sync_number = last["sync_number"]
                    _atomic_write_json(
                        saves_dir / "snapshots" / f"{sync_number:03d}.json", parsed
                    )
                    archive_dir = saves_dir / "archive"
                    archive_dir.mkdir(parents=True, exist_ok=True)
                    archive_name = (
                        f"{sync_number:03d}_{last['date']}_{current_md5[:8]}"
                        f"{_save_suffix(config.get('save_filename'))}"
                    )
                    archive_path = archive_dir / archive_name
                    if not archive_path.exists():
                        shutil.copyfile(latest_path, archive_path)
                    last["has_snapshot"] = True

    _atomic_write_json(history_path, history)
    return history


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


def do_sync(user_id: str, users_dir: Path, local_path: Optional[str] = None) -> dict:
    user_dir = users_dir / user_id
    config = _load_config(user_dir)
    gen = _config_gen(config)

    saves_dir = user_dir / "saves"
    (saves_dir / "archive").mkdir(parents=True, exist_ok=True)
    (saves_dir / "snapshots").mkdir(parents=True, exist_ok=True)

    history = _load_or_bootstrap_history(user_id, users_dir, config)
    last_entry = history["syncs"][-1] if history["syncs"] else None

    save_filename = config.get("save_filename")
    if not save_filename:
        raise SyncError({"status": "error", "error": "config.json is missing save_filename"}, 1)
    latest_path = saves_dir / save_filename

    tmp_path: Optional[Path] = _make_tmp_path(saves_dir)
    try:
        if local_path:
            src = Path(local_path)
            if not src.exists():
                raise SyncError(
                    {"status": "pull_failed", "error": f"Local save file not found: {local_path}"},
                    2,
                )
            shutil.copyfile(src, tmp_path)
        else:
            _scp_pull(config, user_dir, tmp_path)

        md5 = _md5_file(tmp_path)

        if last_entry and last_entry.get("md5") == md5:
            return {
                "status": "unchanged",
                "sync_number": last_entry["sync_number"],
                "md5": md5,
                "date": last_entry["date"],
            }

        parse_error: Optional[str] = None
        parsed: Optional[dict] = None
        valid = False
        try:
            parsed = parse_save(str(tmp_path), gen=gen)
            valid = bool((parsed.get("save_metadata") or {}).get("checksum_valid", False))
        except Exception as exc:  # noqa: BLE001 - any parse failure -> invalid_save
            parse_error = str(exc)

        if parsed is None or not valid:
            rejected_path = saves_dir / f"rejected_{md5[:8]}{_save_suffix(save_filename)}"
            os.replace(tmp_path, rejected_path)
            tmp_path = None
            error_msg = parse_error or "save_metadata.checksum_valid is False"
            raise SyncError({"status": "invalid_save", "error": error_msg}, 3)

        sync_number = (last_entry["sync_number"] + 1) if last_entry else 1
        date_str = date.today().isoformat()

        previous_snapshot = None
        if last_entry and last_entry.get("has_snapshot"):
            previous_snapshot = _load_snapshot(saves_dir, last_entry["sync_number"])

        os.replace(tmp_path, latest_path)
        tmp_path = None

        archive_name = f"{sync_number:03d}_{date_str}_{md5[:8]}{_save_suffix(save_filename)}"
        shutil.copyfile(latest_path, saves_dir / "archive" / archive_name)

        snapshot_path = saves_dir / "snapshots" / f"{sync_number:03d}.json"
        _atomic_write_json(snapshot_path, parsed)

        computed_diff = diff_module.diff_saves(previous_snapshot, parsed) if previous_snapshot else None

        history["syncs"].append(
            {
                "sync_number": sync_number,
                "date": date_str,
                "location": (parsed.get("location") or {}).get("name"),
                "badges": (parsed.get("badges") or {}).get("count"),
                "md5": md5,
                "has_snapshot": True,
            }
        )
        _atomic_write_json(saves_dir / "history.json", history)

        return {
            "status": "synced",
            "sync_number": sync_number,
            "md5": md5,
            "date": date_str,
            "previous_md5": last_entry["md5"] if last_entry else None,
            "snapshot": _relative_to_project(snapshot_path),
            "save": parsed,
            "diff": computed_diff,
        }
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Diff mode
# ---------------------------------------------------------------------------


def do_diff(
    user_id: str, users_dir: Path, from_sync: Optional[int], to_sync: Optional[int]
) -> dict:
    user_dir = users_dir / user_id
    saves_dir = user_dir / "saves"
    history_path = saves_dir / "history.json"
    if not history_path.exists():
        raise SyncError(
            {"status": "error", "error": "No history.json found; run a sync first."}, 1
        )
    with open(history_path, encoding="utf-8") as f:
        history = json.load(f)

    snap_entries = [s for s in history.get("syncs", []) if s.get("has_snapshot")]

    if from_sync is None or to_sync is None:
        if len(snap_entries) < 2:
            raise SyncError(
                {
                    "status": "error",
                    "error": "Fewer than two synced snapshots are available; cannot diff.",
                },
                1,
            )
        default_from = snap_entries[-2]["sync_number"]
        default_to = snap_entries[-1]["sync_number"]
        if from_sync is None:
            from_sync = default_from
        if to_sync is None:
            to_sync = default_to

    old = _load_snapshot(saves_dir, from_sync)
    new = _load_snapshot(saves_dir, to_sync)
    if old is None:
        raise SyncError(
            {"status": "error", "error": f"No snapshot found for sync {from_sync}."}, 1
        )
    if new is None:
        raise SyncError(
            {"status": "error", "error": f"No snapshot found for sync {to_sync}."}, 1
        )

    computed = diff_module.diff_saves(old, new)
    return {"status": "diff", "from": from_sync, "to": to_sync, "diff": computed}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python3 -m parser.sync")
    p.add_argument(
        "--version", action="version", version=f"parser.sync {__version__}"
    )
    p.add_argument("user_id", help="Telegram user id (matches users/<user_id>/)")
    p.add_argument("--local", metavar="PATH", help="use a local save file (.srm/.sav) instead of scp")
    p.add_argument(
        "--diff", action="store_true", help="diff two stored snapshots instead of syncing"
    )
    p.add_argument(
        "--full",
        action="store_true",
        help="print the full, uncompacted save (box Mons included) instead of the "
        "compact stdout form; snapshots/NNN.json is always full regardless of this flag",
    )
    p.add_argument("--from", dest="from_sync", type=int, default=None, metavar="N")
    p.add_argument("--to", dest="to_sync", type=int, default=None, metavar="M")
    p.add_argument(
        "--users-dir",
        default=None,
        help="override the users/ directory root (default: <project root>/users)",
    )
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    users_dir = Path(args.users_dir) if args.users_dir else DEFAULT_USERS_DIR

    try:
        if args.diff:
            payload = do_diff(args.user_id, users_dir, args.from_sync, args.to_sync)
        else:
            payload = do_sync(args.user_id, users_dir, local_path=args.local)
    except SyncError as exc:
        print(exc.payload.get("error") or exc.payload.get("status", "error"), file=sys.stderr)
        print(json.dumps(exc.payload, ensure_ascii=False, separators=(",", ":")))
        return exc.exit_code

    if not args.full and payload.get("status") == "synced" and "save" in payload:
        payload = dict(payload)
        payload["save"] = _compact_save_for_stdout(payload["save"])

    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
