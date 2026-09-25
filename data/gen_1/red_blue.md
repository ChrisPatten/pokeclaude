# Pokémon Red / Blue (Game Boy)

Red and Blue share one save format, map, and story. They differ only in wild/prize Pokémon (see Version Exclusives). Mechanics below are Gen 1-specific and verified against the pret/pokered decompilation.

## Supporting Files

`grep` these files for quick reference. All except this file are generated from pret/pokered by `scripts/build_gen1_data.py`.

- `./pokedex_gen1.md` — Pokémon, types, base stats (HP/Atk/Def/Spd/Spc), catch rate, base EXP, growth rate
- `./moves_gen1.md` — moves with Gen 1 type, category, power, accuracy, PP, TM/HM number, Gen 1 effect
- `./learnsets_gen1.md` — level-up moves (L1 = starting moves) and TM/HM compatibility
- `./tmhm_gen1.md` — TM/HM numbers, moves, prices, every location (item ball, gift, mart, Game Corner)
- `./evolution_gen1.md` — evolution chains and methods
- `./items_gen1.md` — items, prices, effects, every location (item ball, hidden, gift, mart)
- `./catch_locations_gen1.md` — wild encounters per area with level ranges and rates (Red vs Blue), fishing, gifts, static encounters, in-game trades, Game Corner prizes, fossils
- `./shops_gen1.md` — Poké Mart and Dept. Store inventories with prices, Game Corner prizes
- `./trainers_gen1.md` — every Gym Leader, Elite Four, rival, and Giovanni team with exact movesets
- `./type_chart_gen1.md` — Gen 1 type chart, attacking and defending views

No abilities, natures, held items, breeding, or Dark/Steel types exist in Gen 1.

## Gym Leaders

| # | Leader | Location | Type | Ace | Badge | Reward | Badge effect |
|---|--------|----------|------|-----|-------|--------|--------------|
| 1 | Brock | Pewter City | Rock | Onix Lv14 (Bide) | Boulder | TM34 Bide | Attack ×1.125 in battle; Flash usable |
| 2 | Misty | Cerulean City | Water | Starmie Lv21 (Bubble Beam) | Cascade | TM11 Bubble Beam | Traded Pokémon obey to Lv30; Cut usable |
| 3 | Lt. Surge | Vermilion City | Electric | Raichu Lv24 (Thunderbolt) | Thunder | TM24 Thunderbolt | Defense ×1.125; Fly usable |
| 4 | Erika | Celadon City | Grass | Vileplume Lv29 (Mega Drain) | Rainbow | TM21 Mega Drain | Obey to Lv50; Strength usable |
| 5 | Koga | Fuchsia City | Poison | Weezing Lv43 (Toxic, Self-Destruct) | Soul | TM06 Toxic | Speed ×1.125; Surf usable |
| 6 | Sabrina | Saffron City | Psychic | Alakazam Lv43 (Psywave, Recover) | Marsh | TM46 Psywave | Obey to Lv70 |
| 7 | Blaine | Cinnabar Island | Fire | Arcanine Lv47 (Fire Blast) | Volcano | TM38 Fire Blast | Special ×1.125 |
| 8 | Giovanni | Viridian City | Ground | Rhydon Lv50 (Fissure) | Earth | TM27 Fissure | All traded Pokémon obey |

Full teams and movesets: `grep "Trainer:<Name>" trainers_gen1.md`.

- Lt. Surge's gym is behind a Cut tree. The trash-can switch puzzle re-randomizes the second switch on a miss.
- Koga, Sabrina, and Blaine can be done in any order after Erika. Blaine needs Surf and the Secret Key (Pokémon Mansion B1F). Giovanni's gym opens after the other seven badges.
- Sabrina's Kadabra and Alakazam: Psychic has no real counter in Gen 1. Bug is its only weakness and Gen 1 Bug moves are weak. Ghost moves do nothing to Psychic.

## Elite Four & Champion

