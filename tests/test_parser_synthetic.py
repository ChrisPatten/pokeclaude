"""Synthetic unit tests for the Gen III parser — no save file required.

Covers growth-rate EXP curves, Gen III string decoding, XOR
(de)cryption, the sector checksum function, and save-block selection
built from hand-crafted (synthetic) sector data.
"""

import os
import struct
import tempfile
import unittest

from parser import decode
from parser.parse_save import parse
from parser.pokemon import _exp_for_level, _estimate_level


# ---------------------------------------------------------------------------
# Growth rate EXP curves
# ---------------------------------------------------------------------------

class TestGrowthRates(unittest.TestCase):
    def test_level_100_exp(self) -> None:
        # Known Gen III totals (Bulbapedia "Experience" growth-rate table).
        cases = {
            "medium_fast": 1_000_000,
            "erratic": 600_000,
            "fluctuating": 1_640_000,
            "medium_slow": 1_059_860,
            "fast": 800_000,
            "slow": 1_250_000,
        }
        for rate, expected in cases.items():
            with self.subTest(rate=rate):
                self.assertEqual(_exp_for_level(100, rate), expected)

    def test_level_50_exp(self) -> None:
        # Known Gen III mid-level totals, same source.
        cases = {
            "medium_fast": 125_000,
            "erratic": 125_000,
            "fluctuating": 142_500,
            "medium_slow": 117_360,
            "fast": 100_000,
            "slow": 156_250,
        }
        for rate, expected in cases.items():
            with self.subTest(rate=rate):
                self.assertEqual(_exp_for_level(50, rate), expected)

    def test_level_1_is_zero_exp_for_all_rates(self) -> None:
        for rate in ("medium_fast", "erratic", "fluctuating", "medium_slow", "fast", "slow"):
            with self.subTest(rate=rate):
                self.assertEqual(_exp_for_level(1, rate), 0)

    def test_estimate_level_roundtrips_exp_for_level(self) -> None:
        for rate in ("medium_fast", "erratic", "fluctuating", "medium_slow", "fast", "slow"):
            for lv in (1, 5, 22, 50, 77, 100):
                exp = _exp_for_level(lv, rate)
                with self.subTest(rate=rate, level=lv):
                    self.assertEqual(_estimate_level(exp, rate), lv)

    def test_estimate_level_clamps_below_one(self) -> None:
        self.assertEqual(_estimate_level(0, "medium_fast"), 1)
        self.assertEqual(_estimate_level(-5, "medium_fast"), 1)


# ---------------------------------------------------------------------------
# String decoding
# ---------------------------------------------------------------------------

class TestStringDecoding(unittest.TestCase):
    def test_decodes_letters_and_digits(self) -> None:
        # 'A' 'B' 'C' '1' '2' terminator, then trailing garbage that must be ignored.
        encoded = bytes([0xBB, 0xBC, 0xBD, 0xA2, 0xA3, 0xFF, 0xBB, 0xBB])
        self.assertEqual(decode.decode_string(encoded), "ABC12")

    def test_empty_before_terminator(self) -> None:
        self.assertEqual(decode.decode_string(bytes([0xFF, 0xBB])), "")

    def test_no_terminator_reads_whole_buffer(self) -> None:
        encoded = bytes([0xD5, 0xD6, 0xD7])  # 'a' 'b' 'c'
        self.assertEqual(decode.decode_string(encoded), "abc")

    def test_unmapped_bytes_are_skipped(self) -> None:
        # 0x01 has no table entry and should be silently dropped, not raise.
        encoded = bytes([0xBB, 0x01, 0xBC, 0xFF])
        self.assertEqual(decode.decode_string(encoded), "AB")


# ---------------------------------------------------------------------------
# XOR (de)cryption
# ---------------------------------------------------------------------------

class TestXorDecrypt(unittest.TestCase):
    def test_roundtrip_is_identity(self) -> None:
        data = bytes(range(48))  # 12 words, mirrors a substructure block
        key = 0xDEADBEEF
        once = decode.xor_decrypt(data, key)
        self.assertNotEqual(once, data)
        twice = decode.xor_decrypt(once, key)
        self.assertEqual(twice, data)

    def test_zero_key_is_identity(self) -> None:
        data = bytes(range(16))
        self.assertEqual(decode.xor_decrypt(data, 0), data)

    def test_known_vector(self) -> None:
        data = struct.pack("<I", 0x11223344)
        key = 0x0F0F0F0F
        expected = struct.pack("<I", 0x11223344 ^ 0x0F0F0F0F)
        self.assertEqual(decode.xor_decrypt(data, key), expected)


# ---------------------------------------------------------------------------
# Sector checksum
# ---------------------------------------------------------------------------

class TestChecksum(unittest.TestCase):
    def test_matches_manual_computation(self) -> None:
        # Four u32 words -> sum, then fold high/low 16 bits, per Gen III spec.
        words = [0x00000001, 0xFFFFFFFF, 0x12345678, 0x00000000]
        data = b"".join(struct.pack("<I", w) for w in words)
        total = sum(words) & 0xFFFFFFFF
        expected = ((total >> 16) + (total & 0xFFFF)) & 0xFFFF
        self.assertEqual(decode._checksum(data, len(data)), expected)

    def test_only_covers_requested_length(self) -> None:
        data = struct.pack("<II", 0x00000001, 0xFFFFFFFF)  # second word ignored below
        self.assertEqual(decode._checksum(data, 4), 1)


