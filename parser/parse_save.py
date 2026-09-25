"""parse_save.py — Pokémon save file parser (Gen 3 Ruby/Sapphire, Gen 1 Red/Blue).

CLI usage:  python -m parser.parse_save <path/to/save> [--gen {1,3}]
Import:     from parser.parse_save import parse

The generation is taken from ``gen`` when given (parser.sync passes the
trainer's config.json "gen"), otherwise detected from the file size:
128KB flash saves are Gen 3, 32KB SRAM saves are Gen 1.

stdout is JSON only; all logging (including warnings collected into the
output's "warnings" list) goes to stderr.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone

from . import __version__, decode, gen1, trainer, pokemon

SUPPORTED_GENERATIONS = (1, 3)

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


def detect_generation(data: bytes) -> int:
    """Guess the generation from the save size.

    Gen 3 flash saves are 128KB (at least two 56KB blocks). Gen 1 SRAM saves
    are 32KB, sometimes with a few bytes of emulator RTC data appended. Gen 2
    saves are also 32KB and are not supported — pass ``gen`` explicitly
    rather than relying on detection when that matters.
    """
    if len(data) >= 2 * decode.SAVE_BLOCK_SIZE:
        return 3
    if gen1.layout.SAVE_SIZE <= len(data) < 2 * gen1.layout.SAVE_SIZE:
        return 1
    raise ValueError(
        f"Unrecognized save size: {len(data)} bytes "
        f"(expected {gen1.layout.SAVE_SIZE} for Gen 1 or at least "
        f"{2 * decode.SAVE_BLOCK_SIZE} for Gen 3)"
    )


def _parse_gen3(data: bytes) -> dict:
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
        "generation": 3,
        "save_slot": slot,
        "save_index": save_index,
        "checksum_valid": len(invalid_sections) == 0,
        "invalid_sections": invalid_sections,
    }
    return result


def _parse_gen1(data: bytes) -> dict:
    # Gen 1 keeps a single save copy; parse_bytes raises on a bad checksum,
    # so reaching the metadata means the main data validated.
    result = gen1.parse_bytes(data)
    result["save_metadata"] = {
        "generation": 1,
        "save_slot": None,
        "save_index": None,
        "checksum_valid": True,
        "invalid_sections": [],
    }
    return result


def parse(srm_path: str, gen: int | None = None) -> dict:
    """Parse a save file and return a structured dict.

    *gen* selects the save format (1 or 3); None auto-detects from file size.
    """
    list_handler = _ListHandler()
    root_logger = logging.getLogger()
    root_logger.addHandler(list_handler)
    try:
        with open(srm_path, "rb") as f:
            data = f.read()

        if gen is None:
            gen = detect_generation(data)
        if gen == 3:
            result = _parse_gen3(data)
        elif gen == 1:
            result = _parse_gen1(data)
        else:
            raise ValueError(
                f"Unsupported generation {gen!r}; supported: {', '.join(map(str, SUPPORTED_GENERATIONS))}"
            )

        result["save_metadata"]["parsed_at"] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        result["warnings"] = list(list_handler.messages)
        return result
    finally:
        root_logger.removeHandler(list_handler)


def main() -> None:
    if sys.argv[1:2] == ["--version"]:
        print(f"parse_save {__version__}")
        return

    ap = argparse.ArgumentParser(prog="python -m parser.parse_save")
    ap.add_argument("path", help="save file (.srm for Gen 3, .sav/.srm for Gen 1)")
    ap.add_argument(
        "--gen", type=int, choices=SUPPORTED_GENERATIONS, default=None,
        help="save format generation (default: detect from file size)",
    )
    args = ap.parse_args()

    try:
        result = parse(args.path, gen=args.gen)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