| Order | Trainer | Types | Ace | Notable |
|---|---|---|---|---|
| 1 | Lorelei | Ice/Water | Lapras Lv56 (Blizzard, Hydro Pump) | Cloyster, Dewgong, Jynx, Slowbro (Amnesia). Electric hits four of five 2x; Jynx is the exception. |
| 2 | Bruno | Fighting/Rock | Machamp Lv58 (Fissure) | Two Onix, Hitmonlee, Hitmonchan. Water/Grass for Onix, Psychic for the rest. |
| 3 | Agatha | Ghost/Poison | Gengar Lv60 (Toxic, Hypnosis, Dream Eater) | Every Ghost is part Poison — Psychic and Ground hit them 2x. Golbat, Arbok. |
| 4 | Lance | Dragon/Flying | Dragonite Lv62 (Barrier, Hyper Beam) | Gyarados, 2 Dragonair, Aerodactyl. Ice: 4x Dragonite, 2x Dragonair and Aerodactyl, 1x Gyarados. Electric: 4x Gyarados. |
| 5 | Rival (Champion) | Mixed | Starter Lv65 | Pidgeot (Sky Attack), Alakazam, Rhydon, Exeggutor/Gyarados/Arcanine per starter. |

No healing between Elite Four battles except items. The Indigo Plateau Lobby mart sells Full Restore, Max Potion, Revive, Ultra Ball.

## Rival Encounters

The rival takes the starter strong against yours. Teams per encounter: `grep "Trainer:Rival" trainers_gen1.md`.

1. Oak's Lab (Lv5) → 2. Route 22 (optional, Lv8-9) → 3. Cerulean City north bridge (Lv15-18) → 4. S.S. Anne 2F (Lv16-20) → 5. Pokémon Tower 2F (Lv20-25) → 6. Silph Co. 7F (Lv35-40) → 7. Route 22 before Victory Road (Lv45-53) → 8. Champion (Lv59-65).

## Progression

| Step | Area | Gate / requirement | Notes |
|---|---|---|---|
| 1 | Pallet Town → Route 1 → Viridian City | — | Deliver Oak's Parcel (from Viridian Mart) to get the Pokédex; Viridian Mart then opens. |
| 2 | Route 2 → Viridian Forest → Pewter City | — | Brock. Rock resists Normal/Fire/Flying; Water/Grass/Fighting/Ground win. |
| 3 | Route 3 → Mt. Moon → Route 4 → Cerulean City | — | Mt. Moon B2F: choose Helix (Omanyte) or Dome (Kabuto) Fossil. Magikarp salesman in the Route 4 Pokémon Center. |
| 4 | Nugget Bridge (Route 24) → Route 25 | — | Nugget from the Rocket at the bridge end. Bill gives the S.S. Ticket. Misty. |
| 5 | Routes 5-6 → Vermilion City | Underground Path (Saffron gates closed) | Bike Voucher from the Fan Club chairman → free Bicycle in Cerulean. S.S. Anne captain gives HM01 Cut. Lt. Surge. |
| 6 | Route 11 → Diglett's Cave → Route 2 | Cut | Diglett's Cave shortcut back to Pewter/Viridian. Route 2 gate aide: HM05 Flash for 10 caught. |
| 7 | Route 9 → Rock Tunnel → Lavender Town | Cut; Flash recommended | Rock Tunnel is dark without Flash. |
| 8 | Route 8 → Underground → Celadon City | — | Erika. Dept. Store (TMs, stones, drinks). Eevee gift in the Celadon Mansion back entrance. Game Corner basement = Rocket Hideout → Silph Scope (Lift Key on B4F). |
| 9 | Pokémon Tower → Mr. Fuji | Silph Scope | Poké Flute. Ghost Marowak on 6F needs the Silph Scope. |
| 10 | Routes 12-15 or 16-18 → Fuchsia City | Poké Flute (Snorlax blocks both) | Super Rod on Route 12. Fly (HM02) on Route 16 behind a Cut tree. Koga. |
| 11 | Safari Zone | ¥500 | HM03 Surf (secret house, Area 3) and Gold Teeth → Warden → HM04 Strength. |
| 12 | Saffron City | Give any drink to a gate guard | Silph Co. (Card Key 5F): Lapras on 7F, Master Ball from the president on 11F. Sabrina. Fighting Dojo: Hitmonlee or Hitmonchan. |
| 13 | Cinnabar Island (Surf Routes 19-21, via Seafoam Islands) | Surf | Pokémon Mansion → Secret Key → Blaine. Cinnabar Lab revives fossils (Lv30). Articuno in Seafoam B4F (Strength boulder puzzle). |
| 14 | Power Plant (Route 10, Surf) | Surf | Zapdos Lv50. Voltorb/Electrode disguised as item balls. |
| 15 | Viridian Gym | 7 badges | Giovanni. |
| 16 | Route 22 → Route 23 → Victory Road → Indigo Plateau | 8 badges; Strength | Route 23 guards check each badge. Moltres Lv50 on Victory Road 2F. |
| 17 | Cerulean Cave | Hall of Fame; Surf | Mewtwo Lv70 on B1F. Highest wild levels in the game. |

