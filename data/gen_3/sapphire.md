# Pokémon Sapphire (GBA)

## Supporting Files

`grep` these files for quick reference:

- `./abilities_gen3.md` — Gen 3 abilities, effects, Pokémon with the ability
- `./items_gen3.md` — Gen 3 items, effects, prices, locations
- `./pokedex_gen3.md` — Gen 3 Pokémon, types, stats, abilities
- `./evolution_gen3.md` — Gen 3 evolution chains, methods
- `./moves_gen3.md` — Gen 3 moves, types, categories, power, accuracy, PP, effects
- `./tmhm_gen3.md` — Gen 3 TM/HM numbers, moves, locations
- `./learnsets_gen3.md` — Gen 3 Pokémon learnsets by level, TM/HM, Move Tutor, breeding
- `./natures_gen3.md` — Gen 3 natures, stat modifiers, flavor likes/dislikes

## Gym Leaders

| # | Leader | Location | Type | Key Pokémon | Badge |
|---|--------|----------|------|-------------|-------|
| 1 | Roxanne | Rustboro City | Rock | Nosepass (Lv. 15) | Stone Badge |
| 2 | Brawly | Dewford Town | Fighting | Hariyama (Lv. 18) | Knuckle Badge |
| 3 | Wattson | Mauville City | Electric | Manectric (Lv. 24) | Dynamo Badge |
| 4 | Flannery | Lavaridge Town | Fire | Torkoal (Lv. 29) | Heat Badge |
| 5 | Norman | Petalburg City | Normal | Slaking (Lv. 31) | Balance Badge |
| 6 | Winona | Fortree City | Flying | Altaria (Lv. 33) | Feather Badge |
| 7 | Tate & Liza | Mossdeep City | Psychic | Solrock/Lunatone (Lv. 42) | Mind Badge |
| 8 | Juan | Sootopolis City | Water | Kingdra (Lv. 46) | Rain Badge |

## Routes & Progression

- **Route 113**: Ash-covered route east of Fallarbor; Soot Sack collects ash for glass flutes
- **Route 114**: Connects Fallarbor Town to Meteor Falls; Swablu, Seviper encounters
- **Route 115**: North of Rustboro, beach area; Swablu encounters
- **Meteor Falls**: Cave between Route 114 and Route 116; Lunatone (Sapphire-exclusive); Steven encounter
- **Mt. Chimney**: Accessed via cable car on Route 112; Team Magma event with meteorite
- **Jagged Pass**: Connects Mt. Chimney to Lavaridge Town; requires Acro Bike for some items
- **Lavaridge Town**: Hot springs; Flannery's gym; Move Tutor (Fire Stone purchaseable)

## Move Tutor Locations

- **Fallarbor Town**: Move Tutor teaches moves for shards (Red, Blue, Yellow, Green shards found in the field)

## Key Items

- **Itemfinder**: Given by rival (May/Brendan) on Route 110 after battling them; required to find hidden items. Use from Key Items — chimes and character faces direction of nearest hidden item; press A when adjacent (not on top of it).

## Berries & RTC

- Berry regrowth at soil patches requires RTC (real-time clock) to be active and set correctly in mGBA
- Berries don't sell for significant money — value is in the berry itself (held items, PokeBlocks)
- High-value berries to plant/collect: Lum (cures any status), Sitrus (HP restore), Salac/Petaya/etc. (stat boost at low HP)

## Type Chart (Gen 3 — Offensive)

When a move of this type is used, damage is multiplied as shown.

| Attacking Type | 2× (super effective) | 0.5× (not very effective) | 0× (immune) |
|---|---|---|---|
| Normal | — | Rock, Steel | Ghost |
| Fighting | Normal, Rock, Steel, Ice, Dark | Flying, Psychic, Bug | Ghost |
| Flying | Fighting, Bug, Grass | Rock, Steel, Electric | — |
| Poison | Grass | Poison, Ground, Rock, Ghost | Steel |
| Ground | Poison, Rock, Steel, Fire, Electric | Grass, Bug | Flying |
| Rock | Flying, Bug, Fire, Ice | Fighting, Ground, Steel | — |
| Bug | Grass, Psychic, Dark | Fighting, Flying, Poison, Ghost, Steel, Fire | — |
| Ghost | Ghost, Psychic | — | Normal, Dark |
| Steel | Rock, Ice | Steel, Fire, Water, Grass | — |
| Fire | Grass, Ice, Bug, Steel | Rock, Fire, Water, Dragon | — |
| Water | Fire, Ground, Rock | Water, Grass, Dragon | — |
| Grass | Water, Ground, Rock | Flying, Poison, Bug, Steel, Fire, Dragon, Grass | — |
| Electric | Flying, Water | Grass, Electric, Dragon | Ground |
| Psychic | Fighting, Poison | Steel, Psychic | Dark |
| Ice | Flying, Ground, Grass, Dragon | Steel, Fire, Water, Ice | — |
| Dragon | Dragon | Steel | — |
| Dark | Ghost, Psychic | Dark, Steel | — |

Source: Bulbapedia — Gen 3 type chart (no Fairy type in Gen 3)

## Strategy

### HMs in Battle
Avoid teaching field HMs to battle Pokémon. Exceptions: Surf (best Water attack in game). Dig stall with Toxic + Mean Look/Block is acceptable.

