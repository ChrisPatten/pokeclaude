"""Tests for the Generation I (Red/Blue) save parser.

tests/data/gen1_red_ingame.sav was written by Pokémon Red's own save routine
(scripts/make_gen1_test_save.py) with known injected data, and
tests/data/gen1_red_realplay.sav is a real 21-hour playthrough, so the golden
assertions below check the parser against real SRAM. The synthetic tests start from that file, mutate
it (box banks, glitch species, duplicate IDs), and re-apply the game's
checksums.
"""

import json
import tempfile
import unittest
from pathlib import Path

from parser import data_loader, gen1, sync
from parser.gen1 import layout, pokemon
from parser.parse_save import detect_generation, parse

_SAVE = Path(__file__).parent / "data" / "gen1_red_ingame.sav"
_REALPLAY = Path(__file__).parent / "data" / "gen1_red_realplay.sav"


def _load() -> bytearray:
    return bytearray(_SAVE.read_bytes())


def _fix_main_checksum(sav: bytearray) -> None:
    sav[layout.CHECKSUM] = layout.checksum(sav, layout.CHECKSUM_START, layout.CHECKSUM_END)


def _box_block(mons: list[tuple[int, int, int, str]]) -> bytes:
    """Build a 0x462-byte box: mons are (species, level, dvs, nickname)."""
    block = bytearray(layout.BOX_DATA_SIZE)
    block[0] = len(mons)
    for i, (species, level, dvs, nick) in enumerate(mons):
        block[layout.BOX_SPECIES + i] = species
        off = layout.BOX_MONS + i * layout.BOX_STRUCT_SIZE
        block[off] = species
        block[off + 3] = level
        block[off + 8] = 33  # Tackle
        block[off + 12:off + 14] = (0x1234).to_bytes(2, "big")
        block[off + 14:off + 17] = (level ** 3).to_bytes(3, "big")
        block[off + 27:off + 29] = dvs.to_bytes(2, "big")
        block[off + 29] = 35
        nick_off = layout.BOX_NICKS + i * layout.NAME_LENGTH
        block[nick_off:nick_off + layout.NAME_LENGTH] = layout.encode_string(nick)
    block[layout.BOX_SPECIES + len(mons)] = 0xFF
    return bytes(block)


