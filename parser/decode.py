"""Low-level sector reading, checksum validation, decryption, and string
decoding for Generation III (Ruby/Sapphire) save files."""

import logging
import struct

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAVE_BLOCK_SIZE = 0xE000   # 57,344 bytes per block
SECTOR_SIZE     = 0x1000   # 4,096 bytes per sector
SECTOR_COUNT    = 14
DATA_SIZE       = 0xFF4    # usable data bytes per sector
FOOTER_OFFSET   = 0xFF4

# ---------------------------------------------------------------------------
# Gen III character table
# ---------------------------------------------------------------------------

_CHAR_TABLE: dict[int, str] = {
    0x00: " ",
    # Uppercase A-Z
    0xBB: "A", 0xBC: "B", 0xBD: "C", 0xBE: "D", 0xBF: "E",
    0xC0: "F", 0xC1: "G", 0xC2: "H", 0xC3: "I", 0xC4: "J",
    0xC5: "K", 0xC6: "L", 0xC7: "M", 0xC8: "N", 0xC9: "O",
    0xCA: "P", 0xCB: "Q", 0xCC: "R", 0xCD: "S", 0xCE: "T",
    0xCF: "U", 0xD0: "V", 0xD1: "W", 0xD2: "X", 0xD3: "Y",
    0xD4: "Z",
    # Lowercase a-z
    0xD5: "a", 0xD6: "b", 0xD7: "c", 0xD8: "d", 0xD9: "e",
    0xDA: "f", 0xDB: "g", 0xDC: "h", 0xDD: "i", 0xDE: "j",
    0xDF: "k", 0xE0: "l", 0xE1: "m", 0xE2: "n", 0xE3: "o",
    0xE4: "p", 0xE5: "q", 0xE6: "r", 0xE7: "s", 0xE8: "t",
    0xE9: "u", 0xEA: "v", 0xEB: "w", 0xEC: "x", 0xED: "y",
    0xEE: "z",
    # Digits 0-9
    0xA1: "0", 0xA2: "1", 0xA3: "2", 0xA4: "3", 0xA5: "4",
    0xA6: "5", 0xA7: "6", 0xA8: "7", 0xA9: "8", 0xAA: "9",
    # Punctuation / special
    0xAB: "!", 0xAC: "?", 0xAD: ".", 0xAE: "-",
    0xAF: "\u2027",  # middle dot
    0xB0: "\u2026",  # ellipsis
    0xB1: "\u201c",  # left double quote
    0xB2: "\u201d",  # right double quote
    0xB3: "\u2018",  # left single quote
    0xB4: "'",       # apostrophe
    0xB5: "'",       # male symbol placeholder
    0xB6: "'",       # female symbol placeholder
    0xBA: " ",       # Mr prefix — simplified to space
}

# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------


def _checksum(sector_data: bytes) -> int:
    """Compute the Gen III sector checksum over the first DATA_SIZE bytes."""
    total = 0
    for offset in range(0, DATA_SIZE, 4):
        (word,) = struct.unpack_from("<I", sector_data, offset)
        total = (total + word) & 0xFFFFFFFF
    return ((total >> 16) + (total & 0xFFFF)) & 0xFFFF


def read_sectors(data: bytes) -> tuple[list[bytes], list[bytes]]:
    """Split a save file into two blocks and validate sector checksums.

    Returns (sectors_A, sectors_B) — each list has 14 raw sector blobs.
    """
    sectors_a: list[bytes] = []
    sectors_b: list[bytes] = []

    for block_idx, block_offset in enumerate((0, SAVE_BLOCK_SIZE)):
        label = "A" if block_idx == 0 else "B"
        dest = sectors_a if block_idx == 0 else sectors_b
        for i in range(SECTOR_COUNT):
            start = block_offset + i * SECTOR_SIZE
            sector = data[start : start + SECTOR_SIZE]
            dest.append(sector)

            expected = struct.unpack_from("<H", sector, FOOTER_OFFSET + 2)[0]
            actual = _checksum(sector)
            if actual != expected:
                logger.warning(
                    "Block %s sector %d checksum mismatch: "
                    "computed 0x%04X, stored 0x%04X",
                    label, i, actual, expected,
                )

    return sectors_a, sectors_b


def select_save_slot(
    sectors_a: list[bytes], sectors_b: list[bytes]
) -> tuple[list[bytes], str]:
    """Pick the more recent save block based on the save index."""
    (idx_a,) = struct.unpack_from("<I", sectors_a[0], 0xFFC)
    (idx_b,) = struct.unpack_from("<I", sectors_b[0], 0xFFC)
    if idx_b > idx_a:
        return sectors_b, "B"
    return sectors_a, "A"


def get_sector_data(sectors: list[bytes], section_id: int) -> bytes:
    """Return the DATA_SIZE payload for the sector matching *section_id*."""
    for sector in sectors:
        (sid,) = struct.unpack_from("<H", sector, FOOTER_OFFSET)
        if sid == section_id:
            return sector[:DATA_SIZE]
    raise ValueError(f"Section ID {section_id} not found in provided sectors")


def xor_decrypt(data: bytes, key: int) -> bytes:
    """XOR-decrypt *data* using a 4-byte little-endian key."""
    key_bytes = struct.pack("<I", key & 0xFFFFFFFF)
    out = bytearray(data)
    for i in range(len(data) // 4):
        off = i * 4
        out[off]     ^= key_bytes[0]
        out[off + 1] ^= key_bytes[1]
        out[off + 2] ^= key_bytes[2]
        out[off + 3] ^= key_bytes[3]
    return bytes(out)


def decode_string(encoded: bytes) -> str:
    """Decode a Gen III encoded byte string into a Python str."""
    chars: list[str] = []
    for b in encoded:
        if b == 0xFF:
            break
        ch = _CHAR_TABLE.get(b)
        if ch is not None:
            chars.append(ch)
    return "".join(chars)
