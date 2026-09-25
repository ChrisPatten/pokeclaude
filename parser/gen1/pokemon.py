"""Parse party, PC box, and daycare Pokémon from a Generation I save.

Gen 1 has no personality value, natures, abilities, held items, or eggs.
The Mon dicts keep the same keys as Gen 3 so diff/sync code stays shared:
``ability``/``nature``/``nature_effect`` are None, ``held_item`` is "None",
``is_egg`` is False. ``pid`` is synthesized from the two values a Gen 1
Pokémon keeps for life — its original trainer ID and its DVs — as
"0xOOOODDDD". Two Pokémon with the same OT and identical DVs would collide;
``assign_unique_pids`` disambiguates any in-save duplicates with a suffix.
"""

from __future__ import annotations

import logging
from typing import Any

from .. import data_loader
from . import layout

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Growth rates (pokered data/growth_rates.asm: a/b*n^3 + c*n^2 + d*n - e)
# ---------------------------------------------------------------------------

_GROWTH = {
    "medium_fast": (1, 1, 0, 0, 0),
    "slightly_fast": (3, 4, 10, 0, 30),
    "slightly_slow": (3, 4, 20, 0, 70),
    "medium_slow": (6, 5, -15, 100, 140),
    "fast": (4, 5, 0, 0, 0),
    "slow": (5, 4, 0, 0, 0),
}


