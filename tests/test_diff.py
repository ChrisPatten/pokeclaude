"""Unit tests for parser.diff.diff_saves.

Fixtures are hand-written dicts that follow the CONTRACT.md parser-output
schema. They intentionally do NOT depend on the real parser (workstream A is
still adding pid/types/ability/nature_effect to it), so these tests stay
green regardless of that work's progress.
"""

import copy
import unittest

from parser.diff import diff_saves


def _move(name, move_type="Normal", move_id=1, slot=0, pp=35, pp_max=35):
    return {"slot": slot, "move_id": move_id, "name": name, "type": move_type, "pp": pp, "pp_max": pp_max}


def _mon(pid, species_name, level=10, nickname=None, moves=None, held_item="None",
         nature="Adamant", types=None, ability="Blaze", slot=0, is_egg=False):
    return {
        "slot": slot,
        "pid": pid,
        "species_id": 1,
        "species_name": species_name,
        "nickname": nickname or species_name.upper(),
        "types": types or ["Fire"],
        "ability": ability,
        "level": level,
        "experience": level * 100,
        "nature": nature,
        "nature_effect": "Atk↑, SpAtk↓",
        "held_item": held_item,
        "moves": moves if moves is not None else [_move("Scratch")],
        "is_egg": is_egg,
    }


def _party_mon(pid, species_name, **kwargs):
    mon = _mon(pid, species_name, **kwargs)
    mon["status"] = "none"
    mon["hp"] = {"current": 30, "max": 30}
    mon["stats"] = {"attack": 20, "defense": 18, "speed": 15, "sp_atk": 10, "sp_def": 10}
    return mon


def _base_save(**overrides):
    save = {
        "trainer": {
            "name": "May",
            "gender": "female",
            "trainer_id": 12345,
            "playtime": {"hours": 10, "minutes": 0, "seconds": 0},
            "money": 1000,
        },
        "badges": {"count": 3, "obtained": ["Stone Badge", "Knuckle Badge", "Dynamo Badge"]},
        "location": {"map_bank": 0, "map_id": 1, "name": "Fallarbor Town", "known": True},
        "party": [],
        "boxes": [{"box_index": 1, "name": "BOX 1", "pokemon": []}],
        "daycare": [],
        "inventory": {
            "pc": [],
            "items": [],
            "key_items": [],
            "balls": [],
            "tms_hms": [],
            "berries": [],
        },
        "pokedex": {"seen": 50, "caught": 20},
        "save_metadata": {
            "save_slot": "A",
            "save_index": 5,
            "checksum_valid": True,
            "invalid_sections": [],
            "parsed_at": "2026-04-01T00:00:00Z",
        },
        "warnings": [],
    }
    save.update(copy.deepcopy(overrides))
    return save


EMPTY_POCKET_DELTA = {"added": {}, "removed": {}, "changed": {}}


class NoChangeTests(unittest.TestCase):
    def test_identical_saves_produce_an_empty_diff(self):
        old = _base_save(party=[_party_mon("0x1", "Torchic", level=10)])
        new = copy.deepcopy(old)

        result = diff_saves(old, new)

        self.assertIsNone(result["location"])
        self.assertEqual(result["badges_gained"], [])
        self.assertEqual(result["money"], {"from": 1000, "to": 1000, "delta": 0})
        self.assertEqual(result["playtime_minutes_delta"], 0)
        self.assertEqual(result["pokedex"], {"seen_delta": 0, "caught_delta": 0})
        self.assertEqual(result["party"], {"added": [], "removed": [], "changed": []})
        self.assertEqual(result["caught"], [])
        self.assertEqual(result["released_or_traded"], [])
        self.assertEqual(result["evolved"], [])
        self.assertEqual(result["leveled"], [])
        self.assertEqual(result["moves_changed"], [])
        self.assertEqual(result["held_items_changed"], [])
        self.assertIsNone(result["daycare"])
        for pocket in ("pc", "items", "key_items", "balls", "tms_hms", "berries"):
            self.assertEqual(result["inventory"][pocket], EMPTY_POCKET_DELTA)


