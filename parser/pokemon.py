"""Parse party and PC box Pokémon from Generation III (Ruby/Sapphire)
save sectors."""

import json
import struct
from pathlib import Path
from typing import Any

from . import decode

_DATA_DIR = Path(__file__).parent / "data"

# Caches
_species_cache: dict[str, str] | None = None
_moves_cache: dict[str, dict] | None = None
_natures_cache: list[dict] | None = None
_items_cache: dict[str, str] | None = None


def _load_species() -> dict[str, str]:
    global _species_cache
    if _species_cache is None:
        with open(_DATA_DIR / "species.json") as f:
            _species_cache = json.load(f)
    return _species_cache


def _load_moves() -> dict[str, dict]:
    global _moves_cache
    if _moves_cache is None:
        with open(_DATA_DIR / "moves.json") as f:
            _moves_cache = json.load(f)
    return _moves_cache


def _load_natures() -> list[dict]:
    global _natures_cache
    if _natures_cache is None:
        with open(_DATA_DIR / "natures.json") as f:
            _natures_cache = json.load(f)
    return _natures_cache


def _load_items() -> dict[str, str]:
    global _items_cache
    if _items_cache is None:
        with open(_DATA_DIR / "items.json") as f:
            _items_cache = json.load(f)
    return _items_cache


# ---------------------------------------------------------------------------
# Substructure order table (PV % 24)
# ---------------------------------------------------------------------------

SUBSTRUCTURE_ORDER = [
    "GAEM", "GAME", "GEAM", "GEMA", "GMAE", "GMEA",
    "AGEM", "AGME", "AEGM", "AEMG", "AMGE", "AMEG",
    "EGAM", "EGMA", "EAGM", "EAMG", "EMGA", "EMAG",
    "MGAE", "MGEA", "MAGE", "MAEG", "MEGA", "MEAG",
]


# ---------------------------------------------------------------------------
# Status condition decoding
# ---------------------------------------------------------------------------

def _decode_status(status_word: int) -> str:
    if status_word == 0:
        return "none"
    if status_word & 0x07:
        return "sleep"
    if status_word & (1 << 7):
        return "bad poison"
    if status_word & (1 << 3):
        return "poison"
    if status_word & (1 << 4):
        return "burn"
    if status_word & (1 << 5):
        return "freeze"
    if status_word & (1 << 6):
        return "paralysis"
    return "none"


# ---------------------------------------------------------------------------
# Substructure parsing
# ---------------------------------------------------------------------------

def _parse_substructures(pv: int, ot_id: int, encrypted: bytes) -> dict:
    """Decrypt and parse the 48-byte substructure block."""
    key = pv ^ ot_id
    decrypted = decode.xor_decrypt(encrypted, key)

    order = SUBSTRUCTURE_ORDER[pv % 24]
    chunks: dict[str, bytes] = {}
    for i, letter in enumerate(order):
        chunks[letter] = decrypted[i * 12 : (i + 1) * 12]

    # Growth (G)
    g = chunks["G"]
    species_id = struct.unpack_from("<H", g, 0)[0]
    item_id = struct.unpack_from("<H", g, 2)[0]
    experience = struct.unpack_from("<I", g, 4)[0]
    pp_bonuses = g[8]

    # Attacks (A)
    a = chunks["A"]
    move_ids = [struct.unpack_from("<H", a, j * 2)[0] for j in range(4)]
    pps = [a[8 + j] for j in range(4)]

    # Misc (M)
    m = chunks["M"]
    iv_egg_ability = struct.unpack_from("<I", m, 4)[0]
    is_egg = bool(iv_egg_ability & (1 << 30))
    ability_bit = (iv_egg_ability >> 31) & 1

    return {
        "species_id": species_id,
        "item_id": item_id,
        "experience": experience,
        "pp_bonuses": pp_bonuses,
        "move_ids": move_ids,
        "pps": pps,
        "is_egg": is_egg,
        "ability_bit": ability_bit,
    }


# ---------------------------------------------------------------------------
# Move formatting
# ---------------------------------------------------------------------------

