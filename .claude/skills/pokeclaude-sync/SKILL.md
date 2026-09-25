---
name: pokeclaude-sync
description: Pull the latest save from the trainer's device, parse it, update all three memory files, and reply with a team snapshot. Invoke when the trainer says /sync, "sync my save", or asks to check their current team/progress.
---

# PokeClaude Sync

All the deterministic work — pull, dedupe, checksum, archive, parse, diff — lives in one command. This skill's job is to interpret its JSON output and update memory in the field-dex voice.

Determine `<user_id>`: the Telegram user id of whoever sent the incoming message. Never hardcode it.

---

## Step 1 — Run the sync

From the project root:

```bash
python3 -m parser.sync <user_id>
```

Output is one JSON object on stdout. Parse it and branch on `status`:

| status | Reply, then stop | Continue? |
|---|---|---|
| `pull_failed` | "Can't reach the device — is it on and connected to Tailscale?" | No |
| `invalid_save` | "Latest save failed validation. Kept the last good sync." | No |
| `unchanged` | "Save unchanged since last sync — nothing new." | No |
| `error` | Surface the `error` field plainly. | No |
| `synced` | — | Yes, go to Step 2 |

---

## Step 2 — Read the payload

`save` (the full parsed save) is ground truth. `diff` (`null` on a trainer's first sync) is the delta from the previous snapshot — use it to decide *what changed* and *what to write*, not `save` alone.

`save` mons already carry `types`, `ability`, and `nature_effect` resolved — never look these up or recompute them.

`save.boxes` mons are compact by default (slot, pid, species_name, nickname if non-default, level, types, ability, nature, nature_effect, held_item, `moves` as name strings, is_egg) — no move ids/pp/type-per-move/experience/species_id. This is enough for Steps 3–4. If you need a box mon's full detail, the full parsed save is at the path in the outer JSON's `snapshot` field.

Useful `diff` fields: `party.added/removed/changed` (`changed[].changes` includes `evolved`, `leveled_up`, `moves_changed`, `held_item_changed`, `nickname_changed`), `caught`, `released_or_traded`, `evolved`, `leveled`, `moves_changed` (`{learned, forgot}`), `held_items_changed`, `daycare` (`null` unless membership changed), `badges_gained`, `location`, `inventory` (per-pocket `added/removed/changed`).

If `save.warnings` is non-empty, or `save.location.known` is `false`, plan one flag line for Step 6 (e.g. a block checksum fallback, or an unrecognized map).

---

## Step 3 — Update MEMORY.md

Read `users/<user_id>/memory/MEMORY.md`. Update in place; **preserve all strategic notes, team analysis, and preferences** unless new data directly contradicts them.

**Header:** playtime, money, Pokédex caught — from `save.trainer` / `save.pokedex`.

**Current Status:** location from `save.location.name`; badge count from `save.badges.count`. If `diff.badges_gained` is non-empty, update "Next gym" (Roxanne→Brawly→Wattson→Flannery→Norman→Winona→Tate & Liza→Wallace→Elite Four).

**Current Party:** rebuild from `save.party`:
```
### <N>. <Species> — Lv. <X> | <Type(s)> | <Nature> (<nature_effect>)
- **Moves:** <move names>
- **Held:** <item or None>
- **Notes:** <keep existing notes if unchanged; write fresh notes if new/evolved/significantly changed>
```
Eggs: `### <N>. [EGG] <species> — steps remaining unknown`. For any pid in `diff.party.changed` tagged `evolved`, replace its notes — don't keep pre-evolution commentary. For `moves_changed` entries, check each learned move against CLAUDE.md's Move Evaluation checks (category, STAB, effectiveness, nature) before recommending it stays or replaces something.

**Daycare:** from `save.daycare`; `_Empty._` if none. Only rewrite notes if `diff.daycare` is non-null.

**Boxed — Notable:** keep notes for mons still boxed. Drop entries whose pid is in `diff.released_or_traded`. For each pid in `diff.caught` now sitting in a box, assess for a new entry: evolved/near-evolving, good nature for its role, HM user, high-level standout — skip filler.

**Save History:** append one row using the outer JSON's `sync_number`, `date`, and `md5` (not anything from `diff`):
```
| <sync_number> | <date> | <save.location.name> | <save.badges.count>/8 | <md5> |
```
`history.json` (written by `parser.sync` itself) is the machine source of truth for this data — this row is only for human readability.

**Do NOT modify:** Team Analysis, Preferences, Key Fossil, Pokédex Catchable Gaps.

---

## Step 4 — Rewrite box.md

Fully replace `users/<user_id>/memory/box.md` from `save.boxes`:
```markdown
# Box Contents — <trainer name>

## Box <N> (<count> Pokémon)

| Slot | Species | Lv | Nature | Moves | Notes |
|------|---------|-----|--------|-------|-------|

## Box Highlights

**Worth monitoring:**
- **<Species> (Lv. X, Nature):** <one-line note>
```
Highlights only for strategic value; otherwise a one-line factual note (typing, ability, evolution stage). Skip obvious filler.

---

## Step 5 — Rewrite inventory.md

Fully replace `users/<user_id>/memory/inventory.md` from `save.inventory`:
```markdown
# Inventory — <trainer name> (<user_id>)

_Last updated: Sync #<sync_number> — <location> (<date>)_

## Held Items (Party)
| Pokémon | Held Item | Notes |

## Items
| Item | Qty | Notes |

## Berries
| Berry | Qty | Effect |

## TMs / HMs
| TM/HM | Move | Notes |

## Key Items
- <item>

## PC Storage
- <item> ×<qty>
```
Use `diff.inventory` to flag what's new: unused TMs with an obvious recipient, held items worth swapping, items already mentioned to the trainer but not acted on.

---

## Step 6 — Reply

1. **Location** + badge count
2. **Party** — one line per mon: species, level, brief note if changed or notable
3. **Team eval** — 1–2 sentences on current strength and the next challenge
4. **Flags** — 2–3 most important items (new mon, notable move change, item situation, upcoming threat, any warning from Step 2)

No full diff unless the trainer asks `/diff`. No recap of what the sync did.