class LocationBadgesMoneyPlaytimeDexTests(unittest.TestCase):
    def test_location_change(self):
        old = _base_save()
        new = _base_save(location={"map_bank": 0, "map_id": 2, "name": "Lavaridge Town", "known": True})
        result = diff_saves(old, new)
        self.assertEqual(result["location"], {"from": "Fallarbor Town", "to": "Lavaridge Town"})

    def test_badges_gained(self):
        old = _base_save(badges={"count": 1, "obtained": ["Stone Badge"]})
        new = _base_save(badges={"count": 2, "obtained": ["Stone Badge", "Knuckle Badge"]})
        result = diff_saves(old, new)
        self.assertEqual(result["badges_gained"], ["Knuckle Badge"])

    def test_money_and_playtime_and_pokedex_deltas(self):
        old = _base_save()
        old["trainer"]["playtime"] = {"hours": 10, "minutes": 0, "seconds": 0}
        old["trainer"]["money"] = 1000
        old["pokedex"] = {"seen": 50, "caught": 20}

        new = _base_save()
        new["trainer"]["playtime"] = {"hours": 10, "minutes": 5, "seconds": 30}
        new["trainer"]["money"] = 1500
        new["pokedex"] = {"seen": 55, "caught": 22}

        result = diff_saves(old, new)
        self.assertEqual(result["money"], {"from": 1000, "to": 1500, "delta": 500})
        self.assertEqual(result["playtime_minutes_delta"], 5)  # 330s -> 5 whole minutes
        self.assertEqual(result["pokedex"], {"seen_delta": 5, "caught_delta": 2})


class EvolutionTests(unittest.TestCase):
    def test_same_pid_different_species_is_an_evolution(self):
        # Same nickname on both sides so only species/evolution is exercised.
        old = _base_save(party=[_party_mon("0x1", "Torchic", level=16, nickname="BLAZE")])
        new = _base_save(party=[_party_mon("0x1", "Combusken", level=16, nickname="BLAZE")])

        result = diff_saves(old, new)

        self.assertEqual(result["evolved"], [{"pid": "0x1", "from": "Torchic", "to": "Combusken"}])
        self.assertEqual(result["leveled"], [])
        self.assertEqual(
            result["party"]["changed"],
            [{"pid": "0x1", "species_name": "Combusken", "changes": ["evolved"]}],
        )


class CatchTests(unittest.TestCase):
    def test_new_pid_anywhere_is_caught(self):
        old = _base_save()
        new = _base_save(
            boxes=[{"box_index": 1, "name": "BOX 1", "pokemon": [_mon("0xCAFE", "Zigzagoon", level=5)]}]
        )

        result = diff_saves(old, new)

        self.assertEqual(
            result["caught"],
            [{"pid": "0xCAFE", "species_name": "Zigzagoon", "level": 5, "where": "box 1"}],
        )


class ReleaseOrTradeTests(unittest.TestCase):
    def test_pid_missing_everywhere_is_released_or_traded(self):
        old = _base_save(party=[_party_mon("0xBEEF", "Wingull", level=8)])
        new = _base_save(party=[])

        result = diff_saves(old, new)

        self.assertEqual(
            result["released_or_traded"],
            [{"pid": "0xBEEF", "species_name": "Wingull", "level": 8, "where": "party"}],
        )


class LevelUpTests(unittest.TestCase):
    def test_level_increase_is_tracked_globally_and_in_party_changed(self):
        old = _base_save(party=[_party_mon("0x1", "Torchic", level=10)])
        new = _base_save(party=[_party_mon("0x1", "Torchic", level=12)])

        result = diff_saves(old, new)

        self.assertEqual(
            result["leveled"], [{"pid": "0x1", "species_name": "Torchic", "from": 10, "to": 12}]
        )
        self.assertEqual(
            result["party"]["changed"],
            [{"pid": "0x1", "species_name": "Torchic", "changes": ["leveled_up"]}],
        )


class MoveChangeTests(unittest.TestCase):
    def test_moves_learned_and_forgotten(self):
        old = _base_save(
            party=[_party_mon("0x1", "Torchic", moves=[_move("Scratch"), _move("Growl")])]
        )
        new = _base_save(
            party=[_party_mon("0x1", "Torchic", moves=[_move("Scratch"), _move("Ember", "Fire")])]
        )

        result = diff_saves(old, new)

        self.assertEqual(
            result["moves_changed"],
            [{"pid": "0x1", "species_name": "Torchic", "learned": ["Ember"], "forgot": ["Growl"]}],
        )