- **HM01 Cut**: Low base power, poor accuracy. Replace with Body Slam, Return, or Tri-Attack.
- **HM02 Fly**: Gives opponent a free switch turn to a Rock or Electric type. Poor accuracy. Replace with Aerial Ace, Wing Attack, or Air Cutter.
- **HM07 Waterfall**: Less damage than Surf, no secondary effect. Use Surf.
- **HM08 Dive**: Gives opponent a free switch. Use Surf.
- **TM29 Dig**: Opponent can switch in a Flying type, or counter with Earthquake. Replace with Earthquake or Mud Shot.

### STAB
Same Type Attack Bonus: 1.5× damage when move type matches the user's type. Applies to all types including Normal. Always prioritize STAB moves when coverage allows.

Best moves by category:

**Physical (Attack stat):** Normal → Body Slam/Return/Frustration | Fighting → Cross Chop/Brick Break | Poison → Sludge Bomb | Ground → Earthquake | Flying → Drill Peck/Wing Attack/Aerial Ace | Rock → Rock Slide | Bug → Megahorn/Silver Wind | Ghost → Shadow Ball | Steel → Iron Tail/Meteor Mash/Metal Claw

**Special (Sp. Atk stat):** Fire → Flamethrower | Water → Surf | Electric → Thunderbolt | Grass → Giga Drain/Razor Leaf/Magical Leaf | Ice → Ice Beam | Psychic → Psychic | Dragon → Dragon Claw/Dragonbreath | Dark → Crunch

Physical attacks are Normal/Fighting/Flying/Poison/Ground/Rock/Bug/Ghost/Steel. Special attacks are Fire/Water/Electric/Grass/Psychic/Dark/Ice/Dragon. Teach Special Attacks only to high Sp. Atk Pokémon and vice versa.

### Move Coverage
Avoid two moves of the same type on one Pokémon. Maximize types covered for maximum matchup coverage. Always include 2+ damaging moves — pure support movesets lack KO power.

### Support Moves & Hazers
Include at least one non-damaging move per Pokémon when viable: Toxic, Thunder Wave, Calm Mind, Bulk Up, Roar, Whirlwind.

At least one **hazer or pseudohazer** recommended per team. Haze eliminates all stat changes for both Pokémon. Roar/Whirlwind force an opponent to switch, removing their boosts. Counters Calm Mind, Double Team, Amnesia strats.

### Evolution Timing
Delay evolution (Everstone or B button) to learn moves earlier. Example: Mudkip learns Protect at Lv. 37; Marshtomp at 42; Swampert at 46. Check learnset before evolving. Note that some moves are only learnable post-evolution.

### Status Conditions
- **Paralysis**: 25% chance opponent cannot move; Speed reduced to 1/4.
- **Sleep**: Cannot attack; Snore/Sleep Talk usable while asleep; enables Dream Eater/Nightmare.
- **Poison**: 1/16 HP lost per turn. Toxic poison doubles damage each turn.
- **Burn**: Attack and Defense drop; HP lost per turn.
- **Freeze**: Cannot move until thawed. Sunny Day or Flame Wheel thaws.
- **Confusion**: 50% chance to hit self for 40 base damage per turn. Cleared by switching.
- **Attract**: 50% chance opponent doesn't attack. Requires opposite gender.

## Catching

### General
- Get target to 1 HP (False Swipe) and inflict Sleep or Paralysis before throwing balls.
- Use Ultra Balls or Timer Balls (Timer Balls more effective as turns increase).
- Wobbuffet as lead: Shadow Tag prevents wild Pokémon from fleeing — essential for Latias/Latios.

### Latias/Latios
Latias roams Hoenn in Sapphire (Latios in Ruby). Use Wobbuffet or Wynaut (Shadow Tag ability) — without Shadow Tag they flee every turn. Can use Repel + Acro Bike in grass to increase encounter rate. Track with Pokédex after first encounter.

### Groudon/Kyogre
Reduce to 1 HP with False Swipe. Apply Sleep or Paralysis. Throw Ultra Balls or Timer Balls repeatedly — may take 20+. Master Ball is always an option.

## Mechanics

- **Wonder Guard (Shedinja)**: Only super-effective moves deal damage; any status, weather, or indirect damage still KOs it
- **Macho Brace**: Halves Speed in battle; do not use in fights
- **Silk Scarf**: Boosts Normal-type moves ×1.1; no effect on Flying or Steel moves
- **Miracle Seed**: Boosts Grass-type moves ×1.1
- **Soft Sand**: Boosts Ground-type moves ×1.1

## Wild Encounters (Pokémon Sapphire)

Version exclusives relevant to Sapphire: Lotad/Lombre/Ludicolo, Seviper, Lunatone, Sableye, Illumise, Minun — all catchable in Sapphire. Ruby exclusives NOT in Sapphire wild: Seedot/Nuzleaf/Shiftry, Zangoose, Solrock, Mawile, Volbeat, Plusle.

Note: Seedot does appear on Route 102/117/120 as a swarm-only (requires record mixing with Emerald). Surskit is available in Sapphire on Routes 102, 111, 114, 117, 120.

Fishing rod tiers: Old Rod = Magikarp/Tentacool/Goldeen only. Good Rod = better variety. Super Rod = highest-level, best species.

Underwater (Dive) encounters only on Routes 124, 126; Seafloor Cavern approach handled via Route 128.