def _write_bank_box(sav: bytearray, box_idx: int, block: bytes) -> None:
    bank_start = layout.BOX_BANKS[box_idx // layout.BOXES_PER_BANK]
    start = bank_start + (box_idx % layout.BOXES_PER_BANK) * layout.BOX_DATA_SIZE
    sav[start:start + layout.BOX_DATA_SIZE] = block


def _fix_bank_checksums(sav: bytearray) -> None:
    for bank_start in layout.BOX_BANKS:
        sav[bank_start + layout.BANK_CHECKSUM_OFFSET] = layout.checksum(
            sav, bank_start, bank_start + layout.BANK_CHECKSUM_OFFSET)


def _parse_bytes(sav: bytes) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as f:
        f.write(sav)
    try:
        return parse(f.name)
    finally:
        Path(f.name).unlink()


# ---------------------------------------------------------------------------
# Golden: a save written by the game itself
# ---------------------------------------------------------------------------

class TestInGameSave(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = parse(str(_SAVE))

    def test_generation_detected(self) -> None:
        self.assertEqual(self.data["save_metadata"]["generation"], 1)
        self.assertTrue(self.data["save_metadata"]["checksum_valid"])
        self.assertEqual(self.data["warnings"], [])

    def test_trainer(self) -> None:
        t = self.data["trainer"]
        self.assertEqual(t["name"], "AAAAAAA")
        self.assertEqual(t["rival_name"], "GARY")
        self.assertEqual(t["trainer_id"], 43627)
        self.assertEqual(t["money"], 12345)
        self.assertEqual(t["coins"], 420)
        self.assertEqual(t["playtime"], {"hours": 0, "minutes": 1, "seconds": 48})

    def test_badges_location_pokedex(self) -> None:
        self.assertEqual(self.data["badges"], {
            "count": 3, "obtained": ["Boulder Badge", "Cascade Badge", "Thunder Badge"]})
        self.assertEqual(self.data["location"]["name"], "Red's House 2F")
        self.assertTrue(self.data["location"]["known"])
        self.assertEqual(self.data["pokedex"], {"seen": 7, "caught": 3})

    def test_inventory(self) -> None:
        self.assertEqual(self.data["inventory"]["items"], [
            {"name": "Potion", "quantity": 5},
            {"name": "TM28", "quantity": 1},
            {"name": "Poké Ball", "quantity": 10},
        ])
        # The game itself seeds the PC with one Potion on a new file.
        self.assertEqual(self.data["inventory"]["pc"], [{"name": "Potion", "quantity": 1}])

    def test_party(self) -> None:
        party = self.data["party"]
        self.assertEqual([m["species_name"] for m in party], ["Bulbasaur", "Pidgey", "Mewtwo"])
        bulba, pidgey, mewtwo = party
        self.assertEqual(bulba["pid"], "0xAA6BABCD")
        self.assertEqual(bulba["types"], ["Grass", "Poison"])
        self.assertEqual(bulba["level"], 12)
        self.assertEqual(bulba["hp"], {"current": 30, "max": 35})
        self.assertEqual(bulba["stats"], {"attack": 20, "defense": 20, "speed": 19, "special": 24})
        tackle = bulba["moves"][0]
        self.assertEqual((tackle["name"], tackle["pp"], tackle["pp_max"]), ("Tackle", 30, 49))
        self.assertEqual(pidgey["nickname"], "BIRDY")
        self.assertEqual(pidgey["status"], "poison")
        self.assertEqual(mewtwo["pid"], "0xD431FFFF")  # traded: OT 54321
        amnesia = mewtwo["moves"][1]
        self.assertEqual((amnesia["name"], amnesia["type"], amnesia["pp_max"]), ("Amnesia", "Psychic", 32))
        self.assertEqual(mewtwo["moves"][2]["type"], "Normal")  # Recover is Normal in Gen 1
        for mon in party:
            self.assertIsNone(mon["ability"])
            self.assertIsNone(mon["nature"])
            self.assertEqual(mon["held_item"], "None")
            self.assertFalse(mon["is_egg"])

    def test_boxes(self) -> None:
        boxes = self.data["boxes"]
        self.assertEqual(len(boxes), 12)
        self.assertTrue(boxes[0]["is_current"])
        self.assertEqual([(m["species_name"], m["level"], m["nickname"]) for m in boxes[0]["pokemon"]],
                         [("Nidoran♂", 5, "NIDORAN♂"), ("Abra", 8, "ABRA")])
        self.assertTrue(all(not b["pokemon"] for b in boxes[1:]))

    def test_daycare_level_comes_from_exp(self) -> None:
        (lax,) = self.data["daycare"]
        self.assertEqual(lax["species_name"], "Snorlax")
        self.assertEqual(lax["nickname"], "LAX")
        self.assertEqual(lax["level"], 31)  # deposited at 30; 37300 EXP >= Slow Lv31 (37238)


# ---------------------------------------------------------------------------
# Golden: a real 21-hour Pokémon Red playthrough (4 badges, Celadon)
# ---------------------------------------------------------------------------

class TestRealPlaySave(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = parse(str(_REALPLAY))

    def test_detected_and_clean(self) -> None:
        self.assertEqual(self.data["save_metadata"]["generation"], 1)
        self.assertEqual(self.data["warnings"], [])

    def test_trainer_and_progress(self) -> None:
        t = self.data["trainer"]
        self.assertEqual((t["name"], t["rival_name"], t["trainer_id"]), ("MY BUTT", "GARY MF", 976))
        self.assertEqual(t["playtime"], {"hours": 21, "minutes": 22, "seconds": 20})
        self.assertEqual((t["money"], t["coins"]), (44012, 0))
        self.assertEqual(self.data["badges"]["obtained"],
                         ["Boulder Badge", "Cascade Badge", "Thunder Badge", "Rainbow Badge"])
        self.assertEqual(self.data["location"]["name"], "Celadon Pokémon Center")
        self.assertEqual(self.data["pokedex"], {"seen": 80, "caught": 30})

    def test_party(self) -> None:
        party = self.data["party"]
        self.assertEqual([(m["species_name"], m["level"]) for m in party], [
            ("Alakazam", 25), ("Geodude", 27), ("Jigglypuff", 26),
            ("Gyarados", 27), ("Charmander", 27), ("Beedrill", 27),
        ])
        gyarados = party[3]
        self.assertEqual(gyarados["types"], ["Water", "Flying"])
        self.assertEqual([m["name"] for m in gyarados["moves"]], ["Bite", "Tackle", "Dragon Rage", "Thunderbolt"])
        self.assertEqual(gyarados["moves"][0]["type"], "Normal")  # Bite is Normal in Gen 1
        self.assertEqual(gyarados["stats"], {"attack": 77, "defense": 54, "speed": 60, "special": 64})

    def test_boxes(self) -> None:
        boxes = self.data["boxes"]
        self.assertEqual(len(boxes[0]["pokemon"]), 16)
        # Bank 2 holds a stale copy of box 1, but the player has never
        # changed boxes (bit 7 clear), so the game ignores the banks.
        self.assertTrue(all(not b["pokemon"] for b in boxes[1:]))
        dux = boxes[0]["pokemon"][11]
        self.assertEqual((dux["species_name"], dux["nickname"], dux["pid"]), ("Farfetch'd", "DUX", "0x0807231C"))

    def test_levels_match_exp(self) -> None:
        species = data_loader.load_gen1_species()
        mons = self.data["party"] + [m for b in self.data["boxes"] for m in b["pokemon"]]
        self.assertEqual(len(mons), 22)
        for mon in mons:
            with self.subTest(mon=mon["species_name"]):
                growth = species[str(mon["species_id"])]["growth_rate"]
                self.assertEqual(pokemon.level_from_exp(mon["experience"], growth), mon["level"])

    def test_inventory(self) -> None:
        inv = self.data["inventory"]
        self.assertEqual(len(inv["items"]), 16)
        self.assertEqual(inv["items"][-1], {"name": "TM21", "quantity": 1})
        self.assertEqual(len(inv["pc"]), 32)
        self.assertIn({"name": "Helix Fossil", "quantity": 1}, inv["pc"])


# ---------------------------------------------------------------------------
# Low-level decoding
# ---------------------------------------------------------------------------

class TestLayoutHelpers(unittest.TestCase):
    def test_string_round_trip(self) -> None:
        for text in ("RED", "NIDORAN♀", "MR.MIME", "A1 B2"):
            with self.subTest(text=text):
                self.assertEqual(layout.decode_string(layout.encode_string(text)), text)

    def test_decode_stops_at_terminator(self) -> None:
        self.assertEqual(layout.decode_string(bytes([0x91, 0x84, 0x83, 0x50, 0x80])), "RED")

    def test_bcd(self) -> None:
        self.assertEqual(layout.bcd(bytes([0x99, 0x99, 0x99])), 999999)
        self.assertEqual(layout.bcd(bytes([0x00, 0x30, 0x00])), 3000)

    def test_checksum_is_complemented_sum(self) -> None:
        self.assertEqual(layout.checksum(bytes([1, 2, 3]), 0, 3), 0xFF - 6)
        self.assertEqual(layout.checksum(bytes([0xFF, 0x01]), 0, 2), 0xFF)

    def test_growth_rates_match_game_totals(self) -> None:
        self.assertEqual(pokemon.exp_for_level(100, "medium_fast"), 1_000_000)
        self.assertEqual(pokemon.exp_for_level(100, "medium_slow"), 1_059_860)
        self.assertEqual(pokemon.exp_for_level(100, "fast"), 800_000)
        self.assertEqual(pokemon.exp_for_level(100, "slow"), 1_250_000)
        for rate in ("medium_fast", "medium_slow", "fast", "slow"):
            for lv in (2, 16, 36, 55, 100):
                with self.subTest(rate=rate, level=lv):
                    self.assertEqual(pokemon.level_from_exp(pokemon.exp_for_level(lv, rate), rate), lv)

    def test_pp_up_bonus_caps_at_seven(self) -> None:
        # 40-PP move with 3 PP Ups: +7 each (8 capped to 7) = 61, the Gen 1 maximum.
        moves = pokemon._format_moves([45, 0, 0, 0], [(3 << 6) | 61, 0, 0, 0])
        self.assertEqual((moves[0]["pp"], moves[0]["pp_max"]), (61, 61))


# ---------------------------------------------------------------------------
# Synthetic mutations of the real save
# ---------------------------------------------------------------------------

class TestSyntheticSaves(unittest.TestCase):
    def test_bad_checksum_rejected(self) -> None:
        sav = _load()
        sav[layout.MONEY] ^= 0x10
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            _parse_bytes(bytes(sav))

    def test_blank_sram_rejected(self) -> None:
        with self.assertRaises(ValueError):
            gen1.parse_bytes(bytes(layout.SAVE_SIZE))

    def test_bank_boxes_ignored_until_boxes_initialised(self) -> None:
        sav = _load()
        _write_bank_box(sav, 3, _box_block([(0x99, 20, 0x1111, "BULBASAUR")]))
        _fix_main_checksum(sav)
        boxes = _parse_bytes(bytes(sav))["boxes"]
        self.assertEqual(boxes[3]["pokemon"], [])

    def test_bank_boxes_and_current_box(self) -> None:
        sav = _load()
        # Current box is box 8 (index 7); boxes initialised.
        sav[layout.CURRENT_BOX] = 0x80 | 7
        _write_bank_box(sav, 0, _box_block([(0x99, 20, 0x1111, "BULBASAUR")]))
        _write_bank_box(sav, 11, _box_block([(0x24, 30, 0x2222, "PIDGEY"), (0x83, 70, 0x3333, "MEWTWO")]))
        # Box 8's bank slot is blanked by the game when it becomes current; put
        # decoy data there to prove the parser reads sCurBoxData instead.
        _write_bank_box(sav, 7, _box_block([(0x84, 50, 0x4444, "DECOY")]))
        _fix_bank_checksums(sav)
        _fix_main_checksum(sav)
        data = _parse_bytes(bytes(sav))
        boxes = data["boxes"]
        self.assertEqual([m["species_name"] for m in boxes[0]["pokemon"]], ["Bulbasaur"])
        self.assertEqual([m["species_name"] for m in boxes[11]["pokemon"]], ["Pidgey", "Mewtwo"])
        self.assertTrue(boxes[7]["is_current"])
        self.assertEqual([m["species_name"] for m in boxes[7]["pokemon"]], ["Nidoran♂", "Abra"])
        self.assertEqual(data["warnings"], [])

    def test_bank_checksum_mismatch_warns(self) -> None:
        sav = _load()
        sav[layout.CURRENT_BOX] = 0x80
        _write_bank_box(sav, 6, _box_block([(0x24, 30, 0x2222, "PIDGEY")]))
        _fix_main_checksum(sav)  # bank checksums deliberately left stale
        data = _parse_bytes(bytes(sav))
        self.assertEqual([m["species_name"] for m in data["boxes"][6]["pokemon"]], ["Pidgey"])
        self.assertTrue(any("bank 3 checksum" in w for w in data["warnings"]))

    def test_duplicate_ot_and_dvs_get_unique_pids(self) -> None:
        sav = _load()
        sav[layout.CURRENT_BOX] = 0x80
        _write_bank_box(sav, 1, _box_block([(0x24, 30, 0xAAAA, "PIDGEY"), (0x24, 31, 0xAAAA, "PIDGEY")]))
        _fix_bank_checksums(sav)
        _fix_main_checksum(sav)
        data = _parse_bytes(bytes(sav))
        pids = [m["pid"] for m in data["boxes"][1]["pokemon"]]
        self.assertEqual(pids, ["0x1234AAAA", "0x1234AAAA-2"])

    def test_glitch_species_warns(self) -> None:
        sav = _load()
        first_box_mon = layout.CUR_BOX_DATA + layout.BOX_MONS
        sav[first_box_mon] = 0x1F  # an unused ("MissingNo.") index
        _fix_main_checksum(sav)
        data = _parse_bytes(bytes(sav))
        mon = data["boxes"][0]["pokemon"][0]
        self.assertTrue(mon["species_name"].startswith("MissingNo."))
        self.assertEqual(mon["types"], ["Unknown"])
        self.assertTrue(data["warnings"])


# ---------------------------------------------------------------------------
# Generation dispatch
# ---------------------------------------------------------------------------

class TestGenerationDispatch(unittest.TestCase):
    def test_detect_by_size(self) -> None:
        self.assertEqual(detect_generation(bytes(0x8000)), 1)
        self.assertEqual(detect_generation(bytes(0x8000 + 0x30)), 1)  # emulator RTC footer
        self.assertEqual(detect_generation(bytes(0x20000)), 3)
        with self.assertRaises(ValueError):
            detect_generation(bytes(1024))

    def test_explicit_gen_overrides_detection(self) -> None:
        with self.assertRaises(ValueError):
            parse(str(_SAVE), gen=3)  # a 32KB file is too small for Gen 3
        self.assertEqual(parse(str(_SAVE), gen=1)["save_metadata"]["generation"], 1)

    def test_unsupported_gen(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported generation"):
            parse(str(_SAVE), gen=2)


# ---------------------------------------------------------------------------
# Sync + diff with a Gen 1 trainer
# ---------------------------------------------------------------------------

class TestGen1Sync(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.users = Path(self._tmp.name)
        user = self.users / "42"
        (user / "memory").mkdir(parents=True)
        (user / "config.json").write_text(json.dumps({
            "game": "red", "gen": 1, "save_filename": "red.sav",
            "device": {"host": "x", "save_path": "/x.sav", "ssh_key": "k"},
        }))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _sync(self, path: str) -> dict:
        return sync.do_sync("42", self.users, local_path=path)

    def test_sync_then_diff(self) -> None:
        first = self._sync(str(_SAVE))
        self.assertEqual(first["status"], "synced")
        self.assertEqual(first["save"]["save_metadata"]["generation"], 1)
        archived = list((self.users / "42/saves/archive").iterdir())
        self.assertEqual(len(archived), 1)
        self.assertTrue(archived[0].name.endswith(".sav"))

        self.assertEqual(self._sync(str(_SAVE))["status"], "unchanged")

        # Level Bulbasaur 12 -> 13, earn a badge, and re-checksum.
        sav = _load()
        sav[layout.PARTY + layout.PARTY_MONS + 33] = 13
        sav[layout.BADGES] |= 0b1000
        _fix_main_checksum(sav)
        second_path = self.users / "second.sav"
        second_path.write_bytes(bytes(sav))
        second = self._sync(str(second_path))
        self.assertEqual(second["status"], "synced")
        diff = second["diff"]
        self.assertEqual(diff["badges_gained"], ["Rainbow Badge"])
        self.assertEqual(diff["leveled"], [
            {"pid": "0xAA6BABCD", "species_name": "Bulbasaur", "from": 12, "to": 13}])
        self.assertEqual(diff["caught"], [])
        self.assertEqual(diff["released_or_traded"], [])

    def test_corrupt_gen1_save_is_invalid(self) -> None:
        sav = _load()
        sav[layout.MONEY] ^= 0x01
        bad = self.users / "bad.sav"
        bad.write_bytes(bytes(sav))
        with self.assertRaises(sync.SyncError) as ctx:
            self._sync(str(bad))
        self.assertEqual(ctx.exception.payload["status"], "invalid_save")

    def test_unsupported_gen_in_config(self) -> None:
        cfg = self.users / "42/config.json"
        cfg.write_text(json.dumps({"game": "gold", "gen": 2, "save_filename": "gold.sav"}))
        with self.assertRaises(sync.SyncError) as ctx:
            self._sync(str(_SAVE))
        self.assertIn("not supported", ctx.exception.payload["error"])

    def test_compact_box_mon_drops_gen3_only_fields(self) -> None:
        save = parse(str(_SAVE))
        compact = sync._compact_save_for_stdout(save)
        mon = compact["boxes"][0]["pokemon"][0]
        for key in ("ability", "nature", "nature_effect"):
            self.assertNotIn(key, mon)
        self.assertEqual(mon["moves"], ["Leer", "Tackle"])


if __name__ == "__main__":
    unittest.main()