class HeldItemChangeTests(unittest.TestCase):
    def test_held_item_change(self):
        old = _base_save(party=[_party_mon("0x1", "Torchic", held_item="None")])
        new = _base_save(party=[_party_mon("0x1", "Torchic", held_item="Silk Scarf")])

        result = diff_saves(old, new)

        self.assertEqual(
            result["held_items_changed"],
            [{"pid": "0x1", "species_name": "Torchic", "from": "None", "to": "Silk Scarf"}],
        )


class PartyBoxSwapTests(unittest.TestCase):
    def test_deposit_to_box_shows_up_as_party_removed_with_box_location(self):
        mon = _party_mon("0x1", "Skarmory", level=30)
        old = _base_save(
            party=[mon], boxes=[{"box_index": 1, "name": "BOX 1", "pokemon": []}]
        )
        boxed_mon = _mon("0x1", "Skarmory", level=30)
        new = _base_save(
            party=[], boxes=[{"box_index": 1, "name": "BOX 1", "pokemon": [boxed_mon]}]
        )

        result = diff_saves(old, new)

        self.assertEqual(result["party"]["added"], [])
        self.assertEqual(
            result["party"]["removed"],
            [{"pid": "0x1", "species_name": "Skarmory", "level": 30, "where": "box 1"}],
        )

    def test_withdraw_from_box_shows_up_as_party_added(self):
        boxed_mon = _mon("0x2", "Golem", level=32)
        old = _base_save(
            party=[], boxes=[{"box_index": 1, "name": "BOX 1", "pokemon": [boxed_mon]}]
        )
        mon = _party_mon("0x2", "Golem", level=32)
        new = _base_save(
            party=[mon], boxes=[{"box_index": 1, "name": "BOX 1", "pokemon": []}]
        )

        result = diff_saves(old, new)

        self.assertEqual(
            result["party"]["added"],
            [{"pid": "0x2", "species_name": "Golem", "level": 32, "where": "party"}],
        )
        self.assertEqual(result["party"]["removed"], [])


class InventoryDeltaTests(unittest.TestCase):
    def test_added_removed_and_changed_quantities_per_pocket(self):
        old = _base_save(
            inventory={
                "pc": [],
                "items": [{"name": "Potion", "quantity": 5}, {"name": "Repel", "quantity": 2}],
                "key_items": ["Bike"],
                "balls": [{"name": "Poke Ball", "quantity": 10}],
                "tms_hms": [],
                "berries": [],
            }
        )
        new = _base_save(
            inventory={
                "pc": [],
                "items": [
                    {"name": "Potion", "quantity": 3},
                    {"name": "Super Potion", "quantity": 1},
                ],
                "key_items": ["Bike", "Devon Scope"],
                "balls": [{"name": "Poke Ball", "quantity": 10}],
                "tms_hms": [],
                "berries": [],
            }
        )

        result = diff_saves(old, new)

        self.assertEqual(
            result["inventory"]["items"],
            {
                "added": {"Super Potion": 1},
                "removed": {"Repel": 2},
                "changed": {"Potion": {"from": 5, "to": 3}},
            },
        )
        self.assertEqual(
            result["inventory"]["key_items"],
            {"added": {"Devon Scope": 1}, "removed": {}, "changed": {}},
        )
        self.assertEqual(result["inventory"]["balls"], EMPTY_POCKET_DELTA)


class DaycareTests(unittest.TestCase):
    def test_unchanged_daycare_membership_is_null(self):
        mon = _mon("0x9", "Wynaut", level=5)
        old = _base_save(daycare=[mon])
        new = _base_save(daycare=[_mon("0x9", "Wynaut", level=9)])  # leveled, same pid

        result = diff_saves(old, new)

        self.assertIsNone(result["daycare"])
        # Still tracked globally even though daycare membership didn't change.
        self.assertEqual(
            result["leveled"], [{"pid": "0x9", "species_name": "Wynaut", "from": 5, "to": 9}]
        )

    def test_daycare_membership_change_reports_from_to(self):
        old = _base_save(daycare=[])
        new = _base_save(daycare=[_mon("0xAB", "Magikarp", level=5)])

        result = diff_saves(old, new)

        self.assertEqual(
            result["daycare"],
            {
                "from": [],
                "to": [{"pid": "0xAB", "species_name": "Magikarp", "level": 5, "where": "daycare"}],
            },
        )


if __name__ == "__main__":
    unittest.main()
