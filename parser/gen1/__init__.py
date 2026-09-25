"""Generation I (Pokémon Red/Blue) save parser.

Entry point: ``parse_bytes(sav) -> dict`` — the same top-level shape as the
Gen 3 parser (see parser/README.md for the Gen 1 differences). Raises
ValueError when the file is too small or the main-data checksum fails,
which ``parser.sync`` reports as ``invalid_save``.
"""

from __future__ import annotations

from . import layout, pokemon, trainer


def validate(sav: bytes) -> None:
    if len(sav) < layout.SAVE_SIZE:
        raise ValueError(
            f"Save file too small: {len(sav)} bytes (expected {layout.SAVE_SIZE} for a Gen 1 save)"
        )
    stored = sav[layout.CHECKSUM]
    computed = layout.checksum(sav, layout.CHECKSUM_START, layout.CHECKSUM_END)
    if stored != computed:
        raise ValueError(
            f"Gen 1 main save checksum mismatch (stored 0x{stored:02X}, computed 0x{computed:02X}). "
            "The file is corrupt, has never been saved, or is not a Red/Blue save."
        )


def parse_bytes(sav: bytes) -> dict:
    validate(sav)
    result: dict = {}
    result.update(trainer.parse_trainer(sav))
    result.update(trainer.parse_badges(sav))
    result.update(trainer.parse_location(sav))
    result["party"] = pokemon.parse_party(sav)
    result["boxes"] = pokemon.parse_boxes(sav)
    result["daycare"] = pokemon.parse_daycare(sav)
    pokemon.assign_unique_pids(result["party"], result["boxes"], result["daycare"])
    result.update(trainer.parse_inventory(sav))
    result.update(trainer.parse_pokedex(sav))
    return result
