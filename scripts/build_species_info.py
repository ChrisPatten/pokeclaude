"""build_species_info.py — generate parser/data/species_info.json.

Reads the Gen 3 Pokédex reference (data/gen_3/pokedex_gen3.md, keyed by
National Dex number) and joins it against parser/data/species.json (keyed by
the internal Gen 3 species id used inside .srm save files) to produce a table
the parser can index directly by internal id:

    {"<internal_id>": {"name", "national_dex", "types": [...], "abilities": [...]}}

Internal Gen 3 species ids do not match National Dex numbers for Hoenn
Pokémon (and Unown forms), so the join key is the species *name*, with a
small alias table for spelling differences between the two data sources.

pokedex_gen3.md's "Abilities:" field is not always in ability1/ability2
order (it disagrees with the actual game data for ~100 species — order
matters because the parser resolves a Pokémon's ability as
abilities[ability_bit]), and it has no entry at all for the vestigial
"Old Unown" id range (252-276). This script gets types/abilities/national
dex close enough to be useful, but is NOT the final word — always follow
it with:

    python3 scripts/verify_data_vs_pokeruby.py --fix

which cross-checks (and corrects) types, abilities, and growth rates
against the pret/pokeruby decompilation, the authoritative source.

Usage: python3 scripts/build_species_info.py
"""

import json
import re
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_POKEDEX_MD = _ROOT / "data" / "gen_3" / "pokedex_gen3.md"
_SPECIES_JSON = _ROOT / "parser" / "data" / "species.json"
_OUTPUT_JSON = _ROOT / "parser" / "data" / "species_info.json"

_LINE_RE = re.compile(
    r"^(?P<dex>\d{3}) (?P<name>.+?) Type1:(?P<type1>\S*) Type2:(?P<type2>\S*) "
    r"HP:\d+ Atk:\d+ Def:\d+ SpAtk:\d+ SpDef:\d+ Spd:\d+ BST:\d+ "
    r"Abilities:(?P<abilities>.+)$"
)

# Species whose name in pokedex_gen3.md differs from the name in species.json.
# Maps the species.json spelling -> the pokedex_gen3.md spelling.
_NAME_ALIASES: dict[str, str] = {
    "Nidoran F": "Nidoran♀",
    "Nidoran M": "Nidoran♂",
}

# pokedex_gen3.md leaves Type1 blank for a handful of species that are
# Fairy-type in modern games (Fairy did not exist in Gen 3). All of these
# were pure/partial Normal type in Gen 3 — fill in the gap rather than
# emit a Pokémon with zero types. (data/gen_3/pokedex_gen3.md is owned by
# another workstream, so this is corrected here rather than in the source.)
_BLANK_TYPE1_FIX = "Normal"


def _parse_pokedex_md() -> dict[str, dict]:
    """Return {name: {"national_dex", "types", "abilities"}} keyed by the
    name exactly as written in pokedex_gen3.md."""
    entries: dict[str, dict] = {}
    with open(_POKEDEX_MD, encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.rstrip("\n")
            if not line.strip():
                continue
            m = _LINE_RE.match(line)
            if not m:
                print(f"WARNING: could not parse pokedex_gen3.md line {lineno}: {line!r}")
                continue

            type1 = m.group("type1") or _BLANK_TYPE1_FIX
            type2 = m.group("type2")
            types = [t for t in (type1, type2) if t and t.lower() != "none"]
            if not types:
                types = [_BLANK_TYPE1_FIX]

            abilities = [a.strip() for a in m.group("abilities").split(",") if a.strip()]

            entries[m.group("name")] = {
                "national_dex": int(m.group("dex")),
                "types": types,
                "abilities": abilities,
            }
    return entries


def _dex_lookup_name(species_name: str) -> str:
    """Map a species.json name to the name used as the key in pokedex_gen3.md."""
    if species_name in _NAME_ALIASES:
        return _NAME_ALIASES[species_name]
    if species_name.startswith("Unown"):
        # species.json has one entry per Unown form (Unown, Unown B..Unown Z);
        # pokedex_gen3.md only has a single "Unown" entry (National Dex #201).
        return "Unown"
    return species_name


def build() -> None:
    with open(_SPECIES_JSON, encoding="utf-8") as f:
        species: dict[str, str] = json.load(f)

    dex_entries = _parse_pokedex_md()

    species_info: dict[str, dict] = {}
    unmatched: list[str] = []

    for internal_id, name in species.items():
        if internal_id == "0" or name == "None":
            continue

        dex_name = _dex_lookup_name(name)
        entry = dex_entries.get(dex_name)
        if entry is None:
            unmatched.append(f"{internal_id} {name!r} (looked up as {dex_name!r})")
            continue

        species_info[internal_id] = {
            "name": name,
            "national_dex": entry["national_dex"],
            "types": entry["types"],
            "abilities": entry["abilities"],
        }

    with open(_OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(species_info, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Wrote {len(species_info)} species to {_OUTPUT_JSON}")
    if unmatched:
        print(f"\n{len(unmatched)} species from species.json could not be matched:")
        for line in unmatched:
            print(f"  - {line}")


if __name__ == "__main__":
    build()
