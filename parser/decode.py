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
DATA_SIZE       = 0xFF4    # max usable data bytes per sector (footer starts here)
FOOTER_OFFSET   = 0xFF4
SECTION_SIGNATURE = 0x08012025

# Per-section checksummed/used data length. Gen III checksums only cover the
# bytes each section actually uses, not the full 0xFF4 up to the footer.
# Verified empirically against a real Ruby/Sapphire save: with these sizes,
# all 14 sectors in both blocks pass their stored checksum.
SECTION_DATA_SIZES: dict[int, int] = {
    0: 0x890,
    1: 0xF80, 2: 0xF80, 3: 0xF80, 4: 0xF80,
    5: 0xF80, 6: 0xF80, 7: 0xF80, 8: 0xF80,
    9: 0xF80, 10: 0xF80, 11: 0xF80, 12: 0xF80,
    13: 0x7D0,
}

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


def _checksum(sector_data: bytes, length: int) -> int:
    """Compute the Gen III sector checksum over the first *length* bytes.

    *length* is section-specific (see SECTION_DATA_SIZES) — Gen III does not
    checksum the full sector, only the portion that section actually uses.
    """
    total = 0
    for offset in range(0, length, 4):
        (word,) = struct.unpack_from("<I", sector_data, offset)
        total = (total + word) & 0xFFFFFFFF
    return ((total >> 16) + (total & 0xFFFF)) & 0xFFFF


def _read_footer(sector: bytes) -> tuple[int, int, int, int]:
    """Return (section_id, checksum, signature, save_index) from a sector footer."""
    section_id, checksum = struct.unpack_from("<HH", sector, FOOTER_OFFSET)
    signature, save_index = struct.unpack_from("<II", sector, FOOTER_OFFSET + 4)
    return section_id, checksum, signature, save_index


def read_sectors(data: bytes) -> tuple[list[bytes], list[bytes]]:
    """Split a save file into its two raw 14-sector blocks (no validation).

    Returns (sectors_A, sectors_B) — each list has 14 raw 0x1000-byte sectors.
    """
    sectors_a = [
        data[i * SECTOR_SIZE : (i + 1) * SECTOR_SIZE] for i in range(SECTOR_COUNT)
    ]
    sectors_b = [
        data[SAVE_BLOCK_SIZE + i * SECTOR_SIZE : SAVE_BLOCK_SIZE + (i + 1) * SECTOR_SIZE]
        for i in range(SECTOR_COUNT)
    ]
    return sectors_a, sectors_b


def validate_block(raw_sectors: list[bytes]) -> dict:
    """Validate one 14-sector block.

    A sector is valid when its signature matches SECTION_SIGNATURE, its
    section id is 0-13 and appears exactly once in the block, and its stored
    checksum matches the computed one over that section's data length.

    Returns a dict:
        valid:            bool — every section id 0-13 present exactly once,
                           all valid, and save_index is not the uninitialised
                           sentinel (0xFFFFFFFF).
        save_index:        int | None
        invalid_sections:  sorted list of section ids that failed validation
                           or are missing entirely
        sections:          {section_id: raw_sector_bytes} for sections that
                           passed validation
    """
    sections: dict[int, bytes] = {}
    invalid_sections: set[int] = set()
    save_indices: set[int] = set()
    seen_ids: set[int] = set()

    for sector in raw_sectors:
        section_id, checksum, signature, save_index = _read_footer(sector)
        save_indices.add(save_index)

        ok = True
        if signature != SECTION_SIGNATURE:
            ok = False
        if section_id not in SECTION_DATA_SIZES:
            ok = False
        elif section_id in seen_ids:
            ok = False  # duplicate section id within the block
        elif ok:
            length = SECTION_DATA_SIZES[section_id]
            if _checksum(sector, length) != checksum:
                ok = False

        if ok:
            seen_ids.add(section_id)
            sections[section_id] = sector
        else:
            invalid_sections.add(section_id)

    missing_ids = set(range(SECTOR_COUNT)) - seen_ids
    invalid_sections |= missing_ids

    save_index = max(save_indices) if save_indices else None
    uninitialised = save_index is None or save_index == 0xFFFFFFFF
    valid = not invalid_sections and not uninitialised

    return {
        "valid": valid,
        "save_index": save_index,
        "invalid_sections": sorted(invalid_sections),
        "sections": sections,
    }


def select_save_slot(
    sectors_a: list[bytes], sectors_b: list[bytes]
) -> tuple[dict[int, bytes], str, int | None, list[int]]:
    """Validate both blocks and pick the valid one with the higher save index.

    Returns (sections_by_id, slot_label, save_index, invalid_sections).
    Raises ValueError if neither block validates.
    """
    block_a = validate_block(sectors_a)
    block_b = validate_block(sectors_b)

    if block_a["valid"] and block_b["valid"]:
        if block_b["save_index"] > block_a["save_index"]:
            chosen, label = block_b, "B"
        else:
            chosen, label = block_a, "A"
    elif block_a["valid"]:
        chosen, label = block_a, "A"
        logger.warning(
            "Save block B failed validation (invalid sections: %s); using block A.",
            block_b["invalid_sections"],
        )
    elif block_b["valid"]:
        chosen, label = block_b, "B"
        logger.warning(
            "Save block A failed validation (invalid sections: %s); using block B.",
            block_a["invalid_sections"],
        )
    else:
        raise ValueError(
            "No valid save block found in file. "
            f"Block A invalid sections: {block_a['invalid_sections']} "
            f"(save_index={block_a['save_index']}); "
            f"Block B invalid sections: {block_b['invalid_sections']} "
            f"(save_index={block_b['save_index']})"
        )

    return chosen["sections"], label, chosen["save_index"], chosen["invalid_sections"]


def get_sector_data(sections: dict[int, bytes], section_id: int) -> bytes:
    """Return the validated data payload for *section_id*.

    *sections* is the {section_id: raw_sector_bytes} dict returned by
    select_save_slot(). The payload is trimmed to that section's actual data
    length (SECTION_DATA_SIZES), not the full sector.
    """
    if section_id not in sections:
        raise ValueError(f"Section ID {section_id} not present in this save block")
    length = SECTION_DATA_SIZES.get(section_id, DATA_SIZE)
    return sections[section_id][:length]


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
