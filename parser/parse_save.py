"""parse_save.py — Pokémon Ruby/Sapphire .srm save file parser.

CLI usage:  python -m parser.parse_save <path/to/save.srm>
Import:     from parser.parse_save import parse

stdout is JSON only; all logging (including warnings collected into the
output's "warnings" list) goes to stderr.
"""

import json
import logging
import sys
from datetime import datetime, timezone

from . import __version__, decode, trainer, pokemon

logging.basicConfig(
    level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s"
)


class _ListHandler(logging.Handler):
    """Collects formatted WARNING+ log records so they can be surfaced in
    the parsed output's "warnings" list, in addition to stderr."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def parse(srm_path: str) -> dict:
    """Parse a Pokémon Ruby/Sapphire .srm save file and return a structured dict."""
    list_handler = _ListHandler()
    root_logger = logging.getLogger()
    root_logger.addHandler(list_handler)
    try:
        with open(srm_path, "rb") as f:
            data = f.read()

        min_size = 2 * decode.SAVE_BLOCK_SIZE
        if len(data) < min_size:
            raise ValueError(
                f"Save file too small: {len(data)} bytes "
                f"(expected at least {min_size} for a Gen 3 save)"
            )

        sectors_a, sectors_b = decode.read_sectors(data)
        sections, slot, save_index, invalid_sections = decode.select_save_slot(
            sectors_a, sectors_b
        )

        result: dict = {}
        result.update(trainer.parse_trainer(sections))
        result.update(trainer.parse_badges(sections))
        result.update(trainer.parse_location(sections))
        result["party"] = pokemon.parse_party(sections)
        result["boxes"] = pokemon.parse_boxes(sections)
        result["daycare"] = pokemon.parse_daycare(sections)
        result.update(trainer.parse_inventory(sections))
        result.update(trainer.parse_pokedex(sections))
        result["save_metadata"] = {
            "save_slot": slot,
            "save_index": save_index,
            "checksum_valid": len(invalid_sections) == 0,
            "invalid_sections": invalid_sections,
            "parsed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        result["warnings"] = list(list_handler.messages)
        return result
    finally:
        root_logger.removeHandler(list_handler)


def main() -> None:
    if sys.argv[1:2] == ["--version"]:
        print(f"parse_save {__version__}")
        return

    if len(sys.argv) != 2:
        print("Usage: python -m parser.parse_save <path/to/save.srm>", file=sys.stderr)
        sys.exit(1)

    try:
        result = parse(sys.argv[1])
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
