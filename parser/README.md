# parser — Pokémon Save File Parser + Sync (Ruby/Sapphire, Red/Blue)

Reads save files from Pokémon Ruby and Sapphire (Generation III GBA, `.srm`) and Pokémon Red and Blue (Generation I Game Boy, `.sav`) and outputs structured JSON containing trainer info, party, PC boxes, daycare, inventory, badges, Pokédex counts, and location. `parser.sync` wraps the parser with the deterministic pull/dedupe/archive/diff pipeline used by the `pokeclaude-sync` skill.

## Usage

### Parse a save

```bash
python3 -m parser.parse_save path/to/save.srm            # generation detected from file size
python3 -m parser.parse_save path/to/red.sav --gen 1     # or state it explicitly
```

Prints JSON to stdout. All logging — including anything collected into the output's `warnings` list — goes to stderr, so stdout is always clean JSON.

```python
from parser.parse_save import parse

data = parse("path/to/save.srm")         # parse(path, gen=1) for Red/Blue
print(data["trainer"]["name"])            # "TRAINER"
print(data["badges"]["count"])            # 6
print(data["party"][0]["species_name"])   # "Tropius"
print(data["party"][0]["types"])          # ["Grass", "Flying"]
```

### Sync a save (pull + parse + diff)

```bash
python3 -m parser.sync <user_id>                        # scp pull from users/<user_id>/config.json, then parse/diff
python3 -m parser.sync <user_id> --local path/to/save.srm  # skip the pull, use a local file
python3 -m parser.sync <user_id> --diff [--from N] [--to M]  # diff two stored snapshots, no pull
```

See the top-level [README](../README.md) for `config.json` setup. `sync.py` prints one JSON object to stdout with a `status` of `pull_failed` (exit 2), `invalid_save` (exit 3), `unchanged`, `synced` (carries the full parsed `save` plus a `diff` against the previous sync), or `diff` (`--diff` mode). It owns everything deterministic — MD5 dedupe, checksum validation, archiving to `saves/archive/`, snapshotting to `saves/snapshots/NNN.json`, and maintaining `saves/history.json` — so the skill only ever needs to interpret that one JSON object.

## Output schema

```
{
  trainer       — name, gender, trainer_id, playtime {hours,minutes,seconds}, money
  badges        — count, obtained[]
  location      — map_bank, map_id, name, known (false when the bank/id pair isn't in locations.json)
  party[]       — see Mon below, plus status, hp {current,max}, stats {attack,defense,speed,sp_atk,sp_def}
  boxes[]       — [{ box_index, name, pokemon: [Mon] }] for all 14 boxes
  daycare[]     — 0-2 Mon, no party-only fields
  inventory     — pc, items, key_items, balls, tms_hms, berries — each [{name, quantity}] (key_items is [str])
  pokedex       — seen, caught
  save_metadata — generation (1|3), save_slot ("A"|"B"; null in Gen 1), save_index (null in Gen 1), checksum_valid, invalid_sections[], parsed_at
  warnings[]    — every WARNING+ log line emitted during parsing (also written to stderr)
}
```

**Mon** (shared shape for party/box/daycare):

```
{
  slot, pid,            — pid is "0x1A2B3C4D", the personality value as a hex string; stable identity across syncs
  species_id, species_name, nickname,
  types: [str],         — 1 or 2 entries, e.g. ["Dragon", "Flying"]
  ability,               — resolved from the substructure's ability bit + species_info.json
  level, experience,     — party: level is the stored value; box/daycare: derived from experience + growth rate
  nature, nature_effect, — nature_effect is e.g. "Atk↑, SpAtk↓", or "neutral"
  held_item,             — "None" when empty
  moves: [{slot, move_id, name, type, pp, pp_max}],
  is_egg
}
```

Types, ability, and nature_effect are resolved by the parser — callers (including the sync skill) should never re-derive or look these up elsewhere.

### Gen 1 (Red/Blue) differences

Same top-level keys and Mon shape, so `diff.py` and `sync.py` work unchanged. Where Gen 1 lacks a concept the key stays with a fixed value:

```
trainer       — adds rival_name, coins; gender is always "male"
location      — map_bank is null; map_id is wCurMap
party[].stats — {attack, defense, speed, special} (one Special stat)
boxes[]       — 12 boxes of 20, names "BOX 1".."BOX 12", plus is_current (the box selected in the PC)
daycare[]     — 0-1 Mon; level derived from EXP (the daycare adds 1 EXP per step)
inventory     — items (the 20-slot bag, in order), pc (50 slots); TMs/HMs named "TM01"/"HM01"
Mon           — ability, nature, nature_effect: null; held_item: "None"; is_egg: false
                pid: "0x<OT ID><DVs>" — the two values fixed for a Pokémon's lifetime. Duplicates
                within one save (same OT and DVs) get a "-2", "-3" suffix and a warning.
                species_id is the internal Gen 1 index (Rhydon = 1), not the National Dex number.
                Box level is the stored level; party level is the party struct's level byte.
```

