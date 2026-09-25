"""Parse trainer info, badges, location, inventory, and Pokédex from a
Generation I save."""

from __future__ import annotations

import logging

from .. import data_loader
from . import layout

logger = logging.getLogger(__name__)


def parse_trainer(sav: bytes) -> dict:
    return {
        "trainer": {
            "name": layout.decode_string(sav[layout.PLAYER_NAME: layout.PLAYER_NAME + layout.NAME_LENGTH]),
            "gender": "male",  # Red/Blue have only the male protagonist
            "trainer_id": layout.u16(sav, layout.PLAYER_ID),
            "rival_name": layout.decode_string(sav[layout.RIVAL_NAME: layout.RIVAL_NAME + layout.NAME_LENGTH]),
            "playtime": {
                "hours": sav[layout.PLAY_HOURS],
                "minutes": sav[layout.PLAY_MINUTES],
                "seconds": sav[layout.PLAY_SECONDS],
            },
            "money": layout.bcd(sav[layout.MONEY: layout.MONEY + 3]),
            "coins": layout.bcd(sav[layout.COINS: layout.COINS + 2]),
        }
    }


def parse_badges(sav: bytes) -> dict:
    bits = sav[layout.BADGES]
    obtained = [name for i, name in enumerate(layout.BADGE_NAMES) if bits & (1 << i)]
    return {"badges": {"count": len(obtained), "obtained": obtained}}


def parse_location(sav: bytes) -> dict:
    map_id = sav[layout.CUR_MAP]
    name = data_loader.load_gen1_location_index().get(map_id)
    known = name is not None
    if not known:
        name = f"Unknown (map={map_id})"
        logger.warning("Unknown Gen 1 map id %d — add to parser/data/gen1/locations.json", map_id)
    return {"location": {"map_bank": None, "map_id": map_id, "name": name, "known": known}}


def _parse_item_list(sav: bytes, offset: int, capacity: int, label: str) -> list[dict]:
    items = data_loader.load_gen1_items()
    count = sav[offset]
    if count > capacity:
        logger.warning("%s item count %d exceeds capacity %d; clamping", label, count, capacity)
        count = capacity
    out = []
    for i in range(count):
        item_id = sav[offset + 1 + i * 2]
        if item_id == 0xFF:
            break
        qty = sav[offset + 2 + i * 2]
        out.append({"name": items.get(str(item_id), f"Unknown Item ({item_id})"), "quantity": qty})
    return out


def parse_inventory(sav: bytes) -> dict:
    """Gen 1 has one 20-slot bag (no pockets) and a 50-slot PC item box."""
    return {
        "inventory": {
            "items": _parse_item_list(sav, layout.BAG_ITEMS, layout.BAG_CAPACITY, "Bag"),
            "pc": _parse_item_list(sav, layout.PC_ITEMS, layout.PC_ITEM_CAPACITY, "PC"),
        }
    }


def _count_bits(data: bytes, num_bits: int) -> int:
    return sum(1 for i in range(num_bits) if data[i // 8] & (1 << (i % 8)))


def parse_pokedex(sav: bytes) -> dict:
    return {
        "pokedex": {
            "seen": _count_bits(sav[layout.POKEDEX_SEEN: layout.POKEDEX_SEEN + 19], 151),
            "caught": _count_bits(sav[layout.POKEDEX_OWNED: layout.POKEDEX_OWNED + 19], 151),
        }
    }