# ---------------------------------------------------------------------------
# Save-block selection (built from synthetic sectors)
# ---------------------------------------------------------------------------

def _build_sector(section_id: int, save_index: int, data_size: int,
                   signature: int = decode.SECTION_SIGNATURE,
                   bad_checksum: bool = False) -> bytes:
    """Build one synthetic 0x1000-byte sector with a correct (or deliberately
    wrong) checksum for the given section id."""
    data = bytearray(decode.SECTOR_SIZE)
    for i in range(data_size):
        data[i] = (i * 7 + section_id) & 0xFF
    checksum = decode._checksum(bytes(data), data_size)
    if bad_checksum:
        checksum = (checksum + 1) & 0xFFFF
    struct.pack_into("<HH", data, decode.FOOTER_OFFSET, section_id, checksum)
    struct.pack_into("<II", data, decode.FOOTER_OFFSET + 4, signature, save_index)
    return bytes(data)


def _build_block(save_index: int, corrupt_section: int | None = None) -> list[bytes]:
    return [
        _build_sector(
            sid, save_index, decode.SECTION_DATA_SIZES[sid],
            bad_checksum=(sid == corrupt_section),
        )
        for sid in range(decode.SECTOR_COUNT)
    ]


class TestSaveBlockSelection(unittest.TestCase):
    def test_valid_a_vs_corrupt_b_picks_a(self) -> None:
        sectors_a = _build_block(save_index=5)
        sectors_b = _build_block(save_index=6, corrupt_section=3)

        with self.assertLogs(level="WARNING"):
            sections, label, save_index, invalid = decode.select_save_slot(sectors_a, sectors_b)

        self.assertEqual(label, "A")
        self.assertEqual(save_index, 5)
        self.assertEqual(invalid, [])
        self.assertEqual(len(sections), decode.SECTOR_COUNT)

    def test_both_valid_picks_higher_save_index(self) -> None:
        sectors_a = _build_block(save_index=10)
        sectors_b = _build_block(save_index=11)

        _, label, save_index, invalid = decode.select_save_slot(sectors_a, sectors_b)

        self.assertEqual(label, "B")
        self.assertEqual(save_index, 11)
        self.assertEqual(invalid, [])

    def test_uninitialised_block_is_invalid(self) -> None:
        sectors_a = _build_block(save_index=0xFFFFFFFF)
        sectors_b = _build_block(save_index=3)

        with self.assertLogs(level="WARNING"):
            _, label, save_index, invalid = decode.select_save_slot(sectors_a, sectors_b)

        self.assertEqual(label, "B")
        self.assertEqual(save_index, 3)

    def test_both_invalid_raises(self) -> None:
        sectors_a = _build_block(save_index=1, corrupt_section=0)
        sectors_b = _build_block(save_index=2, corrupt_section=7)

        with self.assertRaises(ValueError):
            decode.select_save_slot(sectors_a, sectors_b)

    def test_validate_block_flags_missing_section(self) -> None:
        sectors = _build_block(save_index=1)
        del sectors[5]  # section id 5 is now missing entirely

        result = decode.validate_block(sectors)

        self.assertFalse(result["valid"])
        self.assertIn(5, result["invalid_sections"])


# ---------------------------------------------------------------------------
# End-to-end: parse() should log (and collect) the block-fallback warning
# exactly once, not once per handler / once per module.
# ---------------------------------------------------------------------------

def _build_zero_sector(section_id: int, save_index: int, data_size: int,
                        bad_checksum: bool = False) -> bytes:
    """Like _build_sector, but with an all-zero payload so the rest of the
    parser (team size, item pockets, etc.) sees a harmless empty save."""
    data = bytearray(decode.SECTOR_SIZE)
    checksum = decode._checksum(bytes(data), data_size)
    if bad_checksum:
        checksum = (checksum + 1) & 0xFFFF
    struct.pack_into("<HH", data, decode.FOOTER_OFFSET, section_id, checksum)
    struct.pack_into("<II", data, decode.FOOTER_OFFSET + 4,
                      decode.SECTION_SIGNATURE, save_index)
    return bytes(data)


def _build_minimal_save_bytes(corrupt_block_a: bool) -> bytes:
    """A full, minimal two-block synthetic .srm: block A save_index=1, block
    B save_index=2, everything zeroed out except footers (and, optionally, a
    deliberately wrong checksum on block A's section 3)."""
    block_a = b"".join(
        _build_zero_sector(sid, 1, decode.SECTION_DATA_SIZES[sid],
                            bad_checksum=(corrupt_block_a and sid == 3))
        for sid in range(decode.SECTOR_COUNT)
    )
    block_b = b"".join(
        _build_zero_sector(sid, 2, decode.SECTION_DATA_SIZES[sid])
        for sid in range(decode.SECTOR_COUNT)
    )
    return block_a + block_b


class TestParseWarningsNotDuplicated(unittest.TestCase):
    def test_block_fallback_warning_appears_exactly_once(self) -> None:
        save_bytes = _build_minimal_save_bytes(corrupt_block_a=True)

        fd, path = tempfile.mkstemp(suffix=".srm")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(save_bytes)
            result = parse(path)
        finally:
            os.remove(path)

        matching = [
            w for w in result["warnings"]
            if "failed validation" in w and "using block B" in w
        ]
        self.assertEqual(
            len(matching), 1,
            f"expected exactly one block-fallback warning, got: {matching}",
        )


if __name__ == "__main__":
    unittest.main()
