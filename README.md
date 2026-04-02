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
├── sync.sh                 — entry point for save sync; delegates to sync-save subagent
├── start_pokeclaude.sh     — launches Claude Code in the correct working directory
├── parser/                 — Gen III save file parser (Ruby/Sapphire .srm → JSON)
│   ├── parse_save.py       — entry point
│   ├── decode.py           — sector I/O, checksum, XOR decryption, string encoding
│   ├── trainer.py          — trainer info, badges, location, inventory
│   ├── pokemon.py          — party and PC box parsing
│   └── data/               — JSON lookup tables (species, moves, items, natures, etc.)
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
        ├── sync_save.sh
        ├── saves/
        └── memory/
            ├── MEMORY.md
            ├── box.md
            └── inventory.md
```

The agent is Claude Code itself — `CLAUDE.md` is the system prompt. There is no separate bot runtime; Claude Code handles the Telegram integration via the built-in Telegram channel.

---

## Requirements

- [Claude Code](https://claude.ai/code) (CLI or desktop app)
- A Telegram bot token
- Python 3.8+ (for the save parser — stdlib only, no pip packages)
- A GBA emulator that produces `.srm` save files (mGBA recommended)

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

### 3. Connect Telegram to Claude Code

In your Claude Code session, run the Telegram configuration skill:

```
/telegram:configure
```

Paste your bot token when prompted. This saves the token to the Claude Code channel configuration.

Then set access policy — who is allowed to message the bot:

```
/telegram:access
```

Approve your own Telegram account (or others you want to allow). By default the bot is locked down; no one can reach it until explicitly approved.

### 4. Set up user directories

For each player, create their directory scaffold:

```bash
mkdir -p users/<telegram_user_id>/saves
mkdir -p users/<telegram_user_id>/memory
```

Replace `<telegram_user_id>` with their numeric Telegram user ID (you can get this from [@userinfobot](https://t.me/userinfobot) or from the first message the bot receives).

### 5. Create sync_save.sh

Each user needs a script that copies their emulator save to `users/<id>/saves/`. Example for mGBA on macOS:

```bash
#!/bin/bash
# users/<telegram_user_id>/sync_save.sh
cp ~/Library/Application\ Support/mGBA/saves/pokemon_sapphire.srm \
   "$(dirname "$0")/saves/sapphire.srm"
```

Make it executable:

```bash
chmod +x users/<telegram_user_id>/sync_save.sh
```

Adjust the source path to match your emulator and OS.

### 6. Bootstrap memory

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

### 7. Verify the parser

Test the save parser against a real save file:

```bash
python3 -m parser.parse_save users/<telegram_user_id>/saves/sapphire.srm
```

You should see JSON with trainer name, party, badges, and location.

### 8. Start chatting

Message your bot on Telegram. Ask it to sync your save:

> "sync my save"

It will run `sync_save.sh`, parse the file, and reply with your current location, party snapshot, and any flagged tips.

---

## Environment Variables

If you use `direnv` or a `.envrc`, that file is gitignored. No environment variables are required by default — the bot token is stored in Claude Code's channel configuration, not in the repo.

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
