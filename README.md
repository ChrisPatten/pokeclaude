# PokeClaude

A Pokémon companion bot for players working through GBA-era Pokémon games. Connects to your emulator's save file, parses it, and gives you a real-time Pokédex-style assistant — team analysis, upcoming threats, move coverage, and more.

Built on [Claude Code](https://claude.ai/code) running as a Telegram bot.

---

## Features

- **Save file ingestion** — syncs `.srm` files directly from your emulator, parses party, boxes, inventory, badges, and location
- **Persistent memory** — remembers your team, decisions, and playthrough history across sessions
- **Team analysis** — proactive suggestions on coverage gaps, upcoming gym matchups, and move improvements
- **Slash commands** — `/team`, `/badges`, `/tips`, `/diff`, `/find`, `/move`, `/mon`
- **Natural language** — ask anything; slash commands are just shortcuts
- **Multi-user** — each Telegram user gets isolated save data and memory

---

## Architecture

```
pokeclaudebot/
├── CLAUDE.md               — agent instructions (identity, memory system, commands)
├── .mcp.json.example       — agentbus MCP server config template (copy to .mcp.json)
├── config.example.json     — per-user config.json template
├── .claude/
│   └── skills/
│       └── pokeclaude-sync/SKILL.md  — interprets `parser.sync` output, updates memory
├── parser/                 — Gen III save file parser (Ruby/Sapphire .srm → JSON)
│   ├── parse_save.py       — entry point: reads a .srm, returns the parsed dict
│   ├── decode.py           — sector I/O, checksum, XOR decryption, string encoding
│   ├── trainer.py          — trainer info, badges, location, inventory
│   ├── pokemon.py          — party, PC box, and daycare parsing
│   ├── data_loader.py      — cached loaders for parser/data/*.json
│   ├── sync.py             — CLI: pull, dedupe, checksum, archive, snapshot, diff
│   ├── diff.py             — pure function: diff two parsed snapshots
│   └── data/               — JSON lookup tables (species, species_info, moves, items, natures, growth_rates, etc.)
├── scripts/
│   └── build_species_info.py  — builds parser/data/species_info.json from data/gen_3/pokedex_gen3.md
├── tests/                  — unittest suite (see Testing below)
├── data/                   — accumulated game reference data
│   └── gen_3/
│       ├── sapphire.md     — gym leaders, routes, strategy notes; Supporting Files index
│       ├── moves_gen3.md   — move details (power, accuracy, PP, type, effect)
│       ├── learnsets_gen3.md
│       ├── tmhm_gen3.md
│       ├── pokedex_gen3.md
│       ├── evolution_gen3.md
│       ├── abilities_gen3.md
│       ├── items_gen3.md
│       └── catch_locations_gen3.md
└── users/                  — per-user data (gitignored)
    └── <telegram_user_id>/
        ├── config.json     — game, save filename, device host/path/ssh key
        ├── saves/          — latest save, archive/, snapshots/, history.json
        └── memory/
            ├── MEMORY.md
            ├── box.md
            └── inventory.md
```

The agent is Claude Code itself — `CLAUDE.md` is the system prompt. There is no separate bot runtime handling Telegram; the bot process is launched and supervised by **agentbus**, an MCP server configured in `.mcp.json` (see `.mcp.json.example`), which also carries the incoming Telegram user id that identifies which trainer is messaging.

---

## Requirements

- [Claude Code](https://claude.ai/code) (CLI or desktop app)
- **agentbus** — the MCP server that launches and supervises the bot and bridges Telegram; holds the bot token and access policy in its own config
- A Telegram bot token (registered with agentbus)
- Python 3.11 (for the save parser — stdlib only, no pip packages)
- A device or emulator producing `.srm` save files, reachable over `scp` (a TrimUI-style handheld over Tailscale, or a local emulator save directory)

---

## Configuring a New Instance

### 1. Clone the repo

```bash
git clone <repo-url>
cd pokeclaudebot
```

### 2. Create a Telegram bot

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy the bot token you receive

### 3. Configure agentbus

Copy the MCP config template and fill in your paths:

```bash
cp .mcp.json.example .mcp.json
```

`.mcp.json` points Claude Code at your agentbus checkout (`args`) and its config file (`AGENTBUS_CONFIG` env var). The bot token and Telegram access policy — who is allowed to message the bot — live in agentbus's own config, not in this repo; see agentbus's docs to register the token and approve your Telegram account (and anyone else you want to allow). `.mcp.json` is gitignored since it carries machine-specific absolute paths.

### 4. Set up a user

For each player, create their config and directory scaffold:

```bash
mkdir -p users/<telegram_user_id>/{saves,memory}
cp config.example.json users/<telegram_user_id>/config.json
```

Replace `<telegram_user_id>` with their numeric Telegram user ID (from [@userinfobot](https://t.me/userinfobot) or the first message the bot receives). Edit `config.json`:

```jsonc
{
  "game": "sapphire",
  "gen": 3,
  "save_filename": "sapphire.srm",
  "device": {
    "host": "user@100.x.x.x",       // SSH/Tailscale address of the device
    "save_path": "/path/to/save.srm",
    "ssh_key": "trimui_key"         // relative to this user's directory
  }
}
```

Drop the matching private SSH key alongside it as `users/<telegram_user_id>/trimui_key` (or whatever name `ssh_key` points to), and make sure the device accepts it for passwordless `scp` — a Tailscale IP for `host` keeps this working over the internet without exposing the device. `users/` is gitignored, so config and keys never get committed.

### 5. Bootstrap memory

Create an initial `users/<telegram_user_id>/memory/MEMORY.md`. A minimal starting file:

```markdown
# Trainer

**Name:** [trainer name]
**Game:** Pokémon Sapphire
**Playtime:** 0h 0m

## Badges
None yet.

## Party
Not yet synced.

## Save History
| Date | MD5 | Notes |
|------|-----|-------|
```

### 6. Verify sync end to end

Run the sync CLI directly once to confirm the SSH key, device path, and parser all work together:

```bash
python3 -m parser.sync <telegram_user_id>
```

This pulls the save over `scp`, checksums it, parses it, and prints one JSON object with `"status": "synced"` (or `"unchanged"` if it matches an existing sync). To test against a save file already on disk instead of pulling over SSH, use `--local`:

```bash
python3 -m parser.sync <telegram_user_id> --local path/to/save.srm
```

You can also run the parser alone against any `.srm` file to sanity-check it in isolation:

```bash
python3 -m parser.parse_save path/to/save.srm
```

### 7. Start chatting

Message your bot on Telegram. Ask it to sync your save:

> "sync my save"

The `pokeclaude-sync` skill runs `python3 -m parser.sync <user_id>`, reads the resulting JSON, updates `MEMORY.md`/`box.md`/`inventory.md`, and replies with your current location, party snapshot, and any flagged tips. Ask "what changed" or send `/diff` for a full diff against the previous sync (`python3 -m parser.sync <user_id> --diff`).

---

## Testing

```bash
python3 -m unittest discover -s tests -v
```

Most tests run against synthetic fixtures and need no setup. The golden test (`tests/test_parser_golden.py`) additionally needs a real save at `tests/fixtures/sapphire.srm` plus a matching `tests/fixtures/sapphire.golden.json` — both gitignored — and is skipped automatically when they're absent. Regenerate the golden file after an intentional parser change:

```bash
UPDATE_GOLDEN=1 python3 -m unittest tests.test_parser_golden
```

`scripts/build_species_info.py` regenerates `parser/data/species_info.json` (species types/abilities, keyed by internal Gen 3 species id) from `data/gen_3/pokedex_gen3.md`; run it after that reference file changes. `scripts/verify_data_vs_pokeruby.py` cross-checks that data against the pret/pokeruby decompilation and can `--fix` mismatches. See [`parser/README.md`](parser/README.md) for details on both.

---

## Environment Variables

If you use `direnv` or a `.envrc`, that file is gitignored. No environment variables are required by default — bot credentials and access policy live in agentbus's own config, not in this repo.

---

## Parser

See [`parser/README.md`](parser/README.md) for full documentation of the save file parser, including output schema, architecture, and known limitations.

Currently supports: **Pokémon Ruby / Sapphire** (`.srm`)
Not yet supported: Emerald, FireRed/LeafGreen (different offsets)

---

## Game Data

Game reference data lives in `data/<gen_#>/`. Each generation has a main game file (e.g. `data/gen_3/sapphire.md`) with gym leaders, routes, and strategy notes, plus a set of grep-optimized reference files for moves, learnsets, TM/HMs, Pokédex entries, evolutions, abilities, items, and catch locations.

Every line in the reference files is self-contained — a keyword grep returns all relevant data with no further parsing needed. The agent greps these files before going to the web, and appends any new facts it fetches back into the appropriate file. These are committed to the repo so nothing needs to be re-fetched across sessions.

---

## Multi-User Notes

- Each user's data is fully isolated under `users/<telegram_user_id>/`
- The `users/` directory is gitignored — save files and memory are never committed
- The agent routes to the correct user's files based on Telegram user ID from the incoming message

---

## Versioning & releases

PokeClaude follows [Semantic Versioning](https://semver.org/); the current
version is in `VERSION` and `parser.__version__` reads it directly. See
[`CHANGELOG.md`](CHANGELOG.md) for the release history and exactly what
counts as the public API for versioning purposes (the parser's JSON output,
the `parser.sync` CLI, `config.json`, and the on-disk `saves/` layout).

Every push to `main` and every pull request runs the test suite via GitHub
Actions (`.github/workflows/ci.yml`). Pushing a `vX.Y.Z` tag publishes a
GitHub release with that version's changelog section as its notes
(`.github/workflows/release.yml`). See [`docs/RELEASING.md`](docs/RELEASING.md)
for the full release process.
