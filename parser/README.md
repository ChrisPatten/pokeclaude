# parser — Pokémon Ruby/Sapphire Save File Parser

Reads `.srm` save files from Pokémon Ruby and Sapphire (Generation III GBA) and outputs structured JSON containing trainer info, party, PC boxes, inventory, badges, Pokédex counts, and location.

## Usage

### CLI

```bash
python3 -m parser.parse_save path/to/save.srm
```

Prints JSON to stdout.

### As a module

```python
from parser.parse_save import parse

data = parse("path/to/save.srm")
print(data["trainer"]["name"])       # "I3rick"
print(data["badges"]["count"])       # 3
print(data["party"][0]["species_name"])  # "Golem"
```

## Output schema

```
{
  trainer     — name, gender, trainer_id, playtime, money
  badges      — count, obtained[]
  location    — map_bank, map_id, name
  party[]     — species, nickname, level, nature, moves, stats, HP, status, held item
  boxes[]     — box name, pokemon[] (species, nickname, level, nature, moves, held item)
  inventory   — pc, items, key_items, balls, tms_hms, berries
  pokedex     — seen, caught
  save_metadata — save_slot, checksum_valid, parsed_at
}
```

Full schema with types is documented in `../BUILD_PLAN.md`.

## Architecture

```
parser/
├── parse_save.py   — entry point: reads file, orchestrates modules, returns dict
├── decode.py       — sector I/O, checksum validation, XOR decryption, Gen III string decoding
├── trainer.py      — trainer profile, badges (event flags), location, inventory, Pokédex
├── pokemon.py      — party (100-byte entries) and PC box (80-byte entries) parsing
└── data/
    ├── species.json    — Gen III internal species index → name (0–411)
    ├── moves.json      — move ID → { name, type, pp } (0–354)
    ├── items.json      — item ID → name (0–376)
    ├── natures.json    — index 0–24 → { name, stat_up, stat_down }
    ├── abilities.json  — ability ID → name (0–77)
    └── locations.json  — [{ map_bank, map_id, name }] for Hoenn
```

### How it works

1. **Sectors** — The 128KB save file contains two 56KB blocks (A and B), each split into 14 shuffled 4KB sectors. `decode.py` validates checksums, picks the most recent block, and maps section IDs to sector data.

2. **Decryption** — Pokémon substructure data is XOR-encrypted with `PV ^ OT_ID`. The 48-byte block is split into four 12-byte substructures (Growth, Attacks, EVs, Misc) whose order is determined by `PV % 24`.

3. **String encoding** — Gen III uses a custom character table (not ASCII). `decode_string()` translates bytes to Unicode, stopping at the `0xFF` terminator.

4. **Badges** — Stored as event flags in the Section 2 flag array (offset `0x2A0`), not as a simple byte. Flags `0x807`–`0x80E` correspond to the eight Hoenn badges.

## Known limitations

- **Box Pokémon levels** are estimated via the Medium Fast EXP curve (`∛exp`). Species with other growth rates will be off by 1–2 levels.
- **Ability names** are not resolved — would require a species-to-ability mapping table.
- **Location coverage** is partial. Unrecognized map bank/ID pairs fall back to `"Unknown (bank=X, id=Y)"`.
- **Pokédex offsets** (seen/caught) are best-guess for RS and may need adjustment.
- **Emerald and FireRed/LeafGreen** are not supported — offsets differ.

## Dependencies

Python 3.8+, stdlib only (`struct`, `json`, `datetime`, `pathlib`). No pip packages required.
