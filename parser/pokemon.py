"""Parse party and PC box Pokémon from Generation III (Ruby/Sapphire)
save sectors."""

import logging
import struct
from typing import Any

from . import data_loader, decode

logger = logging.getLogger(__name__)

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
    moves_data = data_loader.load_moves()
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
# Nature effect formatting
# ---------------------------------------------------------------------------

_STAT_ABBR = {
    "attack": "Atk", "defense": "Def", "speed": "Spd",
    "sp_atk": "SpAtk", "sp_def": "SpDef",
}


def _format_nature_effect(nature: dict) -> str:
    up = nature.get("stat_up", "none")
    down = nature.get("stat_down", "none")
    if up == "none" or down == "none":
        return "neutral"
    return f"{_STAT_ABBR.get(up, up)}↑, {_STAT_ABBR.get(down, down)}↓"


# ---------------------------------------------------------------------------
# Growth rate / level estimation
# ---------------------------------------------------------------------------

def _exp_for_level(n: int, growth_rate: str) -> int:
    """Return the minimum EXP required to be at level n."""
    if n <= 1:
        return 0
    if growth_rate == "medium_fast":
        return n ** 3
    if growth_rate == "erratic":
        if n <= 50:
            return n ** 3 * (100 - n) // 50
        if n <= 68:
            return n ** 3 * (150 - n) // 100
        if n <= 98:
            return n ** 3 * ((1911 - 10 * n) // 3) // 500
        return n ** 3 * (160 - n) // 100
    if growth_rate == "fluctuating":
        if n <= 15:
            return n ** 3 * (((n + 1) // 3) + 24) // 50
        if n <= 36:
            return n ** 3 * (n + 14) // 50
        return n ** 3 * ((n // 2) + 32) // 50
    if growth_rate == "medium_slow":
        return max(0, (6 * n ** 3) // 5 - 15 * n ** 2 + 100 * n - 140)
    if growth_rate == "fast":
        return 4 * n ** 3 // 5
    if growth_rate == "slow":
        return 5 * n ** 3 // 4
    # default fallback
    return n ** 3


def _estimate_level(experience: int, growth_rate: str = "medium_fast") -> int:
    """Derive level from EXP using the correct growth rate curve."""
    if experience <= 0:
        return 1
    for lv in range(100, 0, -1):
        if _exp_for_level(lv, growth_rate) <= experience:
            return lv
    return 1


# ---------------------------------------------------------------------------
# Shared 80-byte box-format Pokémon record parsing
# ---------------------------------------------------------------------------

def _parse_mon_record(mon_data: bytes) -> dict[str, Any] | None:
    """Parse an 80-byte Gen III box-format Pokémon record.

    Shared by party, box, and daycare parsing — party parsing wraps this and
    overlays the party-only fields (status, hp, stats, stored level).
    Returns None if the slot is empty or otherwise unparseable.
    """
    if len(mon_data) < 80:
        return None

    pv = struct.unpack_from("<I", mon_data, 0x00)[0]
    ot_id = struct.unpack_from("<I", mon_data, 0x04)[0]
    if pv == 0 and ot_id == 0:
        return None

    nickname = decode.decode_string(mon_data[0x08:0x12])
    encrypted = mon_data[0x20:0x50]

    try:
        subs = _parse_substructures(pv, ot_id, encrypted)
    except Exception:
        return None

    species_id = subs["species_id"]
    if species_id == 0:
        return None

    species_names = data_loader.load_species()
    species_info = data_loader.load_species_info()
    natures = data_loader.load_natures()
    items = data_loader.load_items()
    growth_rates = data_loader.load_growth_rates()

    info = species_info.get(str(species_id))
    if info is None:
        logger.warning(
            "No species_info entry for species_id %d (%s) — types/ability unresolved",
            species_id, species_names.get(str(species_id), "?"),
        )
        types = ["Unknown"]
        ability = "Unknown"
    else:
        types = info.get("types") or ["Unknown"]
        abilities = info.get("abilities") or []
        if not abilities:
            ability = "Unknown"
        elif len(abilities) > 1:
            ability = abilities[subs["ability_bit"]]
        else:
            ability = abilities[0]

    species_name = species_names.get(str(species_id), f"Unknown ({species_id})")

    nature_idx = pv % 25
    nature = (natures[nature_idx] if nature_idx < len(natures)
              else {"name": "Unknown", "stat_up": "none", "stat_down": "none"})

    held_item = items.get(str(subs["item_id"]), "None") if subs["item_id"] else "None"

    growth_rate = growth_rates.get(str(species_id), "medium_fast")
    level = _estimate_level(subs["experience"], growth_rate)

    misc_flags = mon_data[0x13]
    is_egg = subs["is_egg"] or bool(misc_flags & (1 << 2))

    return {
        "pid": f"0x{pv:08X}",
        "species_id": species_id,
        "species_name": species_name,
        "nickname": nickname,
        "types": types,
        "ability": ability,
        "level": level,
        "experience": subs["experience"],
        "nature": nature["name"],
        "nature_effect": _format_nature_effect(nature),
        "held_item": held_item,
        "moves": _format_moves(subs["move_ids"], subs["pps"], subs["pp_bonuses"]),
        "is_egg": is_egg,
    }


# ---------------------------------------------------------------------------
# Party parsing
# ---------------------------------------------------------------------------

def parse_party(sections: dict[int, bytes]) -> list[dict[str, Any]]:
    """Parse party Pokémon from Section 1."""
    section1 = decode.get_sector_data(sections, 1)

    team_size = struct.unpack_from("<I", section1, 0x0234)[0]
    if team_size > 6:
        team_size = 6

    party: list[dict[str, Any]] = []

    for slot in range(team_size):
        offset = 0x0238 + slot * 100
        mon_data = section1[offset : offset + 100]
        if len(mon_data) < 100:
            continue

        mon = _parse_mon_record(mon_data[:80])
        if mon is None:
            continue

        # Party-only battle stats (bytes 0x50-0x63 of the 100-byte record)
        status = struct.unpack_from("<I", mon_data, 0x50)[0]
        stored_level = mon_data[0x54]
        current_hp = struct.unpack_from("<H", mon_data, 0x56)[0]
        max_hp = struct.unpack_from("<H", mon_data, 0x58)[0]
        attack = struct.unpack_from("<H", mon_data, 0x5A)[0]
        defense = struct.unpack_from("<H", mon_data, 0x5C)[0]
        speed = struct.unpack_from("<H", mon_data, 0x5E)[0]
        sp_atk = struct.unpack_from("<H", mon_data, 0x60)[0]
        sp_def = struct.unpack_from("<H", mon_data, 0x62)[0]

        mon["slot"] = slot + 1
        mon["level"] = stored_level
        mon["status"] = _decode_status(status)
        mon["hp"] = {"current": current_hp, "max": max_hp}
        mon["stats"] = {
            "attack": attack,
            "defense": defense,
            "speed": speed,
            "sp_atk": sp_atk,
            "sp_def": sp_def,
        }
        party.append(mon)

    return party


# ---------------------------------------------------------------------------
# Box parsing
# ---------------------------------------------------------------------------

def _concat_box_data(sections: dict[int, bytes]) -> bytes:
    """Concatenate sections 5-13 into the PC storage blob."""
    parts = []
    for section_id in range(5, 14):
        try:
            parts.append(decode.get_sector_data(sections, section_id))
        except ValueError:
            break
    return b"".join(parts)


def parse_boxes(sections: dict[int, bytes]) -> list[dict[str, Any]]:
    """Parse PC box Pokémon from Sections 5-13."""
    pc_data = _concat_box_data(sections)
    if not pc_data:
        return []

    BOX_NAME_OFFSET = 0x8344
    BOX_COUNT = 14
    MONS_PER_BOX = 30
    MON_SIZE = 80
    MON_DATA_OFFSET = 4

    boxes: list[dict[str, Any]] = []

    for box_idx in range(BOX_COUNT):
        # Read box name
        name_offset = BOX_NAME_OFFSET + box_idx * 9
        box_name = ""
        if name_offset + 9 <= len(pc_data):
            box_name = decode.decode_string(pc_data[name_offset:name_offset + 9])
        if not box_name:
            box_name = f"BOX {box_idx + 1}"

        pokemon_list: list[dict[str, Any]] = []

        for mon_slot in range(MONS_PER_BOX):
            global_idx = box_idx * MONS_PER_BOX + mon_slot
            offset = MON_DATA_OFFSET + global_idx * MON_SIZE
            if offset + MON_SIZE > len(pc_data):
                break

            mon = _parse_mon_record(pc_data[offset : offset + MON_SIZE])
            if mon is None:
                continue

            mon["slot"] = mon_slot + 1
            pokemon_list.append(mon)

        boxes.append({
            "box_index": box_idx,
            "name": box_name,
            "pokemon": pokemon_list,
        })

    return boxes


# ---------------------------------------------------------------------------
# Daycare parsing
# ---------------------------------------------------------------------------

# Section 4 offsets for the two daycare slots (box-format, 80 bytes each).
# Confirmed empirically against RS save structure.
_DAYCARE_SECTION = 4
_DAYCARE_SLOT_OFFSETS = (0x011C, 0x016C)


def parse_daycare(sections: dict[int, bytes]) -> list[dict[str, Any]]:
    """Return up to 2 deposited Pokémon from the Gen III daycare."""
    try:
        sec4 = decode.get_sector_data(sections, _DAYCARE_SECTION)
    except ValueError:
        return []

    result: list[dict[str, Any]] = []
    for slot_idx, offset in enumerate(_DAYCARE_SLOT_OFFSETS, start=1):
        mon_data = sec4[offset : offset + 80]
        mon = _parse_mon_record(mon_data)
        if mon is None:
            continue
        mon["slot"] = slot_idx
        result.append(mon)
    return result
