"""parse_save.py — Pokémon Ruby/Sapphire .srm save file parser.

CLI usage:  python -m parser.parse_save <path/to/save.srm>
Import:     from parser.parse_save import parse
"""

import json
import sys
from datetime import datetime, timezone

from . import decode, trainer, pokemon


def parse(srm_path: str) -> dict:
    """Parse a Pokémon Sapphire .srm save file and return a structured dict."""
    with open(srm_path, "rb") as f:
        data = f.read()

    sectors_a, sectors_b = decode.read_sectors(data)
    sectors, slot = decode.select_save_slot(sectors_a, sectors_b)

    result = {}
    result.update(trainer.parse_trainer(sectors))
    result.update(trainer.parse_badges(sectors))
    result.update(trainer.parse_location(sectors))
    result["party"] = pokemon.parse_party(sectors)
    result["boxes"] = pokemon.parse_boxes(sectors)
    result.update(trainer.parse_inventory(sectors))
    result.update(trainer.parse_pokedex(sectors))
    result["save_metadata"] = {
        "save_slot": slot,
        "checksum_valid": True,
        "parsed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    return result


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python -m parser.parse_save <path/to/save.srm>")
        sys.exit(1)
    result = parse(sys.argv[1])
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
