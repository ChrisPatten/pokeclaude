"""build_gen1_data.py — generate all Gen 1 (Red/Blue) data from pret/pokered.

The pret/pokered decompilation builds a bit-identical copy of the retail
Red and Blue ROMs, so its data tables are the game's own data. This script
parses them and writes:

    parser/data/gen1/species.json    — internal species index -> {name, national_dex, types, growth_rate}
    parser/data/gen1/moves.json      — move id -> {name, type, pp, power, accuracy}
    parser/data/gen1/items.json      — item id -> display name (TMs/HMs as "TM01"/"HM01")
    parser/data/gen1/locations.json  — [{map_id, name}] for every map id

    data/gen_1/pokedex_gen1.md, moves_gen1.md, learnsets_gen1.md,
    tmhm_gen1.md, evolution_gen1.md, items_gen1.md, catch_locations_gen1.md,
    shops_gen1.md, type_chart_gen1.md, trainers_gen1.md

Every reference-file line is self-contained so a keyword grep returns
complete information. data/gen_1/red_blue.md (strategy, progression) is
hand-written and not touched by this script.

Usage:
    python3 scripts/build_gen1_data.py                    # clones pokered into scripts/cache/pokered
    python3 scripts/build_gen1_data.py --pokered PATH     # use an existing checkout

Move and species display names are taken from parser/data/moves.json and
parser/data/species_info.json (Gen 3 tables, same move ids and National
Dex numbers) so names stay consistent across generations.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import OrderedDict, defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_CACHE_DIR = Path(__file__).resolve().parent / "cache"
_PARSER_OUT = _ROOT / "parser" / "data" / "gen1"
_MD_OUT = _ROOT / "data" / "gen_1"
_POKERED_GIT = "https://github.com/pret/pokered"

# ---------------------------------------------------------------------------
# Static knowledge the decompilation encodes only in code, not data tables
# ---------------------------------------------------------------------------

TYPE_NAMES = {
    "NORMAL": "Normal", "FIGHTING": "Fighting", "FLYING": "Flying",
    "POISON": "Poison", "GROUND": "Ground", "ROCK": "Rock", "BIRD": "Bird",
    "BUG": "Bug", "GHOST": "Ghost", "FIRE": "Fire", "WATER": "Water",
    "GRASS": "Grass", "ELECTRIC": "Electric", "PSYCHIC_TYPE": "Psychic",
    "ICE": "Ice", "DRAGON": "Dragon",
}
TYPE_ORDER = ["Normal", "Fighting", "Flying", "Poison", "Ground", "Rock", "Bug",
              "Ghost", "Fire", "Water", "Grass", "Electric", "Psychic", "Ice", "Dragon"]
PHYSICAL_TYPES = {"Normal", "Fighting", "Flying", "Poison", "Ground", "Rock", "Bug", "Ghost"}

GROWTH_NAMES = {
    "GROWTH_MEDIUM_FAST": "medium_fast", "GROWTH_SLIGHTLY_FAST": "slightly_fast",
    "GROWTH_SLIGHTLY_SLOW": "slightly_slow", "GROWTH_MEDIUM_SLOW": "medium_slow",
    "GROWTH_FAST": "fast", "GROWTH_SLOW": "slow",
}

SPECIES_NAME_OVERRIDES = {29: "Nidoran♀", 32: "Nidoran♂", 83: "Farfetch'd", 122: "Mr. Mime"}

# Gen 1 move-effect descriptions. Chances are the game's own (engine/battle/effects.asm).
EFFECT_TEXT = {
    "NO_ADDITIONAL_EFFECT": "Damages the target.",
    "POISON_SIDE_EFFECT1": "20% chance to poison the target.",
    "POISON_SIDE_EFFECT2": "40% chance to poison the target.",
    "DRAIN_HP_EFFECT": "Heals the user by half the damage dealt.",
    "BURN_SIDE_EFFECT1": "10% chance to burn the target. Cannot burn Fire types.",
    "BURN_SIDE_EFFECT2": "30% chance to burn the target. Cannot burn Fire types.",
    "FREEZE_SIDE_EFFECT1": "10% chance to freeze the target. Frozen Pokemon never thaw naturally in Gen 1; only a Fire move hit or Haze cures it. Cannot freeze Ice types.",
    "FREEZE_SIDE_EFFECT2": "30% chance to freeze the target. Cannot freeze Ice types.",
    "PARALYZE_SIDE_EFFECT1": "10% chance to paralyze the target. Cannot paralyze a Pokemon sharing the move's type.",
    "PARALYZE_SIDE_EFFECT2": "30% chance to paralyze the target. Cannot paralyze a Pokemon sharing the move's type (Body Slam cannot paralyze Normal types).",
    "EXPLODE_EFFECT": "User faints. Halves the target's Defense during damage calculation.",
    "DREAM_EATER_EFFECT": "Only works on a sleeping target. Heals the user by half the damage dealt.",
    "MIRROR_MOVE_EFFECT": "Uses the last move the target used.",
    "ATTACK_UP1_EFFECT": "Raises the user's Attack by 1 stage.",
    "DEFENSE_UP1_EFFECT": "Raises the user's Defense by 1 stage.",
    "SPEED_UP1_EFFECT": "Raises the user's Speed by 1 stage.",
    "SPECIAL_UP1_EFFECT": "Raises the user's Special by 1 stage.",
    "ACCURACY_UP1_EFFECT": "Raises the user's accuracy by 1 stage.",
    "EVASION_UP1_EFFECT": "Raises the user's evasion by 1 stage.",
    "PAY_DAY_EFFECT": "Scatters money equal to 2x the user's level; collected after the battle.",
    "SWIFT_EFFECT": "Never misses (still fails against Fly/Dig).",
    "ATTACK_DOWN1_EFFECT": "Lowers the target's Attack by 1 stage.",
    "DEFENSE_DOWN1_EFFECT": "Lowers the target's Defense by 1 stage.",
    "SPEED_DOWN1_EFFECT": "Lowers the target's Speed by 1 stage.",
    "SPECIAL_DOWN1_EFFECT": "Lowers the target's Special by 1 stage.",
    "ACCURACY_DOWN1_EFFECT": "Lowers the target's accuracy by 1 stage.",
    "EVASION_DOWN1_EFFECT": "Lowers the target's evasion by 1 stage.",
    "CONVERSION_EFFECT": "Changes the user's types to match the target's.",
    "HAZE_EFFECT": "Resets all stat stages for both sides, cures the target's status (including freeze and sleep), and removes Reflect, Light Screen, Focus Energy, Leech Seed, confusion, and Mist.",
    "BIDE_EFFECT": "User waits 2-3 turns, then deals double the damage it took. Hits Ghost types.",
    "THRASH_PETAL_DANCE_EFFECT": "Attacks for 2-3 turns, then the user becomes confused.",
    "SWITCH_AND_TELEPORT_EFFECT": "Ends wild battles. Fails in trainer battles.",
    "TWO_TO_FIVE_ATTACKS_EFFECT": "Hits 2-5 times (37.5% 2, 37.5% 3, 12.5% 4, 12.5% 5). Damage is calculated once and repeated.",
    "FLINCH_SIDE_EFFECT1": "10% chance to make the target flinch.",
    "FLINCH_SIDE_EFFECT2": "30% chance to make the target flinch.",
    "SLEEP_EFFECT": "Puts the target to sleep for 1-7 turns. A Pokemon cannot attack on the turn it wakes up.",
    "OHKO_EFFECT": "One-hit KO. Fails if the target is faster than the user.",
    "CHARGE_EFFECT": "Charges on the first turn, attacks on the second.",
    "SUPER_FANG_EFFECT": "Deals damage equal to half the target's current HP. Hits Ghost types.",
    "TRAPPING_EFFECT": "Traps the target for 2-5 turns; the target cannot act at all while trapped. Damage per turn is fixed at the first hit.",
    "FLY_EFFECT": "User is semi-invulnerable on the first turn, attacks on the second.",
    "ATTACK_TWICE_EFFECT": "Hits twice.",
    "JUMP_KICK_EFFECT": "If it misses, the user takes 1 HP of damage.",
    "MIST_EFFECT": "Protects the user's stats from being lowered by the opponent's moves.",
    "FOCUS_ENERGY_EFFECT": "Bugged in Gen 1: divides the user's critical-hit rate by 4 instead of raising it.",
    "RECOIL_EFFECT": "User takes 1/4 of the damage dealt as recoil.",
    "CONFUSION_EFFECT": "Confuses the target.",
    "ATTACK_UP2_EFFECT": "Raises the user's Attack by 2 stages.",
    "DEFENSE_UP2_EFFECT": "Raises the user's Defense by 2 stages.",
    "SPEED_UP2_EFFECT": "Raises the user's Speed by 2 stages.",
    "SPECIAL_UP2_EFFECT": "Raises the user's Special by 2 stages (Special is both special offense and special defense in Gen 1).",
    "ACCURACY_UP2_EFFECT": "Raises the user's accuracy by 2 stages.",
    "EVASION_UP2_EFFECT": "Raises the user's evasion by 2 stages.",
    "HEAL_EFFECT": "Heals half the user's max HP. Fails if current HP is exactly 255 or 511 below max (Gen 1 bug).",
    "TRANSFORM_EFFECT": "User copies the target's species, types, stats (except HP), stat stages, and moves (5 PP each).",
    "ATTACK_DOWN2_EFFECT": "Lowers the target's Attack by 2 stages.",
    "DEFENSE_DOWN2_EFFECT": "Lowers the target's Defense by 2 stages.",
    "SPEED_DOWN2_EFFECT": "Lowers the target's Speed by 2 stages.",
    "SPECIAL_DOWN2_EFFECT": "Lowers the target's Special by 2 stages.",
    "ACCURACY_DOWN2_EFFECT": "Lowers the target's accuracy by 2 stages.",
    "EVASION_DOWN2_EFFECT": "Lowers the target's evasion by 2 stages.",
    "LIGHT_SCREEN_EFFECT": "Doubles the user's Special against special attacks until it switches out.",
    "REFLECT_EFFECT": "Doubles the user's Defense against physical attacks until it switches out.",
    "POISON_EFFECT": "Poisons the target.",
    "PARALYZE_EFFECT": "Paralyzes the target. Speed drops to 1/4; 25% chance each turn to be fully paralyzed.",
    "ATTACK_DOWN_SIDE_EFFECT": "33% chance to lower the target's Attack by 1 stage.",
    "DEFENSE_DOWN_SIDE_EFFECT": "33% chance to lower the target's Defense by 1 stage.",
    "SPEED_DOWN_SIDE_EFFECT": "33% chance to lower the target's Speed by 1 stage.",
    "SPECIAL_DOWN_SIDE_EFFECT": "33% chance to lower the target's Special by 1 stage.",
    "CONFUSION_SIDE_EFFECT": "10% chance to confuse the target.",
    "TWINEEDLE_EFFECT": "Hits twice; 20% chance to poison the target.",
    "SUBSTITUTE_EFFECT": "User spends 1/4 max HP to make a substitute that absorbs damage.",
    "HYPER_BEAM_EFFECT": "User must recharge next turn, unless this move KOs the target or breaks a substitute.",
    "RAGE_EFFECT": "User is locked into Rage until the battle ends; Attack rises by 1 stage each time it is hit.",
    "MIMIC_EFFECT": "Replaces Mimic with one of the target's moves for the battle.",
    "METRONOME_EFFECT": "Uses a random move.",
    "LEECH_SEED_EFFECT": "Drains 1/16 of the target's max HP each turn to the user. Grass types are immune.",
    "SPLASH_EFFECT": "Does nothing.",
    "DISABLE_EFFECT": "Disables one of the target's moves at random for 1-8 turns.",
}

# Moves whose behaviour is not fully described by their effect constant.
MOVE_NOTES = {
    "KARATE_CHOP": "High critical-hit ratio. Normal-type in Gen 1.",
    "RAZOR_LEAF": "High critical-hit ratio.",
    "CRABHAMMER": "High critical-hit ratio.",
    "SLASH": "High critical-hit ratio.",
    "SEISMIC_TOSS": "Deals damage equal to the user's level. Hits Ghost types.",
    "NIGHT_SHADE": "Deals damage equal to the user's level. Hits Normal types.",
    "SONICBOOM": "Always deals 20 HP of damage.",
    "DRAGON_RAGE": "Always deals 40 HP of damage.",
    "PSYWAVE": "Deals random damage from 1 to 1.5x the user's level.",
    "COUNTER": "Returns double the damage of the last Normal or Fighting move that hit the user.",
    "DIG": "User digs underground on the first turn, attacks on the second.",
    "SKY_ATTACK": "Charges on the first turn, attacks on the second.",
    "SKULL_BASH": "Charges on the first turn, attacks on the second.",
    "SOLARBEAM": "Charges on the first turn, attacks on the second.",
    "RAZOR_WIND": "Charges on the first turn, attacks on the second.",
    "BITE": "10% chance to flinch. Normal-type in Gen 1.",
    "GUST": "Normal-type in Gen 1.",
    "SAND_ATTACK": "Normal-type in Gen 1.",
    "STRUGGLE": "Used automatically when out of PP. Recoil 1/2 of damage dealt. Normal-type; does not hit Ghost types.",
    "REST": "User sleeps for 2 turns and fully restores HP and status.",
    "ROAR": "Ends wild battles. Fails in trainer battles.",
    "WHIRLWIND": "Ends wild battles. Fails in trainer battles.",
    "TELEPORT": "Ends wild battles. Fails in trainer battles. Field use: warps to the last Pokemon Center.",
    "AMNESIA": "Raises the user's Special by 2 stages; in Gen 1 this boosts both special attack and special defense.",
    "LICK": "30% chance to paralyze. Does not affect Psychic types (Gen 1 type chart: Ghost has no effect on Psychic).",
    "EXPLOSION": "User faints. Halves the target's Defense during damage calculation.",
    "SELFDESTRUCT": "User faints. Halves the target's Defense during damage calculation.",
    "HI_JUMP_KICK": "If it misses, the user takes 1 HP of damage.",
    "JUMP_KICK": "If it misses, the user takes 1 HP of damage.",
    "BLIZZARD": "10% chance to freeze. 90% accuracy in Gen 1.",
    "TOXIC": "Badly poisons the target. Damage grows each turn; Leech Seed stacks with the counter.",
    "PSYCHIC_M": "33% chance to lower the target's Special by 1 stage.",
    "HYPER_BEAM": "User must recharge next turn, unless this move KOs the target or breaks a substitute.",
}

ITEM_DESCRIPTIONS = {
    "MASTER_BALL": "Catches any wild Pokemon without fail", "ULTRA_BALL": "Ball with high catch rate",
    "GREAT_BALL": "Ball with good catch rate", "POKE_BALL": "Standard ball", "TOWN_MAP": "Shows the Kanto map",
    "BICYCLE": "Travels twice as fast as walking", "SURFBOARD": "Unused item", "SAFARI_BALL": "Only usable in the Safari Zone",
    "POKEDEX": "Records Pokemon data", "MOON_STONE": "Evolves Nidorina, Nidorino, Clefairy, Jigglypuff",
    "ANTIDOTE": "Cures poison", "BURN_HEAL": "Cures burn", "ICE_HEAL": "Cures freeze", "AWAKENING": "Cures sleep",
    "PARLYZ_HEAL": "Cures paralysis", "FULL_RESTORE": "Fully restores HP and cures status", "MAX_POTION": "Fully restores HP",
    "HYPER_POTION": "Restores 200 HP", "SUPER_POTION": "Restores 50 HP", "POTION": "Restores 20 HP",
    "BOULDERBADGE": "Badge", "CASCADEBADGE": "Badge", "THUNDERBADGE": "Badge", "RAINBOWBADGE": "Badge",
    "SOULBADGE": "Badge", "MARSHBADGE": "Badge", "VOLCANOBADGE": "Badge", "EARTHBADGE": "Badge",
    "ESCAPE_ROPE": "Escapes from caves and dungeons", "REPEL": "Repels weaker wild Pokemon for 100 steps",
    "OLD_AMBER": "Revived into Aerodactyl at the Cinnabar Lab", "FIRE_STONE": "Evolves Vulpix, Growlithe, Eevee",
    "THUNDER_STONE": "Evolves Pikachu, Eevee", "WATER_STONE": "Evolves Poliwhirl, Shellder, Staryu, Eevee",
    "HP_UP": "Raises HP stat experience", "PROTEIN": "Raises Attack stat experience", "IRON": "Raises Defense stat experience",
    "CARBOS": "Raises Speed stat experience", "CALCIUM": "Raises Special stat experience",
    "RARE_CANDY": "Raises a Pokemon's level by 1", "DOME_FOSSIL": "Revived into Kabuto at the Cinnabar Lab",
    "HELIX_FOSSIL": "Revived into Omanyte at the Cinnabar Lab", "SECRET_KEY": "Opens the Cinnabar Gym",
    "UNUSED_ITEM": "Unused item", "BIKE_VOUCHER": "Exchange for a Bicycle at the Cerulean Bike Shop",
    "X_ACCURACY": "Raises accuracy in battle; in Gen 1 makes one-hit KO moves always hit a slower target",
    "LEAF_STONE": "Evolves Gloom, Weepinbell, Exeggcute", "CARD_KEY": "Opens locked doors in Silph Co.",
    "NUGGET": "Sell for 5000", "PP_UP_2": "Unused duplicate of PP Up", "POKE_DOLL": "Guaranteed escape from wild battles; bypasses the Pokemon Tower ghost",
    "FULL_HEAL": "Cures all status", "REVIVE": "Revives a fainted Pokemon with half HP", "MAX_REVIVE": "Revives a fainted Pokemon with full HP",
    "GUARD_SPEC": "Prevents stat reduction in battle", "SUPER_REPEL": "Repels weaker wild Pokemon for 200 steps",
    "MAX_REPEL": "Repels weaker wild Pokemon for 250 steps", "DIRE_HIT": "Bugged in Gen 1: lowers critical-hit rate like Focus Energy",
    "COIN": "Game Corner coin", "FRESH_WATER": "Restores 50 HP", "SODA_POP": "Restores 60 HP", "LEMONADE": "Restores 80 HP",
    "S_S_TICKET": "Boards the S.S. Anne", "GOLD_TEETH": "Return to the Safari Zone Warden for HM04 Strength",
    "X_ATTACK": "Raises Attack in battle", "X_DEFEND": "Raises Defense in battle", "X_SPEED": "Raises Speed in battle",
    "X_SPECIAL": "Raises Special in battle", "COIN_CASE": "Holds up to 9999 Game Corner coins",
    "OAKS_PARCEL": "Deliver to Professor Oak", "ITEMFINDER": "Detects hidden items nearby",
    "SILPH_SCOPE": "Identifies ghosts in Pokemon Tower", "POKE_FLUTE": "Wakes sleeping Pokemon, including the Snorlax blocking Routes 12 and 16",
    "LIFT_KEY": "Operates the Rocket Hideout elevator", "EXP_ALL": "Splits battle experience among the whole party",
    "OLD_ROD": "Fishes up Magikarp (Lv5)", "GOOD_ROD": "Fishes up Goldeen or Poliwag (Lv10)",
    "SUPER_ROD": "Fishes up area-specific Pokemon", "PP_UP": "Raises a move's max PP by 1/5 of base",
    "ETHER": "Restores 10 PP of one move", "MAX_ETHER": "Fully restores PP of one move",
    "ELIXER": "Restores 10 PP of all moves", "MAX_ELIXER": "Fully restores PP of all moves",
}

ITEM_NAME_OVERRIDES = {
    "POKE_BALL": "Poké Ball", "POKEDEX": "Pokédex", "POKE_DOLL": "Poké Doll", "POKE_FLUTE": "Poké Flute",
    "SURFBOARD": "Surfboard (unused)", "S_S_TICKET": "S.S. Ticket", "HP_UP": "HP Up", "PP_UP": "PP Up",
    "PP_UP_2": "PP Up (unused)", "EXP_ALL": "Exp. All", "GUARD_SPEC": "Guard Spec.", "OAKS_PARCEL": "Oak's Parcel",
    "X_ACCURACY": "X Accuracy", "X_ATTACK": "X Attack", "X_DEFEND": "X Defend", "X_SPEED": "X Speed",
    "X_SPECIAL": "X Special", "BOULDERBADGE": "Boulder Badge", "CASCADEBADGE": "Cascade Badge",
    "THUNDERBADGE": "Thunder Badge", "RAINBOWBADGE": "Rainbow Badge", "SOULBADGE": "Soul Badge",
    "MARSHBADGE": "Marsh Badge", "VOLCANOBADGE": "Volcano Badge", "EARTHBADGE": "Earth Badge",
    "PARLYZ_HEAL": "Parlyz Heal", "UNUSED_ITEM": "Unused Item",
}

EXTRA_ITEM_SOURCES = {
    "POKEDEX": "Oak's Lab (gift, after delivering Oak's Parcel)",
    "SAFARI_BALL": "Safari Zone Gate (30 given on entry, ¥500)",
    "FRESH_WATER": "Celadon Dept. Store Roof (vending machine)",
    "SODA_POP": "Celadon Dept. Store Roof (vending machine)",
    "LEMONADE": "Celadon Dept. Store Roof (vending machine)",
    "COIN": "Celadon Game Corner (50 for ¥1000; hidden coins on the floor)",
}

KEY_ITEMS = {
    "TOWN_MAP", "BICYCLE", "SURFBOARD", "POKEDEX", "OLD_AMBER", "DOME_FOSSIL", "HELIX_FOSSIL",
    "SECRET_KEY", "BIKE_VOUCHER", "CARD_KEY", "S_S_TICKET", "GOLD_TEETH", "COIN_CASE",
    "OAKS_PARCEL", "ITEMFINDER", "SILPH_SCOPE", "POKE_FLUTE", "LIFT_KEY", "EXP_ALL",
    "OLD_ROD", "GOOD_ROD", "SUPER_ROD",
}

MAP_WORD_OVERRIDES = {
    "MT": "Mt.", "SS": "S.S.", "POKECENTER": "Pokémon Center", "POKEMON": "Pokémon", "REDS": "Red's",
    "BLUES": "Blue's", "OAKS": "Oak's", "MR": "Mr.", "FUJIS": "Fuji's", "BILLS": "Bill's",
    "LORELEIS": "Lorelei's", "BRUNOS": "Bruno's", "AGATHAS": "Agatha's", "LANCES": "Lance's",
    "CHAMPIONS": "Champion's", "CAPTAINS": "Captain's", "WARDENS": "Warden's", "COPYCATS": "Copycat's",
    "PSYCHICS": "Psychic's", "GRANDPAS": "Grandpa's", "RATERS": "Rater's", "DIGLETTS": "Diglett's",
    "CO": "Co.",
}

MAP_NAME_OVERRIDES = {
    "GAME_CORNER": "Celadon Game Corner", "GAME_CORNER_PRIZE_ROOM": "Celadon Game Corner Prize Room",
    "DAYCARE": "Route 5 Day Care", "BIKE_SHOP": "Cerulean Bike Shop", "FIGHTING_DOJO": "Saffron Fighting Dojo",
    "MUSEUM_1F": "Pewter Museum 1F", "MUSEUM_2F": "Pewter Museum 2F", "POKEMON_FAN_CLUB": "Vermilion Pokémon Fan Club",
    "NAME_RATERS_HOUSE": "Lavender Name Rater's House", "TRADE_CENTER": "Cable Club Trade Center",
    "COLOSSEUM": "Cable Club Colosseum", "MR_FUJIS_HOUSE": "Lavender Mr. Fuji's House",
    "MR_PSYCHICS_HOUSE": "Saffron Mr. Psychic's House", "COPYCATS_HOUSE_1F": "Saffron Copycat's House 1F",
    "COPYCATS_HOUSE_2F": "Saffron Copycat's House 2F", "BILLS_HOUSE": "Bill's House (Route 25)",
    "WARDENS_HOUSE": "Fuchsia Warden's House", "SEA_ROUTES": "Routes 19-20",
    "POWER_PLANT": "Power Plant", "HALL_OF_FAME": "Hall of Fame",
    "UNDERGROUND_PATH_NORTH_SOUTH": "Underground Path (Routes 5-6)",
    "UNDERGROUND_PATH_WEST_EAST": "Underground Path (Routes 7-8)",
    "UNDERGROUND_PATH_ROUTE_5": "Underground Path Entrance (Route 5)",
    "UNDERGROUND_PATH_ROUTE_6": "Underground Path Entrance (Route 6)",
    "UNDERGROUND_PATH_ROUTE_7": "Underground Path Entrance (Route 7)",
    "UNDERGROUND_PATH_ROUTE_8": "Underground Path Entrance (Route 8)",
    "MT_MOON_POKECENTER": "Mt. Moon Pokémon Center (Route 4)",
}

GYMS = [
    # (leader, parties label, gym map, badge, type, lone-move index)
    ("Brock", "BrockData", "PEWTER_GYM", "Boulder Badge", "Rock", 1),
    ("Misty", "MistyData", "CERULEAN_GYM", "Cascade Badge", "Water", 2),
    ("Lt. Surge", "LtSurgeData", "VERMILION_GYM", "Thunder Badge", "Electric", 3),
    ("Erika", "ErikaData", "CELADON_GYM", "Rainbow Badge", "Grass", 4),
    ("Koga", "KogaData", "FUCHSIA_GYM", "Soul Badge", "Poison", 5),
    ("Sabrina", "SabrinaData", "SAFFRON_GYM", "Marsh Badge", "Psychic", 6),
    ("Blaine", "BlaineData", "CINNABAR_GYM", "Volcano Badge", "Fire", 7),
    ("Giovanni", "GiovanniData", "VIRIDIAN_GYM", "Earth Badge", "Ground", 8),
]
ELITE_FOUR = [
    ("Lorelei", "LoreleiData", "LORELEI"), ("Bruno", "BrunoData", "BRUNO"),
    ("Agatha", "AgathaData", "AGATHA"), ("Lance", "LanceData", "LANCE"),
]

# ---------------------------------------------------------------------------
# Generic asm helpers
# ---------------------------------------------------------------------------


def _strip(line: str) -> str:
    return line.split(";", 1)[0].strip()


def _args(rest: str) -> list[str]:
    return [a.strip() for a in rest.split(",") if a.strip()]


def _title(token: str) -> str:
    return " ".join(w.capitalize() for w in token.split("_"))


def _num(tok: str) -> int:
    tok = tok.strip()
    if tok.startswith("$"):
        return int(tok[1:], 16)
    return int(tok)


def _pascal(token: str) -> str:
    """ROUTE_2_GATE -> Route2Gate, MT_MOON_1F -> MtMoon1F (pokered file naming)."""
    return "".join(p if p[:1].isdigit() else p.capitalize() for p in token.split("_"))


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def _versioned_lines(text: str):
    """Yield (version, stripped_line) with version in {None, 'red', 'blue'}
    tracking IF DEF(_RED)/IF DEF(_BLUE) ... ENDC blocks."""
    version = None
    for raw in text.splitlines():
        line = _strip(raw)
        if not line:
            continue
        if line.startswith("IF DEF(_RED)"):
            version = "red"
            continue
        if line.startswith("IF DEF(_BLUE)"):
            version = "blue"
            continue
        if line.startswith("ELSE") and version:
            version = "blue" if version == "red" else "red"
            continue
        if line.startswith("ENDC"):
            version = None
            continue
        yield version, line


# ---------------------------------------------------------------------------
# Loading pokered
# ---------------------------------------------------------------------------


class Pokered:
    def __init__(self, root: Path):
        self.root = root
        self._load_constants()
        self._load_moves()
        self._load_species()
        self._load_evos_moves()
        self._load_items()
        self._load_maps()

    # -- constants -----------------------------------------------------
    def _const_list(self, rel: str, macro: str = "const") -> dict[str, int]:
        out: dict[str, int] = {}
        value = 0
        for line in (_strip(l) for l in _read(self.root, rel).splitlines()):
            if line.startswith("const_def"):
                parts = line.split()
                value = _num(parts[1]) if len(parts) > 1 else 0
            elif line.startswith("const_next"):
                value = _num(line.split()[1])
            elif line.startswith("const_skip"):
                parts = line.split()
                value += _num(parts[1]) if len(parts) > 1 else 1
            elif line.startswith(macro + " "):
                name = _args(line[len(macro):])[0]
                out[name] = value
                value += 1
        return out

    def _load_constants(self) -> None:
        self.species_ids = self._const_list("constants/pokemon_constants.asm")
        self.dex_ids = self._const_list("constants/pokedex_constants.asm")
        self.move_ids = self._const_list("constants/move_constants.asm")
        self.type_ids = self._const_list("constants/type_constants.asm")
        self.map_ids = self._const_list("constants/map_constants.asm", "map_const")
        self.trainer_class_ids = self._const_list("constants/trainer_constants.asm", "trainer_const")

    # -- moves ------------------------------------------------------------
    def _load_moves(self) -> None:
        gen3_names = json.loads((_ROOT / "parser/data/moves.json").read_text(encoding="utf-8"))
        self.moves: dict[str, dict] = OrderedDict()
        for line in (_strip(l) for l in _read(self.root, "data/moves/moves.asm").splitlines()):
            if not line.startswith("move "):
                continue
            const, effect, power, mtype, acc, pp = _args(line[5:])
            mid = self.move_ids[const]
            self.moves[const] = {
                "id": mid,
                "const": const,
                "name": gen3_names[str(mid)]["name"],
                "effect": effect,
                "power": _num(power),
                "type": TYPE_NAMES[mtype],
                "accuracy": _num(acc.replace("percent", "")),
                "pp": _num(pp),
            }
        self.move_by_id = {m["id"]: m for m in self.moves.values()}

    def move_name(self, const: str) -> str:
        return self.moves[const]["name"]

    # -- species ----------------------------------------------------------
    def _load_species(self) -> None:
        gen3 = json.loads((_ROOT / "parser/data/species_info.json").read_text(encoding="utf-8"))
        name_by_dex = {v["national_dex"]: v["name"] for v in gen3.values()}
        name_by_dex.update(SPECIES_NAME_OVERRIDES)

        # TM/HM number order from item constants
        self.tm_moves: list[str] = []
        self.hm_moves: list[str] = []
        for line in (_strip(l) for l in _read(self.root, "constants/item_constants.asm").splitlines()):
            if line.startswith("add_tm "):
                self.tm_moves.append(line.split()[1])
            elif line.startswith("add_hm "):
                self.hm_moves.append(line.split()[1])

        self.base: dict[int, dict] = {}  # dex number -> base data
        files = sorted((self.root / "data/pokemon/base_stats").glob("*.asm"))
        for path in files:
            text = path.read_text(encoding="utf-8")
            dbs = []
            tmhm: list[str] = []
            in_tmhm = False
            for raw in text.splitlines():
                line = _strip(raw)
                if not line:
                    continue
                if line.startswith("tmhm "):
                    in_tmhm = True
                    line = line[5:]
                if in_tmhm:
                    # "UNUSED" is a padding flag bit in Mew's list, not a machine
                    tmhm.extend(a for a in _args(line.rstrip("\\")) if a not in ("\\", "UNUSED"))
                    in_tmhm = line.endswith("\\")
                    continue
                if line.startswith("db "):
                    dbs.append(_args(line[3:]))
            dex_const = dbs[0][0]
            dex = self.dex_ids[dex_const]
            hp, atk, df, spd, spc = (_num(x) for x in dbs[1])
            t1, t2 = (TYPE_NAMES[t] for t in dbs[2])
            self.base[dex] = {
                "dex": dex,
                "name": name_by_dex[dex],
                "const": dex_const[4:],
                "stats": {"hp": hp, "atk": atk, "def": df, "spd": spd, "spc": spc},
                "types": [t1] if t1 == t2 else [t1, t2],
                "catch_rate": _num(dbs[3][0]),
                "base_exp": _num(dbs[4][0]),
                "start_moves": [m for m in dbs[5] if m != "NO_MOVE"],
                "growth": GROWTH_NAMES[dbs[6][0]],
                "tmhm": tmhm,
            }

        # internal index -> dex number (dex_order.asm is indexed by internal id - 1)
        self.internal_to_dex: dict[int, int] = {}
        idx = 1
        for line in (_strip(l) for l in _read(self.root, "data/pokemon/dex_order.asm").splitlines()):
            if line.startswith("db "):
                tok = line[3:].strip()
                dex = 0 if tok == "0" else self.dex_ids[tok]
                if dex:
                    self.internal_to_dex[idx] = dex
                idx += 1
        self.const_to_dex = {c: self.internal_to_dex[i] for c, i in self.species_ids.items()
                             if i in self.internal_to_dex}

    def mon(self, const: str) -> dict:
        return self.base[self.const_to_dex[const]]

    # -- evolutions & learnsets -----------------------------------------
    def _load_evos_moves(self) -> None:
        text = _read(self.root, "data/pokemon/evos_moves.asm")
        labels: list[str] = []
        for line in (_strip(l) for l in text.splitlines()):
            if line.startswith("dw ") and line.endswith("EvosMoves"):
                labels.append(line[3:].strip())
        blocks: dict[str, list[list[str]]] = {}
        current = None
        for line in (_strip(l) for l in text.splitlines()):
            m = re.match(r"^(\w+EvosMoves):$", line)
            if m:
                current = m.group(1)
                blocks[current] = []
            elif current and line.startswith("db "):
                blocks[current].append(_args(line[3:]))
        for dex, base in self.base.items():
            base["evolutions"] = []
            base["learnset"] = []
        for internal_id, label in enumerate(labels, start=1):
            dex = self.internal_to_dex.get(internal_id)
            if not dex:
                continue
            rows = blocks[label]
            i = 0
            while rows[i] != ["0"]:
                row = rows[i]
                if row[0] == "EVOLVE_LEVEL":
                    self.base[dex]["evolutions"].append(("level", _num(row[1]), row[2]))
                elif row[0] == "EVOLVE_ITEM":
                    self.base[dex]["evolutions"].append(("item", row[1], row[3]))
                elif row[0] == "EVOLVE_TRADE":
                    self.base[dex]["evolutions"].append(("trade", None, row[2]))
                i += 1
            for row in rows[i + 1:]:
                if row == ["0"]:
                    break
                self.base[dex]["learnset"].append((_num(row[0]), row[1]))

    def moves_at_level(self, const: str, level: int) -> list[str]:
        """Replicates WriteMonMoves: the moveset a trainer/wild mon has at *level*."""
        mon = self.mon(const)
        moves = list(mon["start_moves"])
        for lv, move in mon["learnset"]:
            if lv > level:
                break
            if move in moves:
                continue
            if len(moves) == 4:
                moves.pop(0)
            moves.append(move)
        return moves

    # -- items ------------------------------------------------------------
    def _load_items(self) -> None:
        consts = self._const_list("constants/item_constants.asm")
        # add_hm / add_tm create consts implicitly; rebuild them
        hm_start = 0xC4
        for i, mv in enumerate(self.hm_moves):
            consts[f"HM_{mv}"] = hm_start + i
        for i, mv in enumerate(self.tm_moves):
            consts[f"TM_{mv}"] = hm_start + len(self.hm_moves) + i
        self.item_ids = consts

        prices: list[int] = []
        for line in (_strip(l) for l in _read(self.root, "data/items/prices.asm").splitlines()):
            if line.startswith("bcd3 "):
                prices.append(_num(line[5:]))
        tm_prices: list[int] = []
        for line in (_strip(l) for l in _read(self.root, "data/items/tm_prices.asm").splitlines()):
            if line.startswith("nybble "):
                tm_prices.append(_num(line[7:]) * 1000)

        self.items: dict[str, dict] = OrderedDict()
        for const, iid in sorted(consts.items(), key=lambda kv: kv[1]):
            if iid == 0 or const.startswith("FLOOR_") or const == "NO_ITEM":
                continue
            if const.startswith("HM_"):
                n = iid - hm_start + 1
                name, price = f"HM{n:02d}", 0
            elif const.startswith("TM_"):
                n = iid - hm_start - len(self.hm_moves) + 1
                name, price = f"TM{n:02d}", tm_prices[n - 1]
            elif iid <= len(prices):
                name = "Unused Item" if const.startswith("ITEM_") else ITEM_NAME_OVERRIDES.get(const, _title(const))
                price = prices[iid - 1]
            else:
                continue
            self.items[const] = {"id": iid, "const": const, "name": name, "price": price}

    def item_name(self, const: str) -> str:
        return self.items[const]["name"]

    def item_label(self, const: str) -> str:
        """TM/HM items get their move appended: 'TM28 (Dig)'."""
        if const.startswith(("TM_", "HM_")):
            return f"{self.items[const]['name']} ({self.move_name(const[3:])})"
        return self.item_name(const)

    # -- maps ---------------------------------------------------------------
    def _load_maps(self) -> None:
        self.map_names: dict[str, str] = {}
        for const in self.map_ids:
            self.map_names[const] = self.pretty_map(const)
        # pokered file stem (PascalCase) -> map const
        self.map_by_stem = {_norm(_pascal(c)): c for c in self.map_ids}

    @staticmethod
    def pretty_map(const: str) -> str:
        if const in MAP_NAME_OVERRIDES:
            return MAP_NAME_OVERRIDES[const]
        if const.startswith("UNUSED_MAP"):
            return f"Unused Map {const.rsplit('_', 1)[1]}"
        if const.startswith("CELADON_MART"):
            rest = const[len("CELADON_MART"):].strip("_")
            return f"Celadon Dept. Store {rest.replace('_', ' ').title()}" if rest else "Celadon Dept. Store"
        copy = const.endswith("_COPY")
        if copy:
            const = const[:-5]
        words = []
        for w in const.split("_"):
            if w in MAP_WORD_OVERRIDES:
                words.append(MAP_WORD_OVERRIDES[w])
            elif re.fullmatch(r"B?\d+F", w):
                words.append(w)
            else:
                words.append(w.capitalize())
        name = " ".join(words)
        if const.endswith("_MART"):
            name = name[: -len("Mart")] + "Poké Mart"
        return name + (" (duplicate)" if copy else "")

    def map_from_stem(self, stem: str) -> str | None:
        return self.map_by_stem.get(_norm(stem))


# ---------------------------------------------------------------------------
# Derived data: where things are
# ---------------------------------------------------------------------------


def _collect_item_sources(pr: Pokered) -> dict[str, list[str]]:
    sources: dict[str, list[str]] = defaultdict(list)

    def add(const: str, where: str) -> None:
        if where not in sources[const]:
            sources[const].append(where)

    # Visible item balls
    for path in sorted((pr.root / "data/maps/objects").glob("*.asm")):
        map_const = pr.map_from_stem(path.stem)
        if not map_const:
            continue
        for line in (_strip(l) for l in path.read_text(encoding="utf-8").splitlines()):
            if line.startswith("object_event") and "SPRITE_POKE_BALL" in line:
                a = _args(line[len("object_event"):])
                if len(a) == 7 and a[6] in pr.items:
                    add(a[6], pr.map_names[map_const])
    # Hidden items
    current = None
    for line in (_strip(l) for l in _read(pr.root, "data/events/hidden_events.asm").splitlines()):
        if line.startswith("hidden_events_for "):
            current = line.split()[1]
        elif line.startswith("hidden_event ") and "HiddenItems" in line and current:
            item = _args(line[len("hidden_event"):])[3]
            if item in pr.items and not current.startswith("UNUSED"):
                add(item, f"{pr.map_names[current]} (hidden)")
    # Scripted gifts: "lb bc, ITEM, qty" feeds GiveItem. ("ld b, ITEM" is an
    # IsItemInBag check, not a gift, so it is deliberately not matched.)
    for path in sorted((pr.root / "scripts").glob("*.asm")):
        map_const = pr.map_from_stem(path.stem)
        if not map_const:
            continue
        where = pr.map_names[map_const]
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"lb bc,\s*([A-Z0-9_]+),", text):
            const = m.group(1)
            if const in pr.items and const not in pr.species_ids:
                add(const, f"{where} (gift)")
        if "OaksAide" in text:
            for m in re.finditer(r"ld a,\s*([A-Z0-9_]+)\s*$", text, re.MULTILINE):
                if m.group(1) in pr.items:
                    need = re.search(r"ld a,\s*(\d+)\s*\n\s*ldh? \[hOaksAideRequirement\]", text)
                    req = f", requires {need.group(1)} species caught" if need else ""
                    add(m.group(1), f"{where} (Oak's aide gift{req})")
    # Marts
    for mart, items in _collect_marts(pr).items():
        for const in items:
            add(const, f"{mart} (buy)")
    # Game Corner prizes
    for const, cost in _collect_prizes(pr)["tms"]:
        add(const, f"Celadon Game Corner Prize Room ({cost} coins)")
    # Handed out by engine code rather than map scripts or data tables
    for const, where in EXTRA_ITEM_SOURCES.items():
        add(const, where)
    return sources


def _collect_marts(pr: Pokered) -> dict[str, list[str]]:
    marts: dict[str, list[str]] = OrderedDict()
    label = None
    for line in (_strip(l) for l in _read(pr.root, "data/items/marts.asm").splitlines()):
        m = re.match(r"^(\w+?)Clerk\d?Text::?$", line)
        if m:
            label = m.group(1)
            continue
        if line.startswith("script_mart") and label:
            if label.startswith("Unused"):
                label = None
                continue
            stem = label
            map_const = pr.map_from_stem(stem)
            name = pr.map_names[map_const] if map_const else _title(stem)
            key = name
            if key in marts:
                key = f"{name} (counter 2)"
            marts[key] = _args(line[len("script_mart"):])
            label = None
    return marts


def _collect_prizes(pr: Pokered) -> dict:
    text = _read(pr.root, "data/events/prizes.asm")
    sections: dict[str, list[tuple[str | None, object]]] = defaultdict(list)
    current = None
    for version, line in _versioned_lines(text):
        m = re.match(r"^(PrizeMenu\w+):$", line)
        if m:
            current = m.group(1)
            continue
        if not current:
            continue
        if line.startswith("db ") and line != 'db "@"':
            sections[current].append((version, line[3:].strip()))
        elif line.startswith("bcd2 "):
            sections[current].append((version, _num(line[5:])))

    def resolve(name: str, version: str) -> list:
        return [value for v, value in sections[name] if v in (None, version)]

    levels: dict[str, dict[str, int]] = {"red": {}, "blue": {}}
    for version, line in _versioned_lines(_read(pr.root, "data/events/prize_mon_levels.asm")):
        if line.startswith("db ") and version:
            mon, lv = _args(line[3:])
            levels[version][mon] = _num(lv)

    result: dict = {"mons": {}, "tms": []}
    for version in ("red", "blue"):
        rows = []
        for group in ("Mon1", "Mon2"):
            mons = resolve(f"PrizeMenu{group}Entries", version)
            costs = resolve(f"PrizeMenu{group}Cost", version)
            for mon, cost in zip(mons, costs):
                rows.append((mon, levels[version][mon], cost))
        result["mons"][version] = rows
    tms = resolve("PrizeMenuTMsEntries", "red")
    tm_costs = resolve("PrizeMenuTMsCost", "red")
    result["tms"] = list(zip(tms, tm_costs))
    return result


def _collect_wild(pr: Pokered) -> dict:
    """map const -> {"grass": {"rate", "red": [(lv, mon)], "blue": [...]}, "water": {...}}"""
    slot_chances: list[int] = []
    for line in (_strip(l) for l in _read(pr.root, "data/wild/probabilities.asm").splitlines()):
        if line.startswith("wild_chance "):
            slot_chances.append(_num(line.split()[1]))
    # WildDataPointers is indexed by map id; its comments are not reliable map names.
    map_by_id = {v: k for k, v in pr.map_ids.items()}
    pointer_map: list[tuple[str, str]] = []
    for line in _read(pr.root, "data/wild/grass_water.asm").splitlines():
        m = re.match(r"\s*dw (\w+)WildMons\b", line)
        if m:
            pointer_map.append((m.group(1), map_by_id[len(pointer_map)]))

    tables: dict[str, dict] = {}
    for path in (pr.root / "data/wild/maps").glob("*.asm"):
        label = path.stem
        data: dict = {}
        kind = None
        for version, line in _versioned_lines(path.read_text(encoding="utf-8")):
            m = re.match(r"def_(grass|water)_wildmons (\d+)", line)
            if m:
                kind = m.group(1)
                data[kind] = {"rate": int(m.group(2)), "red": [], "blue": []}
                continue
            if line.startswith("end_"):
                kind = None
                continue
            if kind and line.startswith("db "):
                lv, mon = _args(line[3:])
                for v in ("red", "blue"):
                    if version in (None, v):
                        data[kind][v].append((_num(lv), mon))
        tables[label] = data

    result: dict[str, dict] = {}
    for label, map_const in pointer_map:
        data = tables.get(label)
        if not data or label == "Nothing":
            continue
        if not any(d["rate"] for d in data.values()):
            continue
        result.setdefault(map_const, data)
    return {"maps": result, "slot_chances": slot_chances, "labels": {mp: label for label, mp in pointer_map}}


def _collect_super_rod(pr: Pokered) -> dict[str, list[tuple[int, str]]]:
    text = _read(pr.root, "data/wild/super_rod.asm")
    map_groups: list[tuple[str, str]] = []
    groups: dict[str, list[tuple[int, str]]] = {}
    current = None
    for line in (_strip(l) for l in text.splitlines()):
        m = re.match(r"dbw (\w+),\s*\.(\w+)", line)
        if m:
            map_groups.append((m.group(1), m.group(2)))
            continue
        m = re.match(r"^\.(\w+):$", line)
        if m:
            current = m.group(1)
            groups[current] = []
            continue
        if current and line.startswith("db "):
            a = _args(line[3:])
            if len(a) == 2:
                groups[current].append((_num(a[0]), a[1]))
    return {mp: groups[g] for mp, g in map_groups}


def _collect_object_mons(pr: Pokered) -> list[tuple[str, str, int]]:
    """Static overworld Pokemon (legendaries, Snorlax, Voltorb items...)."""
    out = []
    for path in sorted((pr.root / "data/maps/objects").glob("*.asm")):
        map_const = pr.map_from_stem(path.stem)
        if not map_const:
            continue
        for line in (_strip(l) for l in path.read_text(encoding="utf-8").splitlines()):
            if line.startswith("object_event"):
                a = _args(line[len("object_event"):])
                if len(a) == 8 and a[6] in pr.const_to_dex:
                    out.append((map_const, a[6], _num(a[7])))
    return out


def _collect_gift_mons(pr: Pokered) -> list[tuple[str, str, int]]:
    out = []
    for folder in ("scripts", "engine/events"):
        for path in sorted((pr.root / folder).glob("*.asm")):
            text = path.read_text(encoding="utf-8")
            if "GivePokemon" not in text:
                continue
            map_const = pr.map_from_stem(path.stem)
            where = pr.map_names[map_const] if map_const else _title(path.stem)
            for m in re.finditer(r"lb bc,\s*([A-Z0-9_]+),\s*(\d+)", text):
                if m.group(1) in pr.const_to_dex:
                    out.append((where, m.group(1), int(m.group(2))))
    return out


def _collect_trades(pr: Pokered) -> list[tuple[str, str, str, str]]:
    out = []
    for line in _read(pr.root, "data/events/trades.asm").splitlines():
        m = re.match(r'\s*npctrade (\w+),\s*(\w+),\s*\w+,\s*"(\w+)"\s*;\s*used in (\w+)', line)
        if m:
            out.append((pr.map_names[m.group(4)], m.group(1), m.group(2), m.group(3)))
    return out


def _collect_trainer_parties(pr: Pokered) -> dict[str, list[list[tuple[int, str]]]]:
    text = _read(pr.root, "data/trainers/parties.asm")
    parties: dict[str, list[list[tuple[int, str]]]] = defaultdict(list)
    comments: dict[str, list[str | None]] = defaultdict(list)
    current = None
    last_comment = None
    for raw in text.splitlines():
        stripped = raw.strip()
        m = re.match(r"^(\w+Data):$", stripped)
        if m:
            current = m.group(1)
            last_comment = None
            continue
        if stripped.startswith(";"):
            last_comment = stripped.lstrip("; ").strip()
            continue
        line = _strip(raw)
        if current and line.startswith("db "):
            a = _args(line[3:])
            if a[-1] == "0":
                a = a[:-1]
            if a[0] == "$FF":
                team = [(_num(a[i]), a[i + 1]) for i in range(1, len(a), 2)]
            else:
                lv = _num(a[0])
                team = [(lv, s) for s in a[1:]]
            parties[current].append(team)
            comments[current].append(last_comment)
    pr.party_comments = comments
    return parties


def _lone_moves(pr: Pokered) -> tuple[list[tuple[int, str]], dict[str, str]]:
    lone: list[tuple[int, str]] = []
    team: dict[str, str] = {}
    section = None
    for line in (_strip(l) for l in _read(pr.root, "data/trainers/special_moves.asm").splitlines()):
        if line.startswith("LoneMoves"):
            section = "lone"
        elif line.startswith("TeamMoves"):
            section = "team"
        elif line.startswith("db ") and section:
            a = _args(line[3:])
            if a == ["-1"]:
                continue
            if section == "lone":
                lone.append((_num(a[0]), a[1]))
            else:
                team[a[0]] = a[1]
    return lone, team


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_md(name: str, lines: list[str]) -> None:
    _MD_OUT.mkdir(parents=True, exist_ok=True)
    (_MD_OUT / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser_json(pr: Pokered) -> None:
    species = {}
    for internal_id in sorted(pr.internal_to_dex):
        b = pr.base[pr.internal_to_dex[internal_id]]
        species[str(internal_id)] = {
            "name": b["name"], "national_dex": b["dex"], "types": b["types"], "growth_rate": b["growth"],
        }
    _write_json(_PARSER_OUT / "species.json", species)

    moves = {str(m["id"]): {"name": m["name"], "type": m["type"], "pp": m["pp"],
                            "power": m["power"], "accuracy": m["accuracy"]}
             for m in sorted(pr.moves.values(), key=lambda m: m["id"])}
    _write_json(_PARSER_OUT / "moves.json", moves)

    items = {str(i["id"]): i["name"] for i in pr.items.values()}
    _write_json(_PARSER_OUT / "items.json", items)

    locations = [{"map_id": mid, "name": pr.map_names[c]} for c, mid in sorted(pr.map_ids.items(), key=lambda kv: kv[1])]
    _write_json(_PARSER_OUT / "locations.json", locations)


def _category(mtype: str, power: int | None = None) -> str:
    if power == 0:
        return "Status"
    return "Physical" if mtype in PHYSICAL_TYPES else "Special"


def _move_effect(m: dict) -> str:
    if m["const"] in MOVE_NOTES:
        return MOVE_NOTES[m["const"]]
    return EFFECT_TEXT.get(m["effect"], m["effect"])


def _fmt_power(m: dict) -> str:
    if m["power"] == 0:
        return "N/A"
    if m["power"] == 1:
        return "Varies"
    return str(m["power"])


def _fmt_acc(m: dict) -> str:
    return f"{m['accuracy']}%"


def build_pokedex_md(pr: Pokered) -> None:
    lines = []
    for dex in sorted(pr.base):
        b = pr.base[dex]
        s = b["stats"]
        t2 = b["types"][1] if len(b["types"]) > 1 else "None"
        bst = sum(s.values())
        lines.append(
            f"{dex:03d} {b['name']} Type1:{b['types'][0]} Type2:{t2} HP:{s['hp']} Atk:{s['atk']} "
            f"Def:{s['def']} Spd:{s['spd']} Spc:{s['spc']} BST:{bst} CatchRate:{b['catch_rate']} "
            f"BaseExp:{b['base_exp']} Growth:{_title(b['growth'])}"
        )
    _write_md("pokedex_gen1.md", lines)


def build_moves_md(pr: Pokered) -> None:
    tm_of = {mv: f"TM{i + 1:02d}" for i, mv in enumerate(pr.tm_moves)}
    tm_of.update({mv: f"HM{i + 1:02d}" for i, mv in enumerate(pr.hm_moves)})
    lines = []
    for m in sorted(pr.moves.values(), key=lambda m: m["name"]):
        machine = f" | Machine:{tm_of[m['const']]}" if m["const"] in tm_of else ""
        lines.append(
            f"Move:{m['name']} | Type:{m['type']} | Category:{_category(m['type'], m['power'])} | PP:{m['pp']} | "
            f"Power:{_fmt_power(m)} | Acc:{_fmt_acc(m)}{machine} | Effect:{_move_effect(m)}"
        )
    _write_md("moves_gen1.md", lines)


def build_learnsets_md(pr: Pokered) -> None:
    tm_label = {mv: f"TM{i + 1:02d}" for i, mv in enumerate(pr.tm_moves)}
    tm_label.update({mv: f"HM{i + 1:02d}" for i, mv in enumerate(pr.hm_moves)})
    order = {mv: i for i, mv in enumerate(pr.tm_moves + pr.hm_moves)}
    lines = []
    for dex in sorted(pr.base):
        b = pr.base[dex]
        level = [f"L1:{pr.move_name(m)}" for m in b["start_moves"]]
        level += [f"L{lv}:{pr.move_name(m)}" for lv, m in b["learnset"]]
        machines = sorted(b["tmhm"], key=lambda mv: order[mv])
        mach = ", ".join(f"{tm_label[mv]} {pr.move_name(mv)}" for mv in machines) or "None"
        lines.append(f"Pokemon:{b['name']} | LevelUp:{', '.join(level)} | Machine:{mach}")
    _write_md("learnsets_gen1.md", lines)


def build_tmhm_md(pr: Pokered, sources: dict[str, list[str]]) -> None:
    lines = []
    for prefix, moves in (("TM", pr.tm_moves), ("HM", pr.hm_moves)):
        for i, mv in enumerate(moves):
            m = pr.moves[mv]
            item_const = f"{prefix}_{mv}"
            price = pr.items[item_const]["price"]
            where = "; ".join(sources.get(item_const, [])) or "Unknown"
            price_txt = f" | Price:{price} (sell {price // 2})" if price else ""
            lines.append(
                f"Machine:{prefix}{i + 1:02d} | Move:{m['name']} | Type:{m['type']} | "
                f"Category:{_category(m['type'], m['power'])} | Power:{_fmt_power(m)} | Acc:{_fmt_acc(m)} | "
                f"PP:{m['pp']}{price_txt} | Location:{where} | Effect:{_move_effect(m)}"
            )
    lines.append("Note: TMs are single-use in Gen 1. HMs are reusable. An HM move cannot be overwritten by a new move, and Red/Blue have no Move Deleter, so an HM taught is permanent.")
    _write_md("tmhm_gen1.md", lines)


def build_evolution_md(pr: Pokered) -> None:
    item_name = {c: i["name"] for c, i in pr.items.items()}
    prevo: dict[int, int] = {}
    for dex, b in pr.base.items():
        for _, _, target in b["evolutions"]:
            prevo[pr.const_to_dex[target]] = dex

    def step(kind, arg) -> str:
        if kind == "level":
            return f"Lvl {arg}"
        if kind == "item":
            return f"Use {item_name[arg]}"
        return "Trade"

    def chains(dex: int) -> list[str]:
        b = pr.base[dex]
        if not b["evolutions"]:
            return [b["name"]]
        out = []
        for kind, arg, target in b["evolutions"]:
            for rest in chains(pr.const_to_dex[target]):
                out.append(f"{b['name']} -> {step(kind, arg)} -> {rest}")
        return out

    lines = []
    for dex in sorted(pr.base):
        if dex in prevo or not pr.base[dex]["evolutions"]:
            continue
        lines.extend(chains(dex))
    lines.append("Does not evolve: " + ", ".join(
        pr.base[d]["name"] for d in sorted(pr.base) if d not in prevo and not pr.base[d]["evolutions"]))
    lines.append("Note: Gen 1 has no held items and no friendship evolutions. Trade evolutions (Kadabra, Machoke, Graveler, Haunter) require a link trade. Pressing B during the evolution animation cancels it; the Pokemon tries again at its next level-up.")
    lines.append("Note: Eevee evolves by stone only in Gen 1: Fire Stone -> Flareon, Thunder Stone -> Jolteon, Water Stone -> Vaporeon.")
    _write_md("evolution_gen1.md", lines)


def build_items_md(pr: Pokered, sources: dict[str, list[str]]) -> None:
    lines = []
    for const, item in pr.items.items():
        if const.startswith(("TM_", "HM_", "ITEM_")) or const.endswith("BADGE") or const in ("SURFBOARD", "PP_UP_2", "UNUSED_ITEM"):
            continue
        category = "Key Items" if const in KEY_ITEMS else (
            "Balls" if const.endswith("_BALL") else "Main Items")
        price = item["price"]
        price_txt = str(price) if price else "-"
        where = "; ".join(sources.get(const, [])) or "-"
        desc = ITEM_DESCRIPTIONS.get(const, "")
        lines.append(
            f"Category:{category} | Name:{item['name']} | Price:{price_txt} | Description:{desc} | Location:{where}")
    lines.append("Category:Vending | Name:Fresh Water / Soda Pop / Lemonade | Price:200 / 300 / 350 | Description:Restore 50 / 60 / 80 HP | Location:Celadon Dept. Store Roof vending machines; give one of each to the girl on the roof for TM13 Ice Beam, TM48 Rock Slide, TM49 Tri Attack")
    lines.append("Note: The bag holds 20 item slots; the PC holds 50. Stacks cap at 99. Items sell for half their price.")
    _write_md("items_gen1.md", lines)


def _encounter_summary(pr: Pokered, rows: list[tuple[int, str]], chances: list[int]) -> str:
    agg: dict[str, dict] = OrderedDict()
    for (lv, mon), chance in zip(rows, chances):
        e = agg.setdefault(mon, {"min": lv, "max": lv, "pct": 0.0})
        e["min"] = min(e["min"], lv)
        e["max"] = max(e["max"], lv)
        e["pct"] += chance * 100 / 256
    parts = []
    for mon, e in sorted(agg.items(), key=lambda kv: -kv[1]["pct"]):
        lv = f"Lv{e['min']}" if e["min"] == e["max"] else f"Lv{e['min']}-{e['max']}"
        parts.append(f"{pr.mon(mon)['name']} ({lv}, {e['pct']:.0f}%)")
    return ", ".join(parts)


def build_catch_md(pr: Pokered) -> None:
    wild = _collect_wild(pr)
    chances = wild["slot_chances"]
    lines = []
    seen_labels: set[str] = set()
    for map_const, data in sorted(wild["maps"].items(), key=lambda kv: pr.map_ids[kv[0]]):
        label = wild["labels"][map_const]
        if label in seen_labels:
            continue
        seen_labels.add(label)
        name = MAP_NAME_OVERRIDES.get("SEA_ROUTES") if label == "SeaRoutes" else pr.map_names[map_const]
        for kind in ("grass", "water"):
            d = data.get(kind)
            if not d or not d["rate"]:
                continue
            method = "Grass" if kind == "grass" else "Surf"
            if kind == "grass" and any(w in name for w in ("Cave", "Mt.", "Tunnel", "Road", "Islands", "Tower", "Mansion", "Plant")):
                method = "Walking"
            red = _encounter_summary(pr, d["red"], chances)
            blue = _encounter_summary(pr, d["blue"], chances)
            if red == blue:
                lines.append(f"Location:{name} | Method:{method} | Version:Both | Pokemon:{red}")
            else:
                lines.append(f"Location:{name} | Method:{method} | Version:Red | Pokemon:{red}")
                lines.append(f"Location:{name} | Method:{method} | Version:Blue | Pokemon:{blue}")

    super_rod = _collect_super_rod(pr)
    by_group: dict[tuple, list[str]] = defaultdict(list)
    for map_const, group in super_rod.items():
        by_group[tuple(group)].append(pr.map_names[map_const])
    for group, maps in by_group.items():
        mons = ", ".join(f"{pr.mon(m)['name']} (Lv{lv})" for lv, m in group)
        for name in maps:
            lines.append(f"Location:{name} | Method:Super Rod | Version:Both | Pokemon:{mons} (equal odds)")
    lines.append("Location:Any fishable water | Method:Old Rod | Version:Both | Pokemon:Magikarp (Lv5)")
    lines.append("Location:Any fishable water | Method:Good Rod | Version:Both | Pokemon:Goldeen (Lv10), Poliwag (Lv10) (50% each)")

    for where, mon, lv in _collect_gift_mons(pr):
        if mon == "MAGIKARP":
            lines.append(f"Location:{where} | Method:Purchase | Version:Both | Pokemon:Magikarp (Lv{lv}) for ¥500 from the salesman (one time)")
        else:
            lines.append(f"Location:{where} | Method:Gift | Version:Both | Pokemon:{pr.mon(mon)['name']} (Lv{lv})")
    lines.append("Location:Saffron Fighting Dojo | Method:Gift | Version:Both | Pokemon:Hitmonlee (Lv30) or Hitmonchan (Lv30) — choose one after beating the Karate Master")
    statics: dict[tuple[str, str, int], int] = OrderedDict()
    for map_const, mon, lv in _collect_object_mons(pr):
        key = (pr.map_names[map_const], mon, lv)
        statics[key] = statics.get(key, 0) + 1
    for (where, mon, lv), count in statics.items():
        qty = f" x{count}" if count > 1 else ""
        note = " — disguised as item balls" if mon in ("VOLTORB", "ELECTRODE") else ""
        lines.append(f"Location:{where} | Method:Static encounter | Version:Both | Pokemon:{pr.mon(mon)['name']} (Lv{lv}){qty}{note} (one chance; gone once defeated or caught)")
    lines.append("Location:Route 12 | Method:Static encounter | Version:Both | Pokemon:Snorlax (Lv30) — wake with the Poké Flute (one chance)")
    lines.append("Location:Route 16 | Method:Static encounter | Version:Both | Pokemon:Snorlax (Lv30) — wake with the Poké Flute (one chance)")
    for where, give, get, nick in _collect_trades(pr):
        lines.append(f"Location:{where} | Method:In-game trade | Version:Both | Pokemon:{pr.mon(get)['name']} (nicknamed {nick}) for your {pr.mon(give)['name']}")
    prizes = _collect_prizes(pr)
    for version in ("red", "blue"):
        rows = ", ".join(f"{pr.mon(m)['name']} (Lv{lv}, {cost} coins)" for m, lv, cost in prizes["mons"][version])
        lines.append(f"Location:Celadon Game Corner Prize Room | Method:Prize | Version:{version.capitalize()} | Pokemon:{rows}")
    lines.append("Location:Cinnabar Lab Fossil Room | Method:Fossil revival | Version:Both | Pokemon:Omanyte (Lv30) from Helix Fossil, Kabuto (Lv30) from Dome Fossil, Aerodactyl (Lv30) from Old Amber")
    lines.append("Location:Mt. Moon B2F | Method:Fossil choice | Version:Both | Pokemon:Helix Fossil (Omanyte) or Dome Fossil (Kabuto) — pick one after defeating the Super Nerd; the other is lost")
    lines.append("Location:Pewter Museum 1F (back entrance, requires Cut) | Method:Gift item | Version:Both | Pokemon:Old Amber (revive to Aerodactyl)")
    _write_md("catch_locations_gen1.md", lines)


def build_shops_md(pr: Pokered) -> None:
    lines = ["## Gen 1 Shop Inventories (Red/Blue)", "",
             "Each line: Shop | Items with price. Items sell for half price.", ""]
    for shop, items in _collect_marts(pr).items():
        entries = ", ".join(f"{pr.item_label(i)} ¥{pr.items[i]['price']}" for i in items)
        lines.append(f"Shop:{shop} | Items:{entries}")
    prizes = _collect_prizes(pr)
    lines.append("Shop:Celadon Game Corner Prize Room | Items:" + ", ".join(
        f"{pr.item_label(c)} {cost} coins" for c, cost in prizes["tms"]))
    for version in ("red", "blue"):
        lines.append(f"Shop:Celadon Game Corner Prize Room ({version.capitalize()}) | Pokemon:" + ", ".join(
            f"{pr.mon(m)['name']} Lv{lv} {cost} coins" for m, lv, cost in prizes["mons"][version]))
    lines.append("Shop:Celadon Game Corner | Items:Coins 50 for ¥1000 (Coin Case required)")
    lines.append("Shop:Celadon Dept. Store Roof vending machines | Items:Fresh Water ¥200, Soda Pop ¥300, Lemonade ¥350")
    lines.append("Shop:Mt. Moon Pokémon Center (Route 4) | Pokemon:Magikarp Lv5 ¥500 (one time)")
    lines.append("Shop:Cerulean Bike Shop | Items:Bicycle ¥1000000 (get it free with the Bike Voucher from the Vermilion Pokémon Fan Club chairman)")
    _write_md("shops_gen1.md", lines)


def build_type_chart_md(pr: Pokered) -> None:
    chart: dict[tuple[str, str], float] = {}
    mult = {"SUPER_EFFECTIVE": 2.0, "NOT_VERY_EFFECTIVE": 0.5, "NO_EFFECT": 0.0}
    for line in (_strip(l) for l in _read(pr.root, "data/types/type_matchups.asm").splitlines()):
        if line.startswith("db ") and line != "db -1":
            a = _args(line[3:])
            if len(a) == 3:
                chart[(TYPE_NAMES[a[0]], TYPE_NAMES[a[1]])] = mult[a[2]]
    lines = ["# Gen 1 Type Chart (Red/Blue)", "",
             "Straight from the game's matchup table. Unlisted pairs are 1x. No Dark, Steel, or Fairy types exist.", ""]
    for atk in TYPE_ORDER:
        se = [d for d in TYPE_ORDER if chart.get((atk, d)) == 2.0]
        nve = [d for d in TYPE_ORDER if chart.get((atk, d)) == 0.5]
        imm = [d for d in TYPE_ORDER if chart.get((atk, d)) == 0.0]
        lines.append(f"Attacking:{atk} | Category:{_category(atk)} | 2x:{', '.join(se) or '-'} | 0.5x:{', '.join(nve) or '-'} | 0x:{', '.join(imm) or '-'}")
    lines.append("")
    for dfn in TYPE_ORDER:
        weak = [a for a in TYPE_ORDER if chart.get((a, dfn)) == 2.0]
        res = [a for a in TYPE_ORDER if chart.get((a, dfn)) == 0.5]
        imm = [a for a in TYPE_ORDER if chart.get((a, dfn)) == 0.0]
        lines.append(f"Defending:{dfn} | Weak to:{', '.join(weak) or '-'} | Resists:{', '.join(res) or '-'} | Immune to:{', '.join(imm) or '-'}")
    lines += ["",
              "Gen 1 differences vs later games: Ghost has no effect on Psychic (a bug; the games intended 2x). Bug is 2x vs Poison and Poison is 2x vs Bug. Ice is 1x vs Fire (Fire resists Ice from Gen 2 on). Psychic has no weaknesses except Bug, and the only Bug attacks are weak (Pin Missile, Twineedle, Leech Life).",
              "Dual types multiply: a 2x and 2x matchup is 4x; a 2x and 0.5x matchup is 1x."]
    _write_md("type_chart_gen1.md", lines)


def _fmt_team(pr: Pokered, team: list[tuple[int, str]], overrides: dict[int, dict[int, str]] | None = None) -> list[str]:
    out = []
    for i, (lv, mon) in enumerate(team):
        moves = pr.moves_at_level(mon, lv)
        for slot, move in (overrides or {}).get(i, {}).items():
            while len(moves) <= slot:
                moves.append(None)
            moves[slot] = move
        names = ", ".join(pr.move_name(m) for m in moves if m)
        out.append(f"{pr.mon(mon)['name']} Lv{lv} ({'/'.join(pr.mon(mon)['types'])}) [{names}]")
    return out


def build_trainers_md(pr: Pokered) -> None:
    parties = _collect_trainer_parties(pr)
    lone, team_moves = _lone_moves(pr)
    rewards = _collect_item_sources_by_gym(pr)
    lines = ["# Gen 1 Boss Trainers (Red/Blue)", "",
             "Movesets are computed from level-up learnsets exactly as the game builds trainer parties, plus each leader's scripted special move. One line per trainer/team.", ""]
    for n, (leader, label, gym, badge, gtype, lone_idx) in enumerate(GYMS, start=1):
        team = parties[label][-1]
        mon_idx, move = lone[lone_idx - 1]
        overrides = {mon_idx: {2: move}}
        reward = rewards.get(gym, "")
        lines.append(
            f"Trainer:{leader} | Role:Gym {n} ({pr.map_names[gym]}) | Type:{gtype} | Badge:{badge} | "
            f"Reward:{reward} | Team:{'; '.join(_fmt_team(pr, team, overrides))}")
    for leader, label, cls in ELITE_FOUR:
        team = parties[label][0]
        overrides = {4: {2: team_moves[cls]}}
        lines.append(f"Trainer:{leader} | Role:Elite Four | Team:{'; '.join(_fmt_team(pr, team, overrides))}")
    starters = ["SQUIRTLE", "BULBASAUR", "CHARMANDER"]
    player_pick = {"SQUIRTLE": "Charmander", "BULBASAUR": "Squirtle", "CHARMANDER": "Bulbasaur"}
    rival_labels = [("Rival1Data", 3), ("Rival2Data", 3), ("Rival3Data", 3)]
    for label, per in rival_labels:
        teams = parties[label]
        comments = pr.party_comments[label]
        for i in range(0, len(teams), per):
            where = next((c for c in comments[i:i + per] if c), None)
            if label == "Rival1Data" and i == 0:
                where = "Oak's Lab"
            if label == "Rival3Data":
                where = "Indigo Plateau (Champion)"
            for j, team in enumerate(teams[i:i + per]):
                rival_starter = starters[j]
                overrides = None
                if label == "Rival3Data":
                    starter_move = {"SQUIRTLE": "BLIZZARD", "BULBASAUR": "MEGA_DRAIN", "CHARMANDER": "FIRE_BLAST"}[rival_starter]
                    overrides = {0: {2: "SKY_ATTACK"}, len(team) - 1: {2: starter_move}}
                lines.append(
                    f"Trainer:Rival | Role:{where} | If you chose:{player_pick[rival_starter]} | "
                    f"Team:{'; '.join(_fmt_team(pr, team, overrides))}")
    for i, team in enumerate(parties["GiovanniData"]):
        where = pr.party_comments["GiovanniData"][i]
        if where == "Viridian Gym":
            continue
        lines.append(f"Trainer:Giovanni | Role:{where} | Team:{'; '.join(_fmt_team(pr, team))}")
    _write_md("trainers_gen1.md", lines)


def _collect_item_sources_by_gym(pr: Pokered) -> dict[str, str]:
    out = {}
    for _, _, gym, *_ in GYMS:
        path = pr.root / "scripts" / f"{_pascal(gym)}.asm"
        text = path.read_text(encoding="utf-8")
        m = re.search(r"lb bc,\s*(TM_\w+),", text)
        if m:
            out[gym] = pr.item_label(m.group(1))
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _ensure_pokered(path: Path | None) -> Path:
    if path:
        return path
    target = _CACHE_DIR / "pokered"
    if not target.exists():
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", _POKERED_GIT, str(target)], check=True)
    return target


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--pokered", type=Path, default=None, help="path to a pret/pokered checkout")
    args = p.parse_args(argv)
    pr = Pokered(_ensure_pokered(args.pokered))

    build_parser_json(pr)
    sources = _collect_item_sources(pr)
    build_pokedex_md(pr)
    build_moves_md(pr)
    build_learnsets_md(pr)
    build_tmhm_md(pr, sources)
    build_evolution_md(pr)
    build_items_md(pr, sources)
    build_catch_md(pr)
    build_shops_md(pr)
    build_type_chart_md(pr)
    build_trainers_md(pr)
    print(f"Wrote {len(pr.base)} species, {len(pr.moves)} moves, {len(pr.items)} items, "
          f"{len(pr.map_ids)} maps to {_PARSER_OUT.relative_to(_ROOT)} and {_MD_OUT.relative_to(_ROOT)}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