## Architecture

```
parser/
├── parse_save.py   — entry point: reads a save, detects/dispatches the generation, returns the dict
├── sync.py          — CLI: scp pull, MD5 dedupe, archive, snapshot, history.json, diff
├── diff.py          — pure function diff_saves(old, new) -> dict; no I/O
├── decode.py        — sector I/O, checksum validation, XOR decryption, Gen III string decoding
├── trainer.py       — trainer profile, badges (event flags), location, inventory, Pokédex
├── pokemon.py       — party (100-byte), PC box (80-byte), and daycare Pokémon parsing
├── data_loader.py   — cached (lru_cache) loaders for everything in data/ — load each JSON file once per process
├── gen1/            — Generation I (Red/Blue)
│   ├── __init__.py  — parse_bytes(sav): checksum validation + orchestration
│   ├── layout.py    — SRAM offsets (verified against pokered.sym), charset, BCD, checksum
│   ├── pokemon.py   — party (44-byte), box (33-byte), daycare structs; PC box banks; growth curves
│   └── trainer.py   — trainer, badges, location, bag/PC items, Pokédex
└── data/
    ├── species.json       — internal Gen III species id → display name
    ├── species_info.json  — internal Gen III species id → { name, national_dex, types, abilities } (built by scripts/build_species_info.py)
    ├── moves.json          — move id → { name, type, pp }
    ├── items.json          — item id → name
    ├── natures.json        — index (PID % 25) → { name, stat_up, stat_down }
    ├── growth_rates.json   — internal Gen III species id → growth rate key (medium_fast, erratic, ...)
    ├── locations.json      — [{ map_bank, map_id, name }] for Hoenn
    └── gen1/               — built by scripts/build_gen1_data.py from pret/pokered
        ├── species.json    — internal Gen 1 species index → { name, national_dex, types, growth_rate }
        ├── moves.json      — move id → { name, type, pp, power, accuracy } (Gen 1 values)
        ├── items.json      — item id → name
        └── locations.json  — [{ map_id, name }] for every Kanto map id
```

Every parser module reads static reference tables through `data_loader.py` rather than opening `data/*.json` directly, so each file is parsed once per process no matter how many modules use it.

### How it works

1. **Sectors and block fallback** — The 128KB save file contains two 56KB blocks (A and B), each split into 14 shuffled 4KB sectors. `decode.py` validates each block independently (every section 0-13 present once, signature and per-section checksum correct, save index initialized). If both blocks are valid, it picks the one with the higher save index (the most recently written save). If only one block is valid, it uses that one and logs a warning — added to the output's `warnings` list — naming the sections that failed in the discarded block. If neither block validates, parsing raises an error instead of returning a result; `parser.sync` catches that and reports `invalid_save`, leaving the trainer's last good save and snapshot untouched. `save_metadata.invalid_sections` / `checksum_valid` describe the block that was actually used.

2. **Decryption** — Pokémon substructure data is XOR-encrypted with `PV ^ OT_ID`. The 48-byte block is split into four 12-byte substructures (Growth, Attacks, EVs, Misc) whose order is determined by `PV % 24`.

3. **String encoding** — Gen III uses a custom character table (not ASCII). `decode_string()` translates bytes to Unicode, stopping at the `0xFF` terminator.

4. **Badges** — Stored as event flags in the Section 2 flag array (offset `0x2A0`), not as a simple byte. Flags `0x807`–`0x80E` correspond to the eight Hoenn badges.

5. **Types/ability resolution** — `pokemon.py` looks up each Pokémon's `species_id` in `species_info.json` for its types and ability list, then picks the ability using the substructure's ability bit. A missing `species_info.json` entry logs a warning and falls back to `["Unknown"]` / `"Unknown"` rather than failing the parse.

6. **Box/daycare levels** — derived from stored experience using the species' actual growth rate curve (`growth_rates.json`), not a flat cube-root estimate — species on `erratic`, `fluctuating`, `medium_slow`, `fast`, or `slow` curves are accurate, not just `medium_fast`.

### How Gen 1 works

1. **Layout** — The 32KB `.sav` is the cartridge SRAM: four 8KB banks end to end. Bank 1 holds the main data (player, bag, badges, Pokédex, party, the currently selected PC box); banks 2 and 3 hold PC boxes 1-6 and 7-12. Every offset in `gen1/layout.py` was checked against the symbol file of a pret/pokered build that matches the retail ROMs byte for byte. All integers are big-endian; money and coins are BCD.
2. **Validation** — Gen 1 keeps one save copy, so there is no fallback block. The main checksum (bitwise NOT of the 8-bit sum of `0x2598-0x3522`) must match the byte at `0x3523`, or parsing raises and `parser.sync` reports `invalid_save`. PC bank checksums are checked too; a mismatch there is a warning, since the game itself never re-verifies them on load.
3. **PC boxes** — The selected box lives in bank 1 (`sCurBoxData`) and its bank-2/3 slot is blanked by the game, so the parser reads that box from bank 1. Banks 2 and 3 are only initialised the first time the player changes boxes (bit 7 of `wCurrentBoxNum`); before that, every other box is empty.
4. **PP** — The top two bits of each PP byte are PP Ups; each adds `min(base // 5, 7)` (a 40-PP move caps at 61).
5. **Glitch species** — An internal index with no species (MissingNo. slots) is reported as `"MissingNo. (<index>)"` with type `"Unknown"` and a warning, rather than failing the parse.

