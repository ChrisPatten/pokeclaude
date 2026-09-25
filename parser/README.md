# parser — Pokémon Ruby/Sapphire Save File Parser + Sync

Reads `.srm` save files from Pokémon Ruby and Sapphire (Generation III GBA) and outputs structured JSON containing trainer info, party, PC boxes, daycare, inventory, badges, Pokédex counts, and location. `parser.sync` wraps the parser with the deterministic pull/dedupe/archive/diff pipeline used by the `pokeclaude-sync` skill.

## Usage

### Parse a save

```bash
python3 -m parser.parse_save path/to/save.srm
```

Prints JSON to stdout. All logging — including anything collected into the output's `warnings` list — goes to stderr, so stdout is always clean JSON.

```python
from parser.parse_save import parse

data = parse("path/to/save.srm")
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
  save_metadata — save_slot ("A"|"B"), save_index, checksum_valid, invalid_sections[], parsed_at
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

## Architecture

```
parser/
├── parse_save.py   — entry point: reads a .srm, orchestrates the modules below, returns the dict
├── sync.py          — CLI: scp pull, MD5 dedupe, archive, snapshot, history.json, diff
├── diff.py          — pure function diff_saves(old, new) -> dict; no I/O
├── decode.py        — sector I/O, checksum validation, XOR decryption, Gen III string decoding
├── trainer.py       — trainer profile, badges (event flags), location, inventory, Pokédex
├── pokemon.py       — party (100-byte), PC box (80-byte), and daycare Pokémon parsing
├── data_loader.py   — cached (lru_cache) loaders for everything in data/ — load each JSON file once per process
└── data/
    ├── species.json       — internal Gen III species id → display name
    ├── species_info.json  — internal Gen III species id → { name, national_dex, types, abilities } (built by scripts/build_species_info.py)
    ├── moves.json          — move id → { name, type, pp }
    ├── items.json          — item id → name
    ├── natures.json        — index (PID % 25) → { name, stat_up, stat_down }
    ├── growth_rates.json   — internal Gen III species id → growth rate key (medium_fast, erratic, ...)
    └── locations.json      — [{ map_bank, map_id, name }] for Hoenn
```

Every parser module reads static reference tables through `data_loader.py` rather than opening `data/*.json` directly, so each file is parsed once per process no matter how many modules use it.

### How it works

1. **Sectors and block fallback** — The 128KB save file contains two 56KB blocks (A and B), each split into 14 shuffled 4KB sectors. `decode.py` validates each block independently (every section 0-13 present once, signature and per-section checksum correct, save index initialized). If both blocks are valid, it picks the one with the higher save index (the most recently written save). If only one block is valid, it uses that one and logs a warning — added to the output's `warnings` list — naming the sections that failed in the discarded block. If neither block validates, parsing raises an error instead of returning a result; `parser.sync` catches that and reports `invalid_save`, leaving the trainer's last good save and snapshot untouched. `save_metadata.invalid_sections` / `checksum_valid` describe the block that was actually used.

2. **Decryption** — Pokémon substructure data is XOR-encrypted with `PV ^ OT_ID`. The 48-byte block is split into four 12-byte substructures (Growth, Attacks, EVs, Misc) whose order is determined by `PV % 24`.

3. **String encoding** — Gen III uses a custom character table (not ASCII). `decode_string()` translates bytes to Unicode, stopping at the `0xFF` terminator.

4. **Badges** — Stored as event flags in the Section 2 flag array (offset `0x2A0`), not as a simple byte. Flags `0x807`–`0x80E` correspond to the eight Hoenn badges.

5. **Types/ability resolution** — `pokemon.py` looks up each Pokémon's `species_id` in `species_info.json` for its types and ability list, then picks the ability using the substructure's ability bit. A missing `species_info.json` entry logs a warning and falls back to `["Unknown"]` / `"Unknown"` rather than failing the parse.

6. **Box/daycare levels** — derived from stored experience using the species' actual growth rate curve (`growth_rates.json`), not a flat cube-root estimate — species on `erratic`, `fluctuating`, `medium_slow`, `fast`, or `slow` curves are accurate, not just `medium_fast`.

## Diff (`parser/diff.py`)

`diff_saves(old, new)` takes two parsed-save dicts and returns a deterministic diff, matching Pokémon across party/boxes/daycare by `pid` (so evolution, box moves, and level-ups don't break identity tracking). It covers: location, badges gained, money/playtime/Pokédex deltas, party membership (added/removed/changed) and per-mon changes for evolution/level/moves/held item/nickname, newly caught and released-or-traded pids (presence anywhere in the save), a full daycare from/to when membership changes, and per-pocket inventory deltas. See `parser/sync.py`'s module docstring and `tests/test_diff.py` for the exact shape and edge cases (e.g. a mon that leaves the party but stays in a box gets a `where` field instead of disappearing).

## Known limitations

- **Location coverage** is partial. Unrecognized map bank/ID pairs get `location.known: false` and a name like `"Unknown (bank=X, id=Y)"`.
- **Emerald and FireRed/LeafGreen** are not supported — offsets differ.

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

`tests/test_parser_synthetic.py` and `tests/test_diff.py`/`tests/test_sync.py` run against hand-built fixtures and mocks — no real save file needed. `tests/test_parser_golden.py` additionally checks a real save (`tests/fixtures/sapphire.srm`) against a checked-in expected output (`tests/fixtures/sapphire.golden.json`); both are gitignored, and the golden test skips itself when they're missing. Regenerate the golden file after an intentional parser change:

```bash
UPDATE_GOLDEN=1 python3 -m unittest tests.test_parser_golden
```

## Dependencies

Python 3.11, stdlib only (`struct`, `json`, `datetime`, `pathlib`, `argparse`, `subprocess`, `hashlib`). No pip packages required.
