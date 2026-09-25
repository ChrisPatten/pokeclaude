"""Cached loaders for static reference data (Generation III and Generation I).

All parser modules should load species/move/nature/item/location/growth-rate
tables through this module instead of reading parser/data/*.json themselves,
so each file is parsed once per process regardless of how many modules use it.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).parent / "data"


def _load_json(filename: str) -> Any:
    with open(_DATA_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_species() -> dict[str, str]:
    """Internal Gen 3 species id (str) -> display name."""
    return _load_json("species.json")


@lru_cache(maxsize=1)
def load_species_info() -> dict[str, dict]:
    """Internal Gen 3 species id (str) -> {"name", "national_dex", "types", "abilities"}."""
    return _load_json("species_info.json")


@lru_cache(maxsize=1)
def load_moves() -> dict[str, dict]:
    """Move id (str) -> {"name", "type", "pp"}."""
    return _load_json("moves.json")


@lru_cache(maxsize=1)
def load_natures() -> list[dict]:
    """Nature table, indexed by PID % 25 -> {"name", "stat_up", "stat_down"}."""
    return _load_json("natures.json")


@lru_cache(maxsize=1)
def load_items() -> dict[str, str]:
    """Item id (str) -> display name."""
    return _load_json("items.json")


@lru_cache(maxsize=1)
def load_locations() -> list[dict]:
    """Raw location table: [{"map_bank", "map_id", "name"}, ...]."""
    return _load_json("locations.json")


@lru_cache(maxsize=1)
def load_location_index() -> dict[tuple[int, int], str]:
    """(map_bank, map_id) -> location name, built once from load_locations()."""
    return {(loc["map_bank"], loc["map_id"]): loc["name"] for loc in load_locations()}


@lru_cache(maxsize=1)
def load_growth_rates() -> dict[str, str]:
    """Internal Gen 3 species id (str) -> growth rate key (medium_fast, erratic, ...)."""
    data = _load_json("growth_rates.json")
    return {k: v for k, v in data.items() if k != "comment"}


# ---------------------------------------------------------------------------
# Generation I (Red/Blue) — parser/data/gen1/, built by scripts/build_gen1_data.py
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_gen1_species() -> dict[str, dict]:
    """Internal Gen 1 species index (str) -> {"name", "national_dex", "types", "growth_rate"}."""
    return _load_json("gen1/species.json")


@lru_cache(maxsize=1)
def load_gen1_moves() -> dict[str, dict]:
    """Move id (str) -> {"name", "type", "pp", "power", "accuracy"} with Gen 1 values."""
    return _load_json("gen1/moves.json")


@lru_cache(maxsize=1)
def load_gen1_items() -> dict[str, str]:
    """Gen 1 item id (str) -> display name ("TM01"/"HM01" for machines)."""
    return _load_json("gen1/items.json")


@lru_cache(maxsize=1)
def load_gen1_location_index() -> dict[int, str]:
    """Gen 1 map id -> location name."""
    return {loc["map_id"]: loc["name"] for loc in _load_json("gen1/locations.json")}
