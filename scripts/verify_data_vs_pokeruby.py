"""verify_data_vs_pokeruby.py — cross-check our species reference data against
the pret/pokeruby decompilation (the authoritative source for Gen 3 Ruby's
actual compiled data tables).

Fetches (or reuses a cached copy of) three pokeruby headers:
    src/data/pokemon/base_stats.h   — per-species type1/type2/ability1/ability2/growthRate
    include/constants/species.h     — SPECIES_<TOKEN> -> internal id
    include/constants/abilities.h   — ABILITY_<TOKEN> -> numeric id

and compares them against our parser/data/species.json (names),
parser/data/species_info.json (types, abilities) and
parser/data/growth_rates.json (growth rate), for every internal id our
species.json currently defines (0-411 as of this writing).

Reports every mismatch. Pass --fix to write corrected values back to
species_info.json and growth_rates.json (species.json names are reported
only, never silently rewritten, since a name change is a bigger/riskier
edit than swapping a type/ability/growth-rate string).

Usage:
    python3 scripts/verify_data_vs_pokeruby.py            # report only
    python3 scripts/verify_data_vs_pokeruby.py --fix       # report and fix
"""

import json
import re
import sys
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_CACHE_DIR = Path(__file__).parent / "cache"
_DATA_DIR = _ROOT / "parser" / "data"

_RAW_BASE = "https://raw.githubusercontent.com/pret/pokeruby/master"
_SOURCES = {
    "base_stats.h": f"{_RAW_BASE}/src/data/pokemon/base_stats.h",
    "species.h": f"{_RAW_BASE}/include/constants/species.h",
    "abilities.h": f"{_RAW_BASE}/include/constants/abilities.h",
}

# Special-case display names where a mechanical TOKEN -> "Title Case" pass
# gets it wrong (punctuation, symbols, or a name pokeruby's token doesn't spell
# out plainly).
_TOKEN_NAME_OVERRIDES = {
    "NIDORAN_F": "Nidoran♀",
    "NIDORAN_M": "Nidoran♂",
    "MR_MIME": "Mr. Mime",
    "FARFETCHD": "Farfetch'd",
    "HO_OH": "Ho-Oh",
    "PORYGON2": "Porygon2",
}


def _fetch(name: str, url: str) -> str:
    _CACHE_DIR.mkdir(exist_ok=True)
    cached = _CACHE_DIR / name
    if cached.exists():
        return cached.read_text(encoding="latin-1")
    with urllib.request.urlopen(url, timeout=30) as resp:
        text = resp.read().decode("latin-1")
    cached.write_text(text, encoding="latin-1")
    return text