def exp_for_level(n: int, growth_rate: str) -> int:
    """Minimum EXP for level *n*, computed the way the game does (integer math)."""
    if n <= 1:
        return 0
    a, b, c, d, e = _GROWTH.get(growth_rate, _GROWTH["medium_fast"])
    return max(0, a * n ** 3 // b + c * n ** 2 + d * n - e)


def level_from_exp(experience: int, growth_rate: str) -> int:
    for lv in range(100, 1, -1):
        if exp_for_level(lv, growth_rate) <= experience:
            return lv
    return 1


# ---------------------------------------------------------------------------
# Field decoding
# ---------------------------------------------------------------------------

def decode_status(status: int) -> str:
    if status == 0:
        return "none"
    if status & 0x07:
        return "sleep"
    if status & (1 << 3):
        return "poison"
    if status & (1 << 4):
        return "burn"
    if status & (1 << 5):
        return "freeze"
    if status & (1 << 6):
        return "paralysis"
    return "none"


def _format_moves(move_ids: list[int], pp_bytes: list[int]) -> list[dict]:
    moves = data_loader.load_gen1_moves()
    out = []
    for i, mid in enumerate(move_ids):
        if mid == 0:
            continue
        info = moves.get(str(mid), {"name": f"Unknown Move ({mid})", "type": "???", "pp": 0})
        base = info["pp"]
        ups = pp_bytes[i] >> 6
        # engine/items/item_effects.asm AddBonusPP: +min(base // 5, 7) per PP Up
        pp_max = base + ups * min(base // 5, 7)
        out.append({
            "slot": i + 1,
            "move_id": mid,
            "name": info["name"],
            "type": info["type"],
            "pp": pp_bytes[i] & 0x3F,
            "pp_max": pp_max,
        })
    return out


def _species_info(species_id: int) -> tuple[str, list[str], str]:
    info = data_loader.load_gen1_species().get(str(species_id))
    if info is None:
        logger.warning("Unknown Gen 1 species index %d (glitch Pokémon?) — types unresolved", species_id)
        return f"MissingNo. ({species_id})", ["Unknown"], "medium_fast"
    return info["name"], info["types"], info["growth_rate"]


def parse_box_struct(
    data: bytes, nickname: str, *, level: int | None = None
) -> dict[str, Any] | None:
    """Parse a 33-byte box_struct. Returns None for an empty slot.

    *level* overrides the stored BoxLevel (party mons carry their real level
    separately; daycare mons gain EXP per step, so their level is derived).
    """
    if len(data) < layout.BOX_STRUCT_SIZE or data[0] == 0:
        return None
    species_id = data[0]
    name, types, growth = _species_info(species_id)
    ot_id = layout.u16(data, 12)
    experience = layout.u24(data, 14)
    dvs = layout.u16(data, 27)
    return {
        "pid": f"0x{ot_id:04X}{dvs:04X}",
        "species_id": species_id,
        "species_name": name,
        "nickname": nickname,
        "types": types,
        "ability": None,
        "level": level if level is not None else data[3],
        "experience": experience,
        "nature": None,
        "nature_effect": None,
        "held_item": "None",
        "moves": _format_moves(list(data[8:12]), list(data[29:33])),
        "is_egg": False,
        "_growth": growth,
    }


def _finish(mon: dict[str, Any], slot: int) -> dict[str, Any]:
    mon.pop("_growth", None)
    mon["slot"] = slot
    return mon


# ---------------------------------------------------------------------------
# Party
# ---------------------------------------------------------------------------

def parse_party(sav: bytes) -> list[dict[str, Any]]:
    base = layout.PARTY
    count = sav[base]
    if count > layout.PARTY_LENGTH:
        logger.warning("Party count %d exceeds %d; clamping", count, layout.PARTY_LENGTH)
        count = layout.PARTY_LENGTH

    party = []
    for i in range(count):
        off = base + layout.PARTY_MONS + i * layout.PARTY_STRUCT_SIZE
        raw = sav[off: off + layout.PARTY_STRUCT_SIZE]
        nick_off = base + layout.PARTY_NICKS + i * layout.NAME_LENGTH
        nickname = layout.decode_string(sav[nick_off: nick_off + layout.NAME_LENGTH])
        mon = parse_box_struct(raw, nickname, level=raw[33])
        if mon is None:
            continue
        mon["status"] = decode_status(raw[4])
        mon["hp"] = {"current": layout.u16(raw, 1), "max": layout.u16(raw, 34)}
        mon["stats"] = {
            "attack": layout.u16(raw, 36),
            "defense": layout.u16(raw, 38),
            "speed": layout.u16(raw, 40),
            "special": layout.u16(raw, 42),
        }
        party.append(_finish(mon, i + 1))
    return party


# ---------------------------------------------------------------------------
# PC boxes
# ---------------------------------------------------------------------------

def parse_box_block(block: bytes, box_label: str) -> list[dict[str, Any]]:
    """Parse one 0x462-byte box (sCurBoxData or sBoxN)."""
    count = block[0]
    if count == 0:
        return []
    if count > layout.MONS_PER_BOX:
        logger.warning("%s has an invalid count (%d); treating it as empty", box_label, count)
        return []
    mons = []
    for i in range(count):
        off = layout.BOX_MONS + i * layout.BOX_STRUCT_SIZE
        nick_off = layout.BOX_NICKS + i * layout.NAME_LENGTH
        nickname = layout.decode_string(block[nick_off: nick_off + layout.NAME_LENGTH])
        mon = parse_box_struct(block[off: off + layout.BOX_STRUCT_SIZE], nickname)
        if mon is not None:
            mons.append(_finish(mon, i + 1))
    return mons


def parse_boxes(sav: bytes) -> list[dict[str, Any]]:
    """Return all 12 boxes.

    The selected box lives in the main bank (sCurBoxData); its slot in bank 2/3
    is blanked when the player switches to it. Banks 2 and 3 are only
    initialised the first time the player changes boxes (bit 7 of
    wCurrentBoxNum) — before that, every box but the current one is empty.
    """
    current = sav[layout.CURRENT_BOX] & 0x7F
    banks_initialised = bool(sav[layout.CURRENT_BOX] & 0x80)
    if current >= layout.NUM_BOXES:
        logger.warning("Current box index %d out of range; assuming box 1", current + 1)
        current = 0

    if banks_initialised:
        for bank, bank_start in enumerate(layout.BOX_BANKS, start=2):
            stored = sav[bank_start + layout.BANK_CHECKSUM_OFFSET]
            computed = layout.checksum(sav, bank_start, bank_start + layout.BANK_CHECKSUM_OFFSET)
            if stored != computed:
                logger.warning(
                    "PC box bank %d checksum mismatch (stored 0x%02X, computed 0x%02X); "
                    "boxes %d-%d may be unreliable",
                    bank, stored, computed,
                    (bank - 2) * layout.BOXES_PER_BANK + 1, (bank - 1) * layout.BOXES_PER_BANK,
                )

    boxes = []
    for idx in range(layout.NUM_BOXES):
        label = f"BOX {idx + 1}"
        if idx == current:
            block = sav[layout.CUR_BOX_DATA: layout.CUR_BOX_DATA + layout.BOX_DATA_SIZE]
            mons = parse_box_block(block, label)
        elif banks_initialised:
            bank_start = layout.BOX_BANKS[idx // layout.BOXES_PER_BANK]
            start = bank_start + (idx % layout.BOXES_PER_BANK) * layout.BOX_DATA_SIZE
            mons = parse_box_block(sav[start: start + layout.BOX_DATA_SIZE], label)
        else:
            mons = []
        boxes.append({"box_index": idx, "name": label, "is_current": idx == current, "pokemon": mons})
    return boxes


# ---------------------------------------------------------------------------
# Daycare
# ---------------------------------------------------------------------------

def parse_daycare(sav: bytes) -> list[dict[str, Any]]:
    """Gen 1 daycare holds one Pokémon. It gains 1 EXP per step, so its level
    is derived from EXP (what it will be on withdrawal), not the stored byte."""
    if not sav[layout.DAYCARE_IN_USE]:
        return []
    raw = sav[layout.DAYCARE_MON: layout.DAYCARE_MON + layout.BOX_STRUCT_SIZE]
    nickname = layout.decode_string(sav[layout.DAYCARE_NICK: layout.DAYCARE_NICK + layout.NAME_LENGTH])
    mon = parse_box_struct(raw, nickname)
    if mon is None:
        return []
    mon["level"] = min(100, max(mon["level"], level_from_exp(mon["experience"], mon["_growth"])))
    return [_finish(mon, 1)]


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def assign_unique_pids(party: list[dict], boxes: list[dict], daycare: list[dict]) -> None:
    """Make synthesized pids unique within one save (party, boxes, daycare order)."""
    seen: dict[str, int] = {}
    mons = list(party) + [m for box in boxes for m in box["pokemon"]] + list(daycare)
    for mon in mons:
        pid = mon["pid"]
        if pid in seen:
            seen[pid] += 1
            mon["pid"] = f"{pid}-{seen[pid]}"
            logger.warning(
                "Two Pokémon share OT ID and DVs (%s); tracking %s as %s",
                pid, mon["species_name"], mon["pid"],
            )
        else:
            seen[pid] = 1
