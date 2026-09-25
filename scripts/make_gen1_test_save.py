"""make_gen1_test_save.py — regenerate tests/data/gen1_red_ingame.sav.

Produces a Pokémon Red save written by the game's own save routine, so the
Gen 1 parser is tested against real SRAM (layout, checksum, struct packing)
rather than only against fixtures built with the parser's own assumptions.

It boots a pret/pokered build in PyBoy, plays through the intro (the player
is named by holding A, so the name is "AAAAAAA"), writes a known party, box,
daycare, bag, money, coins, badges, and Pokédex into WRAM, then saves via the
Start menu. tests/test_gen1_parser.py asserts on exactly those values.

Requirements (not needed to run the test suite, only to regenerate the file):
    - a pokered checkout built with `make red` (pokered.gbc + pokered.sym);
      it builds from source and matches the retail ROM's SHA1
    - pip install pyboy pillow

Usage:
    python3 scripts/make_gen1_test_save.py --pokered PATH [--out tests/data/gen1_red_ingame.sav]
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

_CHARS = {c: 0x80 + i for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")}
_CHARS.update({" ": 0x7F, "♂": 0xEF})


def _name(text: str) -> list[int]:
    body = [_CHARS[c] for c in text]
    return body + [0x50] * (11 - len(body))


def _be16(v: int) -> list[int]:
    return [v >> 8, v & 0xFF]


def box_struct(species, hp, level, status, t1, t2, moves, ot_id, exp, dvs, pp) -> list[int]:
    return ([species] + _be16(hp) + [level, status, t1, t2, 45] + moves + _be16(ot_id)
            + [exp >> 16, (exp >> 8) & 0xFF, exp & 0xFF] + [0] * 10 + _be16(dvs) + pp)


def party_struct(box: list[int], level: int, stats: list[int]) -> list[int]:
    return box + [level] + sum((_be16(s) for s in stats), [])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pokered", type=Path, required=True, help="built pret/pokered checkout")
    ap.add_argument("--out", type=Path, default=_ROOT / "tests/data/gen1_red_ingame.sav")
    args = ap.parse_args(argv)

    from pyboy import PyBoy  # imported lazily: only this tool needs it

    rom = args.pokered / "pokered.gbc"
    sym: dict[str, int] = {}
    for line in (args.pokered / "pokered.sym").read_text().splitlines():
        m = re.match(r"([0-9a-f]+):([0-9a-f]+) (\S+)", line)
        if m:
            sym[m.group(3)] = int(m.group(2), 16)

    ram_file = Path(str(rom) + ".ram")
    ram_file.unlink(missing_ok=True)
    pb = PyBoy(str(rom), window="null", sound_emulated=False)
    pb.set_emulation_speed(0)
    mem = pb.memory

    def tick(n: int = 1) -> None:
        for _ in range(n):
            pb.tick()

    def press(button: str, hold: int = 8, after: int = 20) -> None:
        pb.button_press(button)
        tick(hold)
        pb.button_release(button)
        tick(after)

    def write(addr: int, data: list[int]) -> None:
        for i, b in enumerate(data):
            mem[addr + i] = b

    # Intro: title screen, NEW GAME, Oak's speech, names (A-spam), into the bedroom.
    tick(600)
    for _ in range(400):
        press("a", hold=4)
    for _ in range(6):
        press("b", hold=4, after=30)

    tid = (mem[sym["wPlayerID"]] << 8) | mem[sym["wPlayerID"] + 1]
    bulba = party_struct(box_struct(0x99, 30, 12, 0, 0x16, 0x03, [33, 45, 73, 22], tid, 1800, 0xABCD,
                                    [(2 << 6) | 30, 40, 10, 10]), 12, [35, 20, 20, 19, 24])
    pidgey = party_struct(box_struct(0x24, 11, 9, 0x08, 0x00, 0x02, [33, 28, 0, 0], tid, 729, 0x1234,
                                     [35, 15, 0, 0]), 9, [26, 15, 14, 16, 13])
    mewtwo = party_struct(box_struct(0x83, 250, 70, 0, 0x18, 0x18, [94, 133, 105, 0], 54321, 1_200_000,
                                     0xFFFF, [10, (3 << 6) | 20, 20, 0]), 70, [250, 180, 140, 190, 220])
    write(sym["wPartyCount"], [3, 0x99, 0x24, 0x83, 0xFF])
    for i, mon in enumerate([bulba, pidgey, mewtwo]):
        write(sym["wPartyMons"] + i * 44, mon)
    for i, (ot, nick) in enumerate([("AAAAAAA", "BULBASAUR"), ("AAAAAAA", "BIRDY"), ("GIOVANNI", "MEWTWO")]):
        write(sym["wPartyMonOT"] + i * 11, _name(ot))
        write(sym["wPartyMonNicks"] + i * 11, _name(nick))

    nido = box_struct(0x03, 20, 5, 0, 0x03, 0x03, [43, 33, 0, 0], tid, 135, 0x0F0F, [30, 35, 0, 0])
    abra = box_struct(0x94, 22, 8, 0, 0x18, 0x18, [100, 0, 0, 0], tid, 360, 0x8421, [20, 0, 0, 0])
    write(sym["wBoxCount"], [2, 0x03, 0x94, 0xFF])
    write(sym["wBoxMons"], nido + abra)
    write(sym["wBoxMonOT"], _name("AAAAAAA") + _name("AAAAAAA"))
    write(sym["wBoxMonNicks"], _name("NIDORAN♂") + _name("ABRA"))

    # Snorlax deposited at Lv30 with 37300 EXP (Slow curve: Lv31 starts at 37238).
    write(sym["wDayCareInUse"], [1])
    write(sym["wDayCareMonName"], _name("LAX"))
    write(sym["wDayCareMonOT"], _name("AAAAAAA"))
    write(sym["wDayCareMon"], box_struct(0x84, 0, 30, 0, 0, 0, [29, 133, 0, 0], tid, 37300, 0x5555, [15, 20, 0, 0]))

    write(sym["wNumBagItems"], [3, 0x14, 5, 0xE4, 1, 0x04, 10, 0xFF])  # Potion x5, TM28 x1, Poke Ball x10
    write(sym["wPlayerMoney"], [0x01, 0x23, 0x45])
    write(sym["wPlayerCoins"], [0x04, 0x20])
    write(sym["wObtainedBadges"], [0b00000111])
    write(sym["wRivalName"], _name("GARY"))
    owned, seen = [0] * 19, [0] * 19
    for dex in (1, 16, 150):
        owned[(dex - 1) // 8] |= 1 << ((dex - 1) % 8)
    for dex in (1, 16, 150, 19, 32, 63, 143):
        seen[(dex - 1) // 8] |= 1 << ((dex - 1) % 8)
    write(sym["wPokedexOwned"], owned)
    write(sym["wPokedexSeen"], seen)
    tick(30)

    # Start menu -> SAVE (4th entry before the Pokédex is obtained) -> YES
    press("start", after=40)
    while mem[sym["wCurrentMenuItem"]] != 3:
        press("down", after=10)
    press("a", after=120)
    tick(60)
    for _ in range(4):
        press("a", after=300)
    pb.stop(save=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(ram_file), args.out)
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