def _load_json(name: str):
    with open(_DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def _humanize_token(token: str) -> str:
    if token in _TOKEN_NAME_OVERRIDES:
        return _TOKEN_NAME_OVERRIDES[token]
    return token.replace("_", " ").title().replace("2", "2")


def _parse_species_h(text: str) -> dict[int, str]:
    """id -> SPECIES_ token (without the SPECIES_ prefix)."""
    result = {}
    for m in re.finditer(r"#define SPECIES_(\w+) (\d+)", text):
        result[int(m.group(2))] = m.group(1)
    return result


def _parse_abilities_h(text: str) -> dict[str, int]:
    """ABILITY_ token (without prefix) -> numeric id."""
    result = {}
    for m in re.finditer(r"#define ABILITY_(\w+) (\d+)", text):
        result[m.group(1)] = int(m.group(2))
    return result


# The OLD_UNOWN_BASE_STATS macro is referenced (not inlined) for species ids
# 252-276 ("old" / vestigial Unown slots never used by real save data in
# Ruby/Sapphire — see base_stats.h). Its fields, read directly from the
# macro definition:
_OLD_UNOWN_STATS = {
    "type1": "NORMAL",
    "type2": "NORMAL",
    "ability1": "NONE",
    "ability2": "NONE",
    "growthRate": "MEDIUM_FAST",
}


def _parse_base_stats_h(text: str, species_by_id: dict[int, str]) -> dict[int, dict]:
    """id -> {"type1","type2","ability1","ability2","growthRate"} (all as
    the bare token following TYPE_/ABILITY_/GROWTH_)."""
    token_to_id = {tok: sid for sid, tok in species_by_id.items()}
    result: dict[int, dict] = {}

    for m in re.finditer(r"\[SPECIES_(\w+)\]\s*=\s*(OLD_UNOWN_BASE_STATS|\{)", text):
        token = m.group(1)
        sid = token_to_id.get(token)
        if sid is None or sid == 0:
            continue

        if m.group(2) == "OLD_UNOWN_BASE_STATS":
            result[sid] = dict(_OLD_UNOWN_STATS)
            continue

        # Find the matching closing "},"/"}," for this brace-initialised block.
        block_start = m.end() - 1  # position of the opening '{'
        depth = 0
        end = block_start
        for i, ch in enumerate(text[block_start:], start=block_start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        block = text[block_start:end]

        def field(name: str, prefix: str) -> str | None:
            fm = re.search(rf"\.{name}\s*=\s*{prefix}(\w+)", block)
            return fm.group(1) if fm else None

        result[sid] = {
            "type1": field("type1", "TYPE_"),
            "type2": field("type2", "TYPE_"),
            "ability1": field("ability1", "ABILITY_"),
            "ability2": field("ability2", "ABILITY_"),
            "growthRate": field("growthRate", "GROWTH_"),
        }

    return result


def build_pokeruby_table() -> dict[int, dict]:
    """id -> {"name", "types": [...], "abilities": [...], "growth_rate"}."""
    base_stats_text = _fetch("base_stats.h", _SOURCES["base_stats.h"])
    species_text = _fetch("species.h", _SOURCES["species.h"])
    abilities_text = _fetch("abilities.h", _SOURCES["abilities.h"])

    species_by_id = _parse_species_h(species_text)
    ability_token_to_id = _parse_abilities_h(abilities_text)
    raw = _parse_base_stats_h(base_stats_text, species_by_id)

    our_abilities = _load_json("abilities.json")

    def ability_name(token: str | None) -> str | None:
        if token is None:
            return None
        aid = ability_token_to_id.get(token)
        if aid is None:
            return None
        return our_abilities.get(str(aid))

    table: dict[int, dict] = {}
    for sid, fields in raw.items():
        type1 = _humanize_token(fields["type1"]) if fields["type1"] else None
        type2 = _humanize_token(fields["type2"]) if fields["type2"] else None
        # pokeruby represents a single-type Pokemon as type1 == type2 (not a
        # "none" sentinel) — dedupe before comparing against our data, which
        # only lists a second type when the Pokemon actually has one.
        if type2 == type1:
            types = [type1] if type1 else ["Normal"]
        else:
            types = [t for t in (type1, type2) if t and t != "Mystery"]
        if not types:
            types = ["Normal"]

        a1 = ability_name(fields["ability1"]) or "None"
        a2 = ability_name(fields["ability2"]) or "None"
        if a2 != "None" and a2 != a1:
            abilities = [a1, a2]
        else:
            abilities = [a1]

        growth_rate = fields["growthRate"].lower() if fields["growthRate"] else None

        table[sid] = {
            "name": _humanize_token(species_by_id[sid]),
            "types": types,
            "abilities": abilities,
            "growth_rate": growth_rate,
        }
    return table


def main() -> None:
    fix = "--fix" in sys.argv

    pokeruby = build_pokeruby_table()
    species = _load_json("species.json")
    species_info = _load_json("species_info.json")
    growth_rates = _load_json("growth_rates.json")
    growth_rates = {k: v for k, v in growth_rates.items() if k != "comment"}

    name_mismatches = []
    type_mismatches = []
    ability_mismatches = []
    growth_mismatches = []
    missing_from_pokeruby = []

    for id_str, name in species.items():
        sid = int(id_str)
        if sid == 0:
            continue
        pr = pokeruby.get(sid)
        if pr is None:
            missing_from_pokeruby.append((sid, name))
            continue

        if pr["name"] != name:
            name_mismatches.append((sid, name, pr["name"]))

        info = species_info.get(id_str, {})
        if info.get("types") != pr["types"]:
            type_mismatches.append((sid, name, info.get("types"), pr["types"]))

        our_abilities_list = info.get("abilities") or []
        pr_abilities = pr["abilities"] or ["None"]
        if our_abilities_list != pr_abilities:
            ability_mismatches.append((sid, name, our_abilities_list, pr_abilities))

        our_growth = growth_rates.get(id_str)
        if our_growth != pr["growth_rate"]:
            growth_mismatches.append((sid, name, our_growth, pr["growth_rate"]))

    print(f"Checked {len(species) - 1} species (ids 1-{max(int(k) for k in species)}) "
          f"against pokeruby.\n")

    print(f"Name mismatches: {len(name_mismatches)}")
    for sid, ours, theirs in name_mismatches:
        print(f"  {sid}: species.json={ours!r} pokeruby={theirs!r}")

    print(f"\nType mismatches: {len(type_mismatches)}")
    for sid, name, ours, theirs in type_mismatches:
        print(f"  {sid} {name}: species_info={ours} pokeruby={theirs}")

    print(f"\nAbility mismatches: {len(ability_mismatches)}")
    for sid, name, ours, theirs in ability_mismatches:
        print(f"  {sid} {name}: species_info={ours} pokeruby={theirs}")

    print(f"\nGrowth rate mismatches: {len(growth_mismatches)}")
    for sid, name, ours, theirs in growth_mismatches:
        print(f"  {sid} {name}: growth_rates={ours!r} pokeruby={theirs!r}")

    if missing_from_pokeruby:
        print(f"\nIds in species.json with no pokeruby base_stats entry "
              f"(likely unused/vestigial slots): {len(missing_from_pokeruby)}")
        for sid, name in missing_from_pokeruby:
            print(f"  {sid} {name}")

    if fix:
        changed = 0
        for sid, name, ours, theirs in type_mismatches:
            species_info.setdefault(str(sid), {})["types"] = theirs
            changed += 1
        for sid, name, ours, theirs in ability_mismatches:
            species_info.setdefault(str(sid), {})["abilities"] = theirs
            changed += 1
        for sid, name, ours, theirs in growth_mismatches:
            growth_rates[str(sid)] = theirs
            changed += 1

        with open(_DATA_DIR / "species_info.json", "w", encoding="utf-8") as f:
            json.dump(species_info, f, indent=2, ensure_ascii=False)
            f.write("\n")
        with open(_DATA_DIR / "growth_rates.json", "w", encoding="utf-8") as f:
            json.dump(growth_rates, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"\nApplied {changed} field-level fixes to species_info.json / "
              f"growth_rates.json (species.json names were NOT rewritten).")


if __name__ == "__main__":
    main()
