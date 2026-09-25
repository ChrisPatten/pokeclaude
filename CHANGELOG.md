# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## What counts as the public API

For the purposes of SemVer, PokeClaude's public API is:

- **`parser.parse_save` output schema** — the shape of the JSON dict returned by
  `parser.parse_save.parse()` / printed by `python3 -m parser.parse_save`.
- **`parser.sync` CLI contract** — its flags, the `status` values it returns,
  its process exit codes, and the shape of its JSON stdout payload.
- **`users/<id>/config.json` schema** — the fields a per-user config file must
  have and what they mean.
- **On-disk `saves/` layout** — `saves/<filename>`, `saves/archive/`,
  `saves/snapshots/NNN.json`, and `saves/history.json`.

A change that breaks any of the above is a **major** version bump (while the
project is in `0.x`, it's a **minor** bump instead, per SemVer's pre-1.0
carve-out). Anything else — new fields, new optional flags, internal
refactors, reference-data corrections, new reference files — is **minor** or
**patch** depending on whether it adds capability or just fixes something.

## [Unreleased]

### Added

- **Pokémon Red and Blue (Gen 1) support.** Set `"game": "red"` (or
  `"blue"`) and `"gen": 1` in a trainer's `config.json` and `/sync` works the
  same way it does for Sapphire: party, all 12 PC boxes, the daycare, bag and
  PC items, badges, money, coins, Pokédex counts, rival name, and location.
  The save's checksum is verified, so a corrupt or never-saved file is
  rejected instead of synced. `/diff` tracks each Pokémon across syncs by its
  original trainer ID and DVs (Gen 1 has no personality value).
- Gen 1 reference data in `data/gen_1/`: Pokédex, moves, learnsets, TM/HM
  locations, evolutions, items, wild encounters by version, shops, every gym
  leader / Elite Four / rival team with exact movesets, and the Gen 1 type
  chart — all generated from the pret/pokered decompilation by
  `scripts/build_gen1_data.py`. `data/gen_1/red_blue.md` covers progression,
  HMs, version exclusives, and Gen 1 battle mechanics (Special stat,
  Speed-based crits, the Focus Energy bug, badge boosts, obedience).
- `CLAUDE.md` and the `pokeclaude-sync` skill are generation-aware: Gen 1
  memory files skip natures, abilities, and held items, and move evaluation
  compares Attack against Special instead of reading a nature.
- `python3 -m parser.parse_save` takes `--gen {1,3}`; without it the format
  is detected from the file size. The parsed output has a new
  `save_metadata.generation` field (Gen 3 saves report `3`). If you keep a
  local `tests/fixtures/sapphire.golden.json`, regenerate it once with
  `UPDATE_GOLDEN=1 python3 -m unittest tests.test_parser_golden`.
- `tests/data/gen1_red_ingame.sav`, a save written by Pokémon Red itself, and
  `scripts/make_gen1_test_save.py` to regenerate it.

### Changed

- Archived and rejected save copies keep the trainer's save file extension
  (`.sav` for a Red/Blue trainer). Gen 3 archives are still `.srm`.

## [0.1.0] - 2026-09-25

First tagged release. Everything below shipped together as the project's
starting baseline: daycare parsing, growth-rate-based leveling, shop data,
move-evaluation rules, and the full rewrite of sync into a deterministic CLI.

### Added

- `python3 -m parser.sync <user_id>` — one command that pulls your save from
  your device over `scp`, skips the update if the file hasn't changed
  (compared by MD5), verifies the parsed save's checksums before touching
  anything on disk, and keeps a full history: every save is archived
  (`saves/archive/`), every sync gets a parsed snapshot
  (`saves/snapshots/NNN.json`), and `saves/history.json` tracks the sequence
  (bootstrapped automatically from the old "Save History" table in
  `MEMORY.md` the first time it runs). Prints a single JSON object with a
  status and exit code. `--local <path>` syncs from a file already on disk
  instead of over `scp`; `--diff [--from N] [--to M]` compares two past
  syncs instead of pulling a new one; `--full` prints the complete payload
  instead of the compact default.
- `/diff` now works: `parser/diff.py` compares two saves, matching each
  Pokémon by its personality value (so reordering a box doesn't look like a
  swap), and reports evolutions, catches, releases, level-ups, move changes,
  held-item changes, party/daycare changes, and inventory deltas.