## HMs

| HM | Move | Where | Field badge |
|---|---|---|---|
| HM01 | Cut | S.S. Anne captain | Cascade |
| HM02 | Fly | Route 16 house (behind Cut tree) | Thunder |
| HM03 | Surf | Safari Zone secret house | Soul |
| HM04 | Strength | Fuchsia Warden (bring Gold Teeth) | Rainbow |
| HM05 | Flash | Route 2 gate, Oak's aide (10 Pokémon caught) | Boulder |

HM moves cannot be forgotten in Red/Blue. Only teach them to Pokémon that will keep them. Surf is a strong move (95 power, 15 PP) and worth keeping. Cut, Flash, and Fly are weak.

## Key Items & NPCs

- **Oak's aides:** Route 2 gate HM05 Flash (10 caught), Route 11 gate 2F Itemfinder (30), Route 15 gate 2F Exp. All (50).
- **Rods:** Old Rod (Vermilion), Good Rod (Fuchsia), Super Rod (Route 12). The Super Rod pool varies by location; grep `Super Rod` in catch_locations_gen1.md.
- **Celadon Dept. Store:** 2F counter 2 sells TMs; 4F sells evolution stones; 5F sells vitamins and X items; roof vending machines sell drinks. Give the roof girl Fresh Water, Soda Pop, and Lemonade for TM13 Ice Beam, TM48 Rock Slide, and TM49 Tri Attack.
- **Coin Case:** Celadon Diner. Coins: ¥1000 per 50 at the Game Corner. Hidden coins are on the Game Corner floor (Itemfinder).
- **Gift Pokémon:** Eevee Lv25 (Celadon Mansion roof house), Lapras Lv15 (Silph Co. 7F), Hitmonlee or Hitmonchan Lv30 (Fighting Dojo), fossils Lv30 (Cinnabar Lab), Magikarp ¥500 (Route 4).
- **In-game trades:** Mr. Mime, Jynx, Farfetch'd, Lickitung, Electrode, Tangela, Seel, Nidorina, Nidoran♀. Traded Pokémon gain 1.5x EXP and follow the obedience caps above.

## Version Exclusives

- **Red only:** Ekans/Arbok, Oddish/Gloom/Vileplume, Mankey/Primeape, Growlithe/Arcanine, Scyther (Safari Zone, Game Corner), Electabuzz (Power Plant).
- **Blue only:** Sandshrew/Sandslash, Vulpix/Ninetales, Meowth/Persian, Bellsprout/Weepinbell/Victreebel, Pinsir (Safari Zone, Game Corner), Magmar (Pokémon Mansion).
- Game Corner prices and levels differ by version: `grep Prize catch_locations_gen1.md`.
- Mew is not obtainable in normal play.

## Gen 1 Mechanics

### Stats and damage
- **Special** is one stat for both special attack and special defense. Amnesia (+2 Special) raises offense and defense together. It is one of the strongest moves in the game.
- **Physical/Special split is by type.** Physical: Normal, Fighting, Flying, Poison, Ground, Rock, Bug, Ghost. Special: Fire, Water, Grass, Electric, Psychic, Ice, Dragon. Physical moves use Attack/Defense; special moves use Special on both sides.
- **STAB** is 1.5x. Type effectiveness multiplies per defending type (4x, 2x, 1x, 0.5x, 0.25x, 0x).
- **Critical hits** depend on base Speed, not a fixed rate. Chance = base Speed / 512; high-crit moves (Slash, Razor Leaf, Crabhammer, Karate Chop) multiply that by 8, capped at 255/256. Fast Pokémon (Persian, Jolteon, Alakazam, Electrode) crit often. Crits ignore all stat stages and badge boosts on both sides and use the attacker's level doubled.
- **Focus Energy and Dire Hit are bugged:** they cut the crit rate to 1/4 instead of raising it. Never use them.
- **1/256 miss:** 100%-accuracy moves still miss 1/256 of the time. Swift does not.
- **Badge boosts** (Boulder Atk, Thunder Def, Soul Spd, Volcano Spc; ×1.125) apply to your Pokémon in battle, not link battles. They are re-applied whenever any stat changes (a known quirk that stacks boosts).
- **Stat experience and DVs** replace EVs/IVs. DVs are 0-15. The HP DV is derived from the other four. Vitamins add stat experience up to a cap. DVs are only relevant if the trainer asks.

