"""diff.py — compute a deterministic diff between two parsed save snapshots.

Pure function, no I/O. See ``scratchpad/CONTRACT.md`` (shared refactor contract)
for the exact input (parser output) and output (Diff) schemas.

Public API:
    diff_saves(old: dict, new: dict) -> dict
"""

from __future__ import annotations

from typing import Any

_POCKETS = ["pc", "items", "key_items", "balls", "tms_hms", "berries"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flatten(save: dict) -> dict[str, tuple[dict, str]]:
    """Map pid -> (mon, where) across party/boxes/daycare for one save."""
    index: dict[str, tuple[dict, str]] = {}
    for mon in save.get("party") or []:
        index[mon["pid"]] = (mon, "party")
    for box in save.get("boxes") or []:
        where = f"box {box.get('box_index')}"
        for mon in box.get("pokemon") or []:
            index[mon["pid"]] = (mon, where)
    for mon in save.get("daycare") or []:
        index[mon["pid"]] = (mon, "daycare")
    return index


def _mon_ref(mon: dict, where: str) -> dict:
    return {
        "pid": mon["pid"],
        "species_name": mon["species_name"],
        "level": mon["level"],
        "where": where,
    }


def _move_names(mon: dict) -> set[str]:
    return {m["name"] for m in (mon.get("moves") or [])}


def _sorted_by_pid(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda d: d["pid"])


def _inventory_pocket_delta(old_list, new_list, is_key_items: bool = False) -> dict:
    if is_key_items:
        old_map: dict[str, int] = {name: 1 for name in (old_list or [])}
        new_map: dict[str, int] = {name: 1 for name in (new_list or [])}
    else:
        old_map = {item["name"]: item["quantity"] for item in (old_list or [])}
        new_map = {item["name"]: item["quantity"] for item in (new_list or [])}

    added: dict[str, int] = {}
    removed: dict[str, int] = {}
    changed: dict[str, dict[str, int]] = {}
    for name in sorted(set(old_map) | set(new_map)):
        old_qty = old_map.get(name)
        new_qty = new_map.get(name)
        if old_qty is None and new_qty is not None:
            added[name] = new_qty
        elif old_qty is not None and new_qty is None:
            removed[name] = old_qty
        elif old_qty != new_qty:
            changed[name] = {"from": old_qty, "to": new_qty}
    return {"added": added, "removed": removed, "changed": changed}


def _total_seconds(save: dict) -> int:
    pt = (save.get("trainer") or {}).get("playtime") or {}
    return pt.get("hours", 0) * 3600 + pt.get("minutes", 0) * 60 + pt.get("seconds", 0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def diff_saves(old: dict, new: dict) -> dict:
    """Compute a deterministic diff between two parsed save snapshots.

    Mons are matched across party/boxes/daycare by ``pid`` (personality value),
    which is stable across syncs even through evolution, box moves, and level
    ups. See CONTRACT.md's Diff schema for the exact return shape.
    """
    result: dict[str, Any] = {}

    # --- location -----------------------------------------------------
    old_loc = (old.get("location") or {}).get("name")
    new_loc = (new.get("location") or {}).get("name")
    result["location"] = None if old_loc == new_loc else {"from": old_loc, "to": new_loc}

    # --- badges ---------------------------------------------------------
    old_badges = set((old.get("badges") or {}).get("obtained") or [])
    new_badges = set((new.get("badges") or {}).get("obtained") or [])
    result["badges_gained"] = sorted(new_badges - old_badges)

    # --- money / playtime / pokedex -------------------------------------
    old_money = (old.get("trainer") or {}).get("money", 0)
    new_money = (new.get("trainer") or {}).get("money", 0)
    result["money"] = {"from": old_money, "to": new_money, "delta": new_money - old_money}

    result["playtime_minutes_delta"] = (_total_seconds(new) - _total_seconds(old)) // 60

    old_dex = old.get("pokedex") or {}
    new_dex = new.get("pokedex") or {}
    result["pokedex"] = {
        "seen_delta": new_dex.get("seen", 0) - old_dex.get("seen", 0),
        "caught_delta": new_dex.get("caught", 0) - old_dex.get("caught", 0),
    }

    # --- flattened indices across party/boxes/daycare --------------------
    old_index = _flatten(old)
    new_index = _flatten(new)

    old_party_pids = {m["pid"] for m in (old.get("party") or [])}
    new_party_pids = {m["pid"] for m in (new.get("party") or [])}

    # --- party membership: added / removed / changed ---------------------
    added_pids = sorted(new_party_pids - old_party_pids)
    removed_pids = sorted(old_party_pids - new_party_pids)
    stayed_pids = sorted(old_party_pids & new_party_pids)

    party_added = [_mon_ref(*(new_index[pid][0], "party")) for pid in added_pids]

    party_removed = []
    for pid in removed_pids:
        if pid in new_index:
            mon, where = new_index[pid]
            party_removed.append(_mon_ref(mon, where))
        else:
            old_mon, _ = old_index[pid]
            party_removed.append(_mon_ref(old_mon, "party"))

    # "changed" = mons that stayed in the party but whose attributes moved.
    # (Membership churn is fully captured by added/removed; this surfaces
    # per-mon changes — evolution, level, moves, held item, nickname — for
    # mons the trainer kept in the active party. See report for rationale.)
    party_changed = []
    for pid in stayed_pids:
        old_mon, _ = old_index[pid]
        new_mon, _ = new_index[pid]
        tags = []
        if old_mon["species_name"] != new_mon["species_name"]:
            tags.append("evolved")
        if old_mon["level"] < new_mon["level"]:
            tags.append("leveled_up")
        elif old_mon["level"] > new_mon["level"]:
            tags.append("leveled_down")
        if _move_names(old_mon) != _move_names(new_mon):
            tags.append("moves_changed")
        if old_mon.get("held_item") != new_mon.get("held_item"):
            tags.append("held_item_changed")
        if old_mon.get("nickname") != new_mon.get("nickname"):
            tags.append("nickname_changed")
        if tags:
            party_changed.append(
                {"pid": pid, "species_name": new_mon["species_name"], "changes": sorted(tags)}
            )

    result["party"] = {
        "added": _sorted_by_pid(party_added),
        "removed": _sorted_by_pid(party_removed),
        "changed": sorted(party_changed, key=lambda d: d["pid"]),
    }

    # --- caught / released_or_traded: presence anywhere -------------------
    caught_pids = sorted(set(new_index) - set(old_index))
    released_pids = sorted(set(old_index) - set(new_index))
    result["caught"] = [_mon_ref(*new_index[pid]) for pid in caught_pids]
    result["released_or_traded"] = [_mon_ref(*old_index[pid]) for pid in released_pids]

    # --- evolved / leveled / moves_changed / held_items_changed -----------
    common_pids = sorted(set(old_index) & set(new_index))
    evolved = []
    leveled = []
    moves_changed = []
    held_items_changed = []
    for pid in common_pids:
        old_mon, _ = old_index[pid]
        new_mon, _ = new_index[pid]

        if old_mon["species_name"] != new_mon["species_name"]:
            evolved.append(
                {"pid": pid, "from": old_mon["species_name"], "to": new_mon["species_name"]}
            )

        if old_mon["level"] != new_mon["level"]:
            leveled.append(
                {
                    "pid": pid,
                    "species_name": new_mon["species_name"],
                    "from": old_mon["level"],
                    "to": new_mon["level"],
                }
            )

        old_moves = _move_names(old_mon)
        new_moves = _move_names(new_mon)
        learned = sorted(new_moves - old_moves)
        forgot = sorted(old_moves - new_moves)
        if learned or forgot:
            moves_changed.append(
                {
                    "pid": pid,
                    "species_name": new_mon["species_name"],
                    "learned": learned,
                    "forgot": forgot,
                }
            )

        if old_mon.get("held_item") != new_mon.get("held_item"):
            held_items_changed.append(
                {
                    "pid": pid,
                    "species_name": new_mon["species_name"],
                    "from": old_mon.get("held_item"),
                    "to": new_mon.get("held_item"),
                }
            )

    result["evolved"] = evolved
    result["leveled"] = leveled
    result["moves_changed"] = moves_changed
    result["held_items_changed"] = held_items_changed

    # --- daycare: full from/to snapshot, null if unchanged -----------------
    old_daycare = old.get("daycare") or []
    new_daycare = new.get("daycare") or []
    if sorted(m["pid"] for m in old_daycare) == sorted(m["pid"] for m in new_daycare):
        result["daycare"] = None
    else:
        result["daycare"] = {
            "from": _sorted_by_pid([_mon_ref(m, "daycare") for m in old_daycare]),
            "to": _sorted_by_pid([_mon_ref(m, "daycare") for m in new_daycare]),
        }

    # --- inventory: per-pocket deltas --------------------------------------
    old_inv = old.get("inventory") or {}
    new_inv = new.get("inventory") or {}
    inventory = {}
    for pocket in _POCKETS:
        inventory[pocket] = _inventory_pocket_delta(
            old_inv.get(pocket), new_inv.get(pocket), is_key_items=(pocket == "key_items")
        )
    result["inventory"] = inventory

    return result
