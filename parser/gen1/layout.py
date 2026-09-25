"""Generation I (Red/Blue) save layout, character set, and low-level decoders.

The .sav file is the cartridge's 32KB battery-backed SRAM: four 8KB banks
laid end to end (bank N starts at file offset N * 0x2000). Offsets below are
file offsets, verified against the symbol file of a pret/pokered build that
matches the retail ROMs byte for byte (sMainData = 01:a5a3 -> 0x25A3, etc.).

All multi-byte integers in Gen 1 are big-endian. Money and coins are BCD.
"""

SAVE_SIZE = 0x8000  # 32KB SRAM

# --- Bank 1: main save data ------------------------------------------------
PLAYER_NAME = 0x2598        # sPlayerName (11 bytes)
POKEDEX_OWNED = 0x25A3      # wPokedexOwned (19 bytes, 151 bits)
POKEDEX_SEEN = 0x25B6       # wPokedexSeen
BAG_ITEMS = 0x25C9          # wNumBagItems, then (id, qty) pairs, 0xFF terminated
MONEY = 0x25F3              # wPlayerMoney (3 bytes BCD)
RIVAL_NAME = 0x25F6         # wRivalName (11 bytes)
BADGES = 0x2602             # wObtainedBadges (bit 0 = Boulder ... bit 7 = Earth)
PLAYER_ID = 0x2605          # wPlayerID (2 bytes)
CUR_MAP = 0x260A            # wCurMap
PC_ITEMS = 0x27E6           # wNumBoxItems, then (id, qty) pairs
CURRENT_BOX = 0x284C        # wCurrentBoxNum (bits 0-6 box, bit 7 = boxes initialised)
COINS = 0x2850              # wPlayerCoins (2 bytes BCD)
PLAY_HOURS = 0x2CED         # wPlayTimeHours
PLAY_MAXED = 0x2CEE         # wPlayTimeMaxed
PLAY_MINUTES = 0x2CEF
PLAY_SECONDS = 0x2CF0
DAYCARE_IN_USE = 0x2CF4     # wDayCareInUse
DAYCARE_NICK = 0x2CF5       # wDayCareMonName
DAYCARE_OT = 0x2D00         # wDayCareMonOT
DAYCARE_MON = 0x2D0B        # wDayCareMon (box_struct, 33 bytes)
PARTY = 0x2F2C              # sPartyData: count, species[7], mons, OT names, nicknames
CUR_BOX_DATA = 0x30C0       # sCurBoxData: the box currently selected in the PC
CHECKSUM = 0x3523           # sMainDataCheckSum
CHECKSUM_START = 0x2598     # sGameData
CHECKSUM_END = 0x3523       # sGameDataEnd (exclusive)

# --- Banks 2 and 3: the other PC boxes ---------------------------------------
BOX_BANKS = (0x4000, 0x6000)    # boxes 1-6, boxes 7-12
BOXES_PER_BANK = 6
BANK_CHECKSUM_OFFSET = 0x1A4C   # sBank2AllBoxesChecksum relative to the bank start
BANK_BOX_CHECKSUMS_OFFSET = 0x1A4D

# --- Structure sizes ---------------------------------------------------------
NAME_LENGTH = 11
PARTY_LENGTH = 6
MONS_PER_BOX = 20
NUM_BOXES = 12
BOX_STRUCT_SIZE = 33        # box_struct
PARTY_STRUCT_SIZE = 44      # party_struct = box_struct + level + 5 stats
BOX_DATA_SIZE = 0x462       # wBoxDataEnd - wBoxDataStart
BAG_CAPACITY = 20
PC_ITEM_CAPACITY = 50

# Offsets inside a party/box data block
PARTY_SPECIES = 1
PARTY_MONS = PARTY_SPECIES + PARTY_LENGTH + 1                            # 0x08
PARTY_OT = PARTY_MONS + PARTY_LENGTH * PARTY_STRUCT_SIZE                  # 0x110
PARTY_NICKS = PARTY_OT + PARTY_LENGTH * NAME_LENGTH                       # 0x152
BOX_SPECIES = 1
BOX_MONS = BOX_SPECIES + MONS_PER_BOX + 1                                 # 0x16
BOX_OT = BOX_MONS + MONS_PER_BOX * BOX_STRUCT_SIZE                        # 0x2AA
BOX_NICKS = BOX_OT + MONS_PER_BOX * NAME_LENGTH                           # 0x386

BADGE_NAMES = [
    "Boulder Badge", "Cascade Badge", "Thunder Badge", "Rainbow Badge",
    "Soul Badge", "Marsh Badge", "Volcano Badge", "Earth Badge",
]

# ---------------------------------------------------------------------------
# Character set (pokered constants/charmap.asm, English)
# ---------------------------------------------------------------------------

STRING_TERMINATOR = 0x50

_CHARMAP: dict[int, str] = {0x7F: " "}
for _i, _c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ():;[]"):
    _CHARMAP[0x80 + _i] = _c
for _i, _c in enumerate("abcdefghijklmnopqrstuvwxyzé"):
    _CHARMAP[0xA0 + _i] = _c
_CHARMAP.update({
    0xBB: "'d", 0xBC: "'l", 0xBD: "'s", 0xBE: "'t", 0xBF: "'v",
    0xE0: "'", 0xE1: "PK", 0xE2: "MN", 0xE3: "-", 0xE4: "'r", 0xE5: "'m",
    0xE6: "?", 0xE7: "!", 0xE8: ".", 0xEF: "♂", 0xF0: "¥", 0xF1: "×",
    0xF2: ".", 0xF3: "/", 0xF4: ",", 0xF5: "♀",
    0x54: "POKé", 0x5B: "PC", 0x5C: "TM", 0x5D: "TRAINER", 0x5E: "ROCKET",
    0x70: "‘", 0x71: "’", 0x72: "“", 0x73: "”", 0x75: "…",
})
for _i in range(10):
    _CHARMAP[0xF6 + _i] = str(_i)


def decode_string(encoded: bytes) -> str:
    """Decode a Gen 1 string, stopping at the 0x50 terminator."""
    out: list[str] = []
    for b in encoded:
        if b == STRING_TERMINATOR:
            break
        ch = _CHARMAP.get(b)
        if ch is not None:
            out.append(ch)
    return "".join(out)


def encode_string(text: str, length: int = NAME_LENGTH) -> bytes:
    """Encode *text* as a terminator-padded Gen 1 string (used by tests/tools)."""
    reverse: dict[str, int] = {}
    for k, v in sorted(_CHARMAP.items()):
        if len(v) == 1:
            reverse.setdefault(v, k)
    body = bytes(reverse[c] for c in text)
    if len(body) >= length:
        raise ValueError(f"{text!r} does not fit in {length} bytes with its terminator")
    return body + bytes([STRING_TERMINATOR] * (length - len(body)))


def bcd(data: bytes) -> int:
    """Decode big-endian packed BCD (two decimal digits per byte)."""
    value = 0
    for b in data:
        value = value * 100 + (b >> 4) * 10 + (b & 0x0F)
    return value


def u16(data: bytes, offset: int) -> int:
    return (data[offset] << 8) | data[offset + 1]


def u24(data: bytes, offset: int) -> int:
    return (data[offset] << 16) | (data[offset + 1] << 8) | data[offset + 2]


def checksum(data: bytes, start: int, end: int) -> int:
    """Gen 1 SRAM checksum: bitwise NOT of the 8-bit sum of data[start:end]."""
    return ~sum(data[start:end]) & 0xFF