`tests/data/gen1_red_ingame.sav` is a save produced by Pokémon Red's own save routine (booted in PyBoy, known data injected into WRAM, saved from the Start menu — `scripts/make_gen1_test_save.py`), so the tests cover the real SRAM format and checksum, not just the parser's own assumptions.

## Diff (`parser/diff.py`)

`diff_saves(old, new)` takes two parsed-save dicts and returns a deterministic diff, matching Pokémon across party/boxes/daycare by `pid` (so evolution, box moves, and level-ups don't break identity tracking). It covers: location, badges gained, money/playtime/Pokédex deltas, party membership (added/removed/changed) and per-mon changes for evolution/level/moves/held item/nickname, newly caught and released-or-traded pids (presence anywhere in the save), a full daycare from/to when membership changes, and per-pocket inventory deltas. See `parser/sync.py`'s module docstring and `tests/test_diff.py` for the exact shape and edge cases (e.g. a mon that leaves the party but stays in a box gets a `where` field instead of disappearing).

## Known limitations

- **Location coverage** is partial. Unrecognized map bank/ID pairs get `location.known: false` and a name like `"Unknown (bank=X, id=Y)"`.
- **Emerald and FireRed/LeafGreen** are not supported — offsets differ.
- **Yellow** is not supported (Pikachu data and some layout differences). **Gold/Silver/Crystal** saves are also 32KB; size detection would treat one as Gen 1 and the Gen 1 checksum check would reject it. Set `gen` in `config.json`.
- **Gen 1 identity** — `pid` is synthesized from OT ID + DVs. Two Pokémon with the same OT and identical DVs (1 in 65,536 per pair) are disambiguated by save order, so a swap between them can read as two changes in a diff.

## Building the Gen 1 tables

```bash
python3 scripts/build_gen1_data.py                  # clones pret/pokered into scripts/cache/pokered
python3 scripts/build_gen1_data.py --pokered PATH   # or use an existing checkout
```

Writes `parser/data/gen1/*.json` and every `data/gen_1/*_gen1.md` reference file (not `red_blue.md`, which is hand-written). Move names come from `parser/data/moves.json` and species names from `species_info.json` by National Dex number, so names match across generations; everything else (types, power, accuracy, PP, base stats, learnsets, TM compatibility, encounter tables, item locations, trainer parties) is parsed from pokered.

## Building `species_info.json`

```bash
python3 scripts/build_species_info.py
```

Joins `data/gen_3/pokedex_gen3.md` (keyed by National Dex number, owned by the game-data workstream) against `parser/data/species.json` (keyed by the internal Gen III species id used inside `.srm` files) by species name, producing `parser/data/species_info.json` keyed by internal id: `{"<id>": {"name", "national_dex", "types", "abilities"}}`. Re-run it whenever `pokedex_gen3.md` changes. A small alias table in the script handles name-spelling differences (e.g. `Nidoran F`/`Nidoran♀`) between the two sources.

`scripts/verify_data_vs_pokeruby.py` cross-checks `species.json` / `species_info.json` / `growth_rates.json` against the [pret/pokeruby](https://github.com/pret/pokeruby) decompilation (fetched and cached under `scripts/cache/`), reporting every name/type/ability/growth-rate mismatch; pass `--fix` to have it write corrected types/abilities/growth-rates back (species name changes are reported only, never auto-applied). A `verify_golden.py` may also land here to check a live parse against `tests/fixtures/sapphire.golden.json`; check `scripts/` for it if referenced elsewhere.

## Testing

```bash
python3 -m unittest discover -s tests -v
```

`tests/test_parser_synthetic.py` and `tests/test_diff.py`/`tests/test_sync.py` run against hand-built fixtures and mocks — no real save file needed. `tests/test_gen1_parser.py` runs against the committed game-written Red save in `tests/data/` plus mutated copies of it. `tests/test_parser_golden.py` additionally checks a real save (`tests/fixtures/sapphire.srm`) against a checked-in expected output (`tests/fixtures/sapphire.golden.json`); both are gitignored, and the golden test skips itself when they're missing. Regenerate the golden file after an intentional parser change:

```bash
UPDATE_GOLDEN=1 python3 -m unittest tests.test_parser_golden
```

## Dependencies

Python 3.11, stdlib only (`struct`, `json`, `datetime`, `pathlib`, `argparse`, `subprocess`, `hashlib`). No pip packages required.