- Per-user `users/<id>/config.json` (device host, save path, SSH key, save
  filename) replaces the old per-user `sync_save.sh` script. Added
  `config.example.json` and `.mcp.json.example` as copy-and-fill templates.
- Every parsed Pokémon — in the party, in boxes, and in the daycare — now
  includes its personality value (`pid`), both of its types, a resolved
  ability name (this previously always reported "Unknown"), its current
  experience total, and a plain-language nature effect (e.g. "Atk↑,
  SpAtk↓").
- Boxed and daycare Pokémon's moves now include type and PP, matching what
  party moves already showed.
- Location data now reports whether the current map is a recognized one,
  with a warning when it isn't.
- Added `parser/data/species_info.json` (species types and abilities) and
  `scripts/build_species_info.py` to regenerate it from the Pokédex
  reference file, plus `scripts/verify_data_vs_pokeruby.py` and
  `scripts/verify_golden.py` to cross-check parser output and reference data
  against the pret/pokeruby decompilation.
- Added a unittest suite covering the parser, the diff logic, and the sync
  CLI, including a golden-output test that runs against a real save file
  fixture (gitignored, and skipped automatically when that fixture isn't
  present).

### Changed

- Syncing no longer works by having an agent read an MD5 out of a Markdown
  table and shell out to `scp` step by step — it's a single deterministic
  command, and the `pokeclaude-sync` skill just reads its JSON output.
- The `pokeclaude-sync` skill is now version-controlled, works for any
  trainer without a hardcoded user ID or file paths, and runs on agentbus
  instead of the Telegram plugin.
- Corrected the game-data file path referenced in `CLAUDE.md`.
- Sync output is about 50% smaller — boxed Pokémon are summarized in
  stdout, with the full data kept in the per-sync snapshot; pass `--full`
  to print everything. The sync payload also now includes the local
  `date` and the `snapshot` path.

### Fixed

- Save checksum validation is real now: each save section's checksum is
  checked against its expected size (0x890 / 0xF80 / 0x7D0 bytes) with a
  signature check, and a corrupted or uninitialized save block now falls
  back to the other block instead of being silently trusted — previously
  `checksum_valid` was hardcoded to `true` no matter what. A save where
  neither block is valid now fails the sync instead of proceeding with bad
  data.
- Corrected growth-rate data for 30 Hoenn species — including Milotic,
  Flygon, the Duskull and Dusclops line, Anorith and Armaldo, and Swablu and
  Altaria — that had the wrong leveling curve.
- Boxed Pokémon levels are now computed from each species' real growth
  rate; previously every boxed Pokémon used a cube-root/medium-fast
  approximation no matter what it actually was, so boxed levels could be
  off.
- Box data no longer reads past the end of each 3968-byte box section into
  padding bytes.
- The `scp` remote save path is no longer wrapped in quotes, which broke
  pulls under modern SFTP-mode `scp` (OpenSSH 9.0+, including the macOS
  default) — quoting made the literal quote characters part of the
  filename instead of protecting spaces in it.
- Reference data: Volbeat/Illumise and Plusle/Minun are available in both
  Ruby and Sapphire, not version-exclusive as previously listed — only
  their encounter rates are swapped between the two versions. Plusle and
  Minun were also listed with their Route 110 encounter rates reversed.
- Ability resolution: the species ability table had ability 1 and ability 2
  in the wrong order for about 90 species (verified against the
  pret/pokeruby decompilation), so Pokémon could be reported with their
  other ability. Example: Azumarill with Huge Power was reported as Thick
  Fat. Also "Compoundeyes" → "Compound Eyes".
- Type/ability data for the unused "old Unown" species slots corrected to
  match the game.
- Boxed/daycare levels changed for species whose growth rate was wrong. For
  example, a daycare Baltoy previously shown as Lv. 22 is actually Lv. 20.
  Previously synced memory notes may show the old levels until the next
  sync.

### Removed

- `sync.sh`, the `sync-save` subagent, `start.sh`/`start_pokeclaude.sh`, and
  the per-user `sync_save.sh` — syncing now runs through `parser.sync`, and
  the bot process itself is managed by agentbus.

[Unreleased]: https://github.com/ChrisPatten/pokeclaude/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ChrisPatten/pokeclaude/releases/tag/v0.1.0
