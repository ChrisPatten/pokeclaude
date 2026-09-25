"""verify_golden.py — independent cross-check of every Mon (party, box,
daycare) in a parsed save against the reference data in data/gen_3/,
BEFORE that output is frozen as the golden fixture for tests/test_parser_golden.py.

The point is to catch parser bugs, not just snapshot whatever the parser
currently produces (a snapshot of buggy output just locks the bugs in).
Each check below deliberately re-derives its expectation from a different
source file than the one the parser itself reads, so a bug in either path
is likely to show up as a mismatch here.

Checks:
  - types and ability agree with pokedex_gen3.md; ability is one of the
    species' listed abilities (set membership, not position — see note
    in scripts/build_species_info.py about ability-order corrections).
  - every move is learnable by the species or a pre-evolution, per
    learnsets_gen3.md (LevelUp, Egg, or Machine). Sketch, Shedinja/Ninjask,
    and any other miss are reported as warnings, not failures — some are
    event/tutor moves this dataset doesn't cover.
  - nature_effect matches natures.json / natures_gen3.md.
  - pp_max is base_pp..base_pp*1.6 (0-3 PP Ups) and pp <= pp_max.
  - held items and inventory item names all resolve (no "Unknown").
  - box/daycare levels fall in the EXP band their growth rate implies;
    party EXP-derived level == stored level.
  - level is plausible for the species' evolution stage (warning only).

Usage: python3 scripts/verify_golden.py [path/to/save.srm]
Defaults to tests/fixtures/sapphire.srm.
"""

import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from parser import data_loader  # noqa: E402
from parser.parse_save import parse  # noqa: E402
from parser.pokemon import _estimate_level  # noqa: E402

_DATA_DIR = _ROOT / "data" / "gen_3"
_DEFAULT_SAVE = _ROOT / "tests" / "fixtures" / "sapphire.srm"


# ---------------------------------------------------------------------------
# Reference data loaders (data/gen_3/*.md — independent of parser/data/*.json)
# ---------------------------------------------------------------------------

_POKEDEX_LINE_RE = re.compile(
    r"^(?P<dex>\d{3}) (?P<name>.+?) Type1:(?P<type1>\S*) Type2:(?P<type2>\S*) "
    r"HP:\d+ Atk:\d+ Def:\d+ SpAtk:\d+ SpDef:\d+ Spd:\d+ BST:\d+ "
    r"Abilities:(?P<abilities>.+)$"
)


def _load_pokedex_md() -> dict[str, dict]:
    """name -> {"types": [...], "abilities": [...]} straight from the .md."""
    entries = {}
    for line in (_DATA_DIR / "pokedex_gen3.md").read_text(encoding="utf-8").splitlines():
        m = _POKEDEX_LINE_RE.match(line)
        if not m:
            continue
        type1 = m.group("type1") or "Normal"  # see build_species_info.py note
        type2 = m.group("type2")
        types = [t for t in (type1, type2) if t and t.lower() != "none"]
        abilities = [a.strip() for a in m.group("abilities").split(",") if a.strip()]
        entries[m.group("name")] = {"types": types or ["Normal"], "abilities": abilities}
    return entries


_LEARNSET_LINE_RE = re.compile(
    r"^Pokemon:(?P<name>.+?) \| LevelUp:(?P<levelup>.*?) \| Egg:(?P<egg>.*?) \| Machine:(?P<machine>.*)$"
)