def _format_moves(move_ids: list[int], pps: list[int],
                  pp_bonuses: int) -> list[dict]:
    moves_data = _load_moves()
    result = []
    for i, mid in enumerate(move_ids):
        if mid == 0:
            continue
        move_info = moves_data.get(str(mid), {
            "name": f"Unknown Move ({mid})", "type": "???", "pp": 0
        })
        base_pp = move_info["pp"]
        ups = (pp_bonuses >> (i * 2)) & 3
        pp_max = base_pp + (base_pp * ups // 5)
        result.append({
            "slot": i + 1,
            "move_id": mid,
            "name": move_info["name"],
            "type": move_info["type"],
            "pp": pps[i],
            "pp_max": pp_max,
        })
    return result


# ---------------------------------------------------------------------------
# Party parsing
# ---------------------------------------------------------------------------

def parse_party(sectors: list[bytes]) -> list[dict[str, Any]]:
    """Parse party Pokémon from Section 1."""
    section1 = decode.get_sector_data(sectors, 1)

    team_size = struct.unpack_from("<I", section1, 0x0234)[0]
    if team_size > 6:
        team_size = 6

    species_data = _load_species()
    natures = _load_natures()
    items = _load_items()
    party: list[dict[str, Any]] = []

    for slot in range(team_size):
        offset = 0x0238 + slot * 100
        mon_data = section1[offset : offset + 100]
        if len(mon_data) < 100:
            continue

        pv = struct.unpack_from("<I", mon_data, 0x00)[0]
        ot_id = struct.unpack_from("<I", mon_data, 0x04)[0]
        nickname = decode.decode_string(mon_data[0x08:0x12])

        encrypted = mon_data[0x20:0x50]
        try:
            subs = _parse_substructures(pv, ot_id, encrypted)
        except Exception:
            continue

        if subs["species_id"] == 0:
            continue

        # Party-only battle stats
        status = struct.unpack_from("<I", mon_data, 0x50)[0]
        level = mon_data[0x54]
        current_hp = struct.unpack_from("<H", mon_data, 0x56)[0]
        max_hp = struct.unpack_from("<H", mon_data, 0x58)[0]
        attack = struct.unpack_from("<H", mon_data, 0x5A)[0]
        defense = struct.unpack_from("<H", mon_data, 0x5C)[0]
        speed = struct.unpack_from("<H", mon_data, 0x5E)[0]
        sp_atk = struct.unpack_from("<H", mon_data, 0x60)[0]
        sp_def = struct.unpack_from("<H", mon_data, 0x62)[0]

        nature_idx = pv % 25
        nature_name = (natures[nature_idx]["name"]
                      if nature_idx < len(natures) else "Unknown")

        species_name = species_data.get(
            str(subs["species_id"]),
            f"Unknown ({subs['species_id']})"
        )
        held_item = items.get(str(subs["item_id"]), "None")
        if subs["item_id"] == 0:
            held_item = "None"

        misc_flags = mon_data[0x13]
        is_egg = subs["is_egg"] or bool(misc_flags & (1 << 2))

        party.append({
            "slot": slot + 1,
            "species_id": subs["species_id"],
            "species_name": species_name,
            "nickname": nickname,
            "level": level,
            "nature": nature_name,
            "ability": "Unknown",
            "held_item": held_item,
            "status": _decode_status(status),
            "hp": {"current": current_hp, "max": max_hp},
            "stats": {
                "attack": attack,
                "defense": defense,
                "speed": speed,
                "sp_atk": sp_atk,
                "sp_def": sp_def,
            },
            "moves": _format_moves(
                subs["move_ids"], subs["pps"], subs["pp_bonuses"]
            ),
            "is_egg": is_egg,
        })

    return party


# ---------------------------------------------------------------------------
# Box parsing
# ---------------------------------------------------------------------------

def _estimate_level(experience: int) -> int:
    """Approximate level from EXP using Medium Fast (n^3) curve."""
    if experience <= 0:
        return 1
    level = int(round(experience ** (1 / 3)))
    return max(1, min(100, level))


def _concat_box_data(sectors: list[bytes]) -> bytes:
    """Concatenate sections 5-13 into PC storage blob."""
    parts = []
    for section_id in range(5, 14):
        try:
            parts.append(decode.get_sector_data(sectors, section_id))
        except ValueError:
            break
    return b"".join(parts)


def parse_boxes(sectors: list[bytes]) -> list[dict[str, Any]]:
    """Parse PC box Pokémon from Sections 5-13."""
    pc_data = _concat_box_data(sectors)
    if not pc_data:
        return []

    species_data = _load_species()
    natures = _load_natures()
    items = _load_items()
    moves_data = _load_moves()

    BOX_NAME_OFFSET = 0x8344
    BOX_COUNT = 14
    MONS_PER_BOX = 30
    MON_SIZE = 80
    MON_DATA_OFFSET = 4

    boxes: list[dict[str, Any]] = []

    for box_idx in range(BOX_COUNT):
        # Read box name
        name_offset = BOX_NAME_OFFSET + box_idx * 9
        if name_offset + 9 <= len(pc_data):
            box_name = decode.decode_string(
                pc_data[name_offset:name_offset + 9]
            )
        else:
            box_name = f"BOX {box_idx + 1}"
        if not box_name:
            box_name = f"BOX {box_idx + 1}"

        pokemon_list: list[dict[str, Any]] = []

        for mon_slot in range(MONS_PER_BOX):
            global_idx = box_idx * MONS_PER_BOX + mon_slot
            offset = MON_DATA_OFFSET + global_idx * MON_SIZE
            if offset + MON_SIZE > len(pc_data):
                break

            mon_data = pc_data[offset : offset + MON_SIZE]
            pv = struct.unpack_from("<I", mon_data, 0x00)[0]
            ot_id = struct.unpack_from("<I", mon_data, 0x04)[0]

            if pv == 0 and ot_id == 0:
                continue

            nickname = decode.decode_string(mon_data[0x08:0x12])
            encrypted = mon_data[0x20:0x50]

            try:
                subs = _parse_substructures(pv, ot_id, encrypted)
            except Exception:
                continue

            if subs["species_id"] == 0:
                continue

            nature_idx = pv % 25
            nature_name = (natures[nature_idx]["name"]
                          if nature_idx < len(natures) else "Unknown")
            species_name = species_data.get(
                str(subs["species_id"]),
                f"Unknown ({subs['species_id']})"
            )
            held_item = items.get(str(subs["item_id"]), "None")
            if subs["item_id"] == 0:
                held_item = "None"

            level = _estimate_level(subs["experience"])

            move_names = []
            for mid in subs["move_ids"]:
                if mid == 0:
                    continue
                info = moves_data.get(str(mid), {"name": f"Move {mid}"})
                move_names.append(info["name"])

            misc_flags = mon_data[0x13]
            is_egg = subs["is_egg"] or bool(misc_flags & (1 << 2))

            pokemon_list.append({
                "slot": mon_slot + 1,
                "species_id": subs["species_id"],
                "species_name": species_name,
                "nickname": nickname,
                "level": level,
                "nature": nature_name,
                "ability": "Unknown",
                "held_item": held_item,
                "moves": move_names,
                "is_egg": is_egg,
            })

        boxes.append({
            "box_index": box_idx,
            "name": box_name,
            "pokemon": pokemon_list,
        })

    return boxes