### Status
- **Sleep** lasts 1-7 turns. The Pokémon cannot act on the turn it wakes up. Sleep is the strongest status in Gen 1.
- **Freeze** never thaws on its own. In battle only a Fire-type hit or the opponent's Haze cures it (Haze cures the target's status). Outside battle: Ice Heal, Full Heal, or a Pokémon Center.
- **Paralysis** cuts Speed to 1/4 and gives a 25% chance to lose each turn.
- **Burn** halves Attack. **Poison** deals 1/16 per turn. **Toxic** damage escalates; Leech Seed shares its counter.
- Pokémon cannot be burned/frozen/paralyzed by a damaging move of their own type (Body Slam cannot paralyze Normal types; Thunderbolt cannot paralyze Electric types). Thunder Wave does not affect Ground types.

### Notable move behavior
- **Hyper Beam** needs no recharge turn if it KOs or breaks a Substitute. 150 power with STAB on a Normal type is the strongest routine attack in the game.
- **Wrap, Bind, Fire Spin, Clamp** prevent the target from acting at all for 2-5 turns. A faster user can lock a target down completely.
- **Counter** only reflects Normal and Fighting damage.
- **Seismic Toss / Night Shade** deal damage equal to the user's level; Night Shade hits Normal types, Seismic Toss hits Ghosts.
- **Explosion / Self-Destruct** halve the target's Defense in the calculation.
- **Bite, Gust, Karate Chop, Sand Attack** are Normal-type in Gen 1.
- **Ghost moves** do nothing to Psychic types (a bug). The only damaging Ghost move is Lick (20 power); Night Shade is fixed damage.
- **Rest** sleeps for exactly 2 turns. **Recover/Soft-Boiled** fail if the HP deficit is exactly 255 or 511.
- **Blizzard** is 90% accurate in Gen 1 (70% later). With a 10% freeze chance it is the best Ice move.

### What is strong
- Best attacks: Body Slam, Hyper Beam, Blizzard, Ice Beam, Thunderbolt, Thunder, Psychic, Earthquake, Surf, Rock Slide, Submission, Double-Edge.
- Best support: Thunder Wave, Sleep Powder, Hypnosis, Lovely Kiss, Sing, Amnesia, Swords Dance, Recover, Soft-Boiled, Reflect.
- Psychic types (Alakazam, Starmie, Exeggutor, Slowbro, Jynx) dominate. Normal types with Body Slam/Hyper Beam (Snorlax, Tauros, Chansey) are the other top tier.
- TMs are single-use. Assign each TM to its best recipient before using it. `grep` learnsets_gen1.md for compatibility.

### Evolution timing
- Evolving early can skip moves: many evolved forms learn the same moves several levels later, or never. Check `learnsets_gen1.md` for both stages before evolving. Pressing B cancels an evolution.
- Stone evolutions stop learning level-up moves they had not reached (Vileplume, Ninetales, Cloyster, Starmie, Arcanine learn almost nothing after evolving). Learn key moves first.
- Trade evolutions: Kadabra, Machoke, Graveler, Haunter.

## Catching

- Catch chance improves when the target is asleep or frozen (largest bonus) or paralyzed/burned/poisoned (smaller bonus), and at low HP. Ball tiers: Poké < Great < Ultra; Master Ball never fails. Safari Ball matches Ultra Ball.
- **Safari Zone (Kanto):** ¥500, 30 Safari Balls, 500 steps. Throw Rock: easier to catch, more likely to flee. Throw Bait: less likely to flee, harder to catch. Chansey, Kangaskhan, Tauros, Scyther (Red) / Pinsir (Blue), and Dratini (Super Rod) live here.
- **Legendary birds** are Lv50, catch rate 3. **Mewtwo** is Lv70, catch rate 3. Sleep + Ultra Balls, or the Master Ball.
- Static encounters are one chance. Save before each.

## Known Glitches

- **MissingNo.:** talk to the Viridian old man (catching tutorial), then Fly to Cinnabar and surf the east coast. Can corrupt the Hall of Fame; it also multiplies the 6th bag item. The parser reports glitch species as "MissingNo. (<index>)".
- **Mew glitch (trainer-fly):** reachable in Red/Blue via a Fly/Teleport trainer-escape sequence. Not needed for normal play.