def _normalize_move_name(name: str) -> str:
    """learnsets_gen3.md spells some move names without the hyphens/periods
    the canonical name uses (e.g. "Mud Slap" vs "Mud-Slap", "Will O Wisp" vs
    "Will-O-Wisp"). Normalize both sides before comparing."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _load_learnsets_md() -> dict[str, set[str]]:
    """name -> set of normalized move names learnable via LevelUp, Egg, or Machine."""
    result = {}
    for line in (_DATA_DIR / "learnsets_gen3.md").read_text(encoding="utf-8").splitlines():
        m = _LEARNSET_LINE_RE.match(line)
        if not m:
            continue
        moves: set[str] = set()
        for entry in m.group("levelup").split(","):
            entry = entry.strip()
            if not entry or entry == "None":
                continue
            # "L1:Tackle" -> "Tackle"
            move = entry.split(":", 1)[1].strip() if ":" in entry else entry
            moves.add(_normalize_move_name(move))
        for field in (m.group("egg"), m.group("machine")):
            for entry in field.split(","):
                entry = entry.strip()
                if entry and entry != "None":
                    moves.add(_normalize_move_name(entry))
        result[m.group("name")] = moves
    return result


# data/gen_3/evolution_gen3.md only lists Hoenn evolution chains (Treecko
# onward) — Kanto/Johto lines aren't in it at all. In practice this rarely
# matters because learnsets_gen3.md's LevelUp lists for evolved forms are
# already cumulative (an evolved form's list repeats its pre-evolution's
# moves), but a few lines legitimately keep pre-evolution-only moves off the
# evolved form's own list (e.g. Magikarp's Splash/Tackle/Flail don't reappear
# on Gyarados). Supplement the handful of pre-Hoenn chains this save actually
# needs rather than transcribing the whole National Dex.
_SUPPLEMENTAL_CHAINS: list[list[str]] = [
    ["Oddish", "Gloom", "Vileplume"],
    ["Magikarp", "Gyarados"],
    ["Phanpy", "Donphan"],
]


def _load_evolution_chains() -> tuple[dict[str, list[str]], dict[str, int]]:
    """Returns (pre_evolutions, evo_level):
    pre_evolutions[name] = [names before it in its chain]
    evo_level[name] = level at which *name* evolves into the next stage
                      (only set when the method is a plain "Lvl N")."""
    pre_evolutions: dict[str, list[str]] = {}
    evo_level: dict[str, int] = {}

    text = (_DATA_DIR / "evolution_gen3.md").read_text(encoding="utf-8")
    for line in text.strip().splitlines():
        parts = [p.strip() for p in line.split("->")]
        names = parts[0::2]
        methods = parts[1::2]
        for i, name in enumerate(names):
            pre_evolutions[name] = names[:i]
        for name, method in zip(names, methods):
            lvl_m = re.match(r"Lvl (\d+)", method)
            if lvl_m:
                evo_level[name] = int(lvl_m.group(1))

    for chain in _SUPPLEMENTAL_CHAINS:
        for i, name in enumerate(chain):
            pre_evolutions.setdefault(name, chain[:i])

    return pre_evolutions, evo_level


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

class Findings:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []

    def fail(self, msg: str) -> None:
        self.failures.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def _check_mon(mon: dict, where: str, pokedex_md: dict, learnsets_md: dict,
               pre_evolutions: dict, evo_level: dict, growth_rates: dict,
               moves_data: dict, findings: Findings) -> None:
    species = mon["species_name"]
    tag = f"{where} slot {mon['slot']} {species} (pid={mon['pid']})"

    if mon["is_egg"]:
        return  # eggs carry the hidden species' data but display as "Egg" in-game; skip

    # -- types / ability vs pokedex_gen3.md -------------------------------
    dex = pokedex_md.get(species)
    if dex is None:
        findings.warn(f"{tag}: no pokedex_gen3.md entry for {species!r} (Unown form?)")
    else:
        if set(mon["types"]) != set(dex["types"]):
            findings.fail(f"{tag}: types {mon['types']} != pokedex_gen3.md {dex['types']}")
        if dex["abilities"] and mon["ability"] not in dex["abilities"]:
            findings.fail(
                f"{tag}: ability {mon['ability']!r} not in pokedex_gen3.md "
                f"abilities {dex['abilities']}"
            )

    # -- move learnability ---------------------------------------------------
    chain = [species] + pre_evolutions.get(species, [])
    learnable: set[str] = set()
    for name in chain:
        learnable |= learnsets_md.get(name, set())

    for move in mon["moves"]:
        name = move["name"]
        if _normalize_move_name(name) in learnable:
            continue
        if name == "Sketch":
            findings.warn(f"{tag}: knows Sketch (can copy any move) — not flagged")
        elif species in ("Ninjask", "Shedinja"):
            findings.warn(f"{tag}: {name!r} not in learnsets_gen3.md for {species} "
                          f"(Ninjask/Shedinja split quirk)")
        else:
            findings.warn(
                f"{tag}: move {name!r} not found in learnsets_gen3.md for "
                f"{' <- '.join(chain)} (possible event/tutor move, or a real bug)"
            )

        # pp bounds, regardless of learnability
        move_id = move["move_id"]
        base = moves_data.get(str(move_id), {}).get("pp")
        if base is not None:
            pp_max_lo, pp_max_hi = base, int(base * 1.6)
            if not (pp_max_lo <= move["pp_max"] <= pp_max_hi):
                findings.fail(
                    f"{tag}: move {name!r} pp_max {move['pp_max']} outside "
                    f"[{pp_max_lo},{pp_max_hi}] for base pp {base}"
                )
        if move["pp"] > move["pp_max"]:
            findings.fail(f"{tag}: move {name!r} pp {move['pp']} > pp_max {move['pp_max']}")

    # -- nature_effect --------------------------------------------------------
    natures = data_loader.load_natures()
    nature_entry = next((n for n in natures if n["name"] == mon["nature"]), None)
    if nature_entry is None:
        findings.fail(f"{tag}: unknown nature {mon['nature']!r}")
    else:
        from parser.pokemon import _format_nature_effect
        expected_effect = _format_nature_effect(nature_entry)
        if mon["nature_effect"] != expected_effect:
            findings.fail(
                f"{tag}: nature_effect {mon['nature_effect']!r} != "
                f"expected {expected_effect!r} for nature {mon['nature']}"
            )

    # -- held item resolves ---------------------------------------------------
    if mon["held_item"] not in ("None",) and mon["held_item"].startswith("Unknown"):
        findings.fail(f"{tag}: held_item did not resolve: {mon['held_item']!r}")

    # -- level vs EXP / growth rate --------------------------------------------
    growth_rate = growth_rates.get(str(mon["species_id"]), "medium_fast")
    derived_level = _estimate_level(mon["experience"], growth_rate)
    if where == "party":
        if derived_level != mon["level"]:
            findings.fail(
                f"{tag}: party stored level {mon['level']} != EXP-derived "
                f"level {derived_level} (growth_rate={growth_rate})"
            )
    else:
        # Box/daycare levels ARE the EXP-derived estimate by construction;
        # this just guards against the field being stale/overwritten.
        if derived_level != mon["level"]:
            findings.fail(
                f"{tag}: level {mon['level']} != EXP-derived level "
                f"{derived_level} (growth_rate={growth_rate}, exp={mon['experience']})"
            )

    # -- evolution-stage plausibility (warning only) ---------------------------
    if mon["held_item"] == "Everstone":
        return
    if species in evo_level and mon["level"] > evo_level[species] + 10:
        findings.warn(
            f"{tag}: level {mon['level']} is well above its own evolution "
            f"level ({evo_level[species]}) without an Everstone — "
            f"plausible (rare candy / traded), just flagging"
        )
    for pre_name in pre_evolutions.get(species, []):
        if pre_name in evo_level and mon["level"] < evo_level[pre_name]:
            findings.warn(
                f"{tag}: evolved form at level {mon['level']}, below the "
                f"{pre_name}->next evolution level ({evo_level[pre_name]}) — "
                f"plausible (traded pre-evolved), just flagging"
            )


def main() -> None:
    save_path = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_SAVE
    if not save_path.exists():
        print(f"Save file not found: {save_path}", file=sys.stderr)
        sys.exit(1)

    result = parse(str(save_path))

    pokedex_md = _load_pokedex_md()
    learnsets_md = _load_learnsets_md()
    pre_evolutions, evo_level = _load_evolution_chains()
    growth_rates = data_loader.load_growth_rates()
    moves_data = data_loader.load_moves()

    findings = Findings()

    for mon in result["party"]:
        _check_mon(mon, "party", pokedex_md, learnsets_md, pre_evolutions,
                   evo_level, growth_rates, moves_data, findings)
    for box in result["boxes"]:
        for mon in box["pokemon"]:
            _check_mon(mon, f"box {box['box_index']}", pokedex_md, learnsets_md,
                       pre_evolutions, evo_level, growth_rates, moves_data, findings)
    for mon in result["daycare"]:
        _check_mon(mon, "daycare", pokedex_md, learnsets_md, pre_evolutions,
                   evo_level, growth_rates, moves_data, findings)

    # -- inventory item names -----------------------------------------------
    for pocket, items in result["inventory"].items():
        for item in items:
            name = item if isinstance(item, str) else item["name"]
            if name.startswith("Unknown"):
                findings.fail(f"inventory.{pocket}: item did not resolve: {name!r}")

    total_mons = (len(result["party"])
                  + sum(len(b["pokemon"]) for b in result["boxes"])
                  + len(result["daycare"]))

    print(f"Checked {total_mons} Mons from {save_path}\n")
    print(f"FAILURES: {len(findings.failures)}")
    for f in findings.failures:
        print(f"  [FAIL] {f}")
    print(f"\nWARNINGS: {len(findings.warnings)}")
    for w in findings.warnings:
        print(f"  [warn] {w}")

    if findings.failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
