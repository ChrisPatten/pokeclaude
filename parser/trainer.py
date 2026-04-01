"""Parse trainer info, badges, location, inventory, and Pokédex from
Generation III (Ruby/Sapphire) save sectors."""

import json
import struct
from pathlib import Path

from . import decode

_DATA_DIR = Path(__file__).parent / "data"

_items_cache: dict[str, str] | None = None
_locations_cache: list[dict] | None = None


def _load_items() -> dict[str, str]:
    global _items_cache
    if _items_cache is None:
        with open(_DATA_DIR / "items.json") as f:
            _items_cache = json.load(f)
    return _items_cache


def _load_locations() -> list[dict]:
    global _locations_cache
    if _locations_cache is None:
        with open(_DATA_DIR / "locations.json") as f:
            _locations_cache = json.load(f)
    return _locations_cache


def _lookup_item(item_id: int) -> str:
    items = _load_items()
    return items.get(str(item_id), f"Unknown Item ({item_id})")


def _lookup_location(map_bank: int, map_id: int) -> str:
    locations = _load_locations()
    for loc in locations:
        if loc["map_bank"] == map_bank and loc["map_id"] == map_id:
            return loc["name"]
    return f"Unknown (bank={map_bank}, id={map_id})"


# ---------------------------------------------------------------------------
# Security key (needed for money/item decryption in Emerald; 0 in RS)
# ---------------------------------------------------------------------------

def _get_security_key(sectors: list[bytes]) -> int:
    section0 = decode.get_sector_data(sectors, 0)
    return struct.unpack_from("<I", section0, 0x00AC)[0]


# ---------------------------------------------------------------------------
# Trainer info
# ---------------------------------------------------------------------------

def parse_trainer(sectors: list[bytes]) -> dict:
    section0 = decode.get_sector_data(sectors, 0)
    section1 = decode.get_sector_data(sectors, 1)
    security_key = struct.unpack_from("<I", section0, 0x00AC)[0]

    name = decode.decode_string(section0[0x0000:0x0007])
    gender_byte = section0[0x0008]
    trainer_id_full = struct.unpack_from("<I", section0, 0x000A)[0]
    public_id = trainer_id_full & 0xFFFF
    hours = struct.unpack_from("<H", section0, 0x000E)[0]
    minutes = section0[0x0010]
    seconds = section0[0x0011]

    # Money: Section 1, offset 0x0490, XOR with security key
    money_raw = struct.unpack_from("<I", section1, 0x0490)[0]
    money = money_raw ^ security_key

    return {
        "trainer": {
            "name": name,
            "gender": "female" if gender_byte == 1 else "male",
            "trainer_id": public_id,
            "playtime": {
                "hours": hours,
                "minutes": minutes,
                "seconds": seconds,
            },
            "money": money,
        }
    }


# ---------------------------------------------------------------------------
# Badges
# ---------------------------------------------------------------------------

HOENN_BADGES = [
    "Stone Badge", "Knuckle Badge", "Dynamo Badge", "Heat Badge",
    "Balance Badge", "Feather Badge", "Mind Badge", "Rain Badge",
]


def parse_badges(sectors: list[bytes]) -> dict:
    section2 = decode.get_sector_data(sectors, 2)

    # Badges are stored as event flags in Section 2.
    # Event flags start at offset 0x2A0 in Section 2.
    # Badge flags: FLAG_BADGE01_GET=0x807 through FLAG_BADGE08_GET=0x80E
    FLAGS_BASE = 0x2A0
    BADGE_FLAG_START = 0x807

    obtained = []
    for i, badge_name in enumerate(HOENN_BADGES):
        flag_id = BADGE_FLAG_START + i
        byte_idx = flag_id // 8
        bit_idx = flag_id % 8
        offset = FLAGS_BASE + byte_idx
        if offset < len(section2) and (section2[offset] & (1 << bit_idx)):
            obtained.append(badge_name)

    return {
        "badges": {
            "count": len(obtained),
            "obtained": obtained,
        }
    }


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------

def parse_location(sectors: list[bytes]) -> dict:
    section1 = decode.get_sector_data(sectors, 1)

    # SaveBlock1 layout: pos (4 bytes), then WarpData location
    # WarpData: mapGroup (1 byte), mapNum (1 byte), warpId, x, y
    map_bank = section1[0x0004]  # mapGroup
    map_id = section1[0x0005]    # mapNum
    name = _lookup_location(map_bank, map_id)

    return {
        "location": {
            "map_bank": map_bank,
            "map_id": map_id,
            "name": name,
        }
    }


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

def _parse_item_pocket(
    data: bytes, offset: int, capacity: int, security_key: int,
    is_key_items: bool = False,
) -> list[dict] | list[str]:
    items = _load_items()
    result: list = []
    qty_mask = security_key & 0xFFFF

    for i in range(capacity):
        entry_off = offset + i * 4
        if entry_off + 4 > len(data):
            break
        item_id = struct.unpack_from("<H", data, entry_off)[0]
        if item_id == 0:
            continue
        quantity = struct.unpack_from("<H", data, entry_off + 2)[0] ^ qty_mask
        name = items.get(str(item_id), f"Unknown Item ({item_id})")

        if is_key_items:
            result.append(name)
        else:
            result.append({"name": name, "quantity": quantity})

    return result


def parse_inventory(sectors: list[bytes]) -> dict:
    section1 = decode.get_sector_data(sectors, 1)
    security_key = _get_security_key(sectors)

    return {
        "inventory": {
            "pc":        _parse_item_pocket(section1, 0x0498, 50, security_key),
            "items":     _parse_item_pocket(section1, 0x0560, 20, security_key),
            "key_items": _parse_item_pocket(section1, 0x05B0, 20, security_key,
                                            is_key_items=True),
            "balls":     _parse_item_pocket(section1, 0x0600, 16, security_key),
            "tms_hms":   _parse_item_pocket(section1, 0x0640, 64, security_key),
            "berries":   _parse_item_pocket(section1, 0x0740, 46, security_key),
        }
    }


# ---------------------------------------------------------------------------
# Pokédex
# ---------------------------------------------------------------------------

def _count_bits(data: bytes, num_bits: int) -> int:
    count = 0
    for i in range(num_bits):
        byte_idx = i // 8
        bit_idx = i % 8
        if byte_idx < len(data) and (data[byte_idx] & (1 << bit_idx)):
            count += 1
    return count


def parse_pokedex(sectors: list[bytes]) -> dict:
    section0 = decode.get_sector_data(sectors, 0)

    # Pokédex owned (caught) and seen flags — offsets for RS
    # These are 49-byte bitfields (386 pokemon)
    caught_data = section0[0x0028:0x0028 + 49]
    seen_data = section0[0x005C:0x005C + 49]

    return {
        "pokedex": {
            "seen": _count_bits(seen_data, 386),
            "caught": _count_bits(caught_data, 386),
        }
    }
