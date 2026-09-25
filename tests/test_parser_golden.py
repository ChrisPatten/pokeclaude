"""Golden tests against a real Pokémon Sapphire save file.

Skipped entirely if tests/fixtures/sapphire.srm is not present (it is
gitignored — copy it from users/<telegram_user_id>/saves/sapphire.srm to run these).

The full-output snapshot test additionally needs tests/fixtures/sapphire.golden.json
(also gitignored). Regenerate it with:

    UPDATE_GOLDEN=1 python3 -m unittest tests.test_parser_golden

Before trusting a regenerated golden file, run scripts/verify_golden.py
against the same save — it independently cross-checks every Mon against
data/gen_3/ reference data and will flag anything a blind snapshot would
otherwise silently freeze in.
"""

import copy
import json
import os
import unittest
from pathlib import Path

from parser import data_loader
from parser.parse_save import parse
from parser.pokemon import _estimate_level

_FIXTURE = Path(__file__).parent / "fixtures" / "sapphire.srm"
_GOLDEN_JSON = Path(__file__).parent / "fixtures" / "sapphire.golden.json"

# Mon dict keys every Mon (party/box/daycare) must carry per the shared contract.
_COMMON_MON_KEYS = {
    "slot", "pid", "species_id", "species_name", "nickname", "types",
    "ability", "level", "experience", "nature", "nature_effect",
    "held_item", "moves", "is_egg",
}
_PARTY_ONLY_KEYS = {"status", "hp", "stats"}

# Shedinja is created with the exact same personality value (and therefore
# the same "pid") as the Ninjask it split from — a documented Gen III game
# mechanic, not a parsing bug. The pid-uniqueness check below allows this
# one well-known exception.
_KNOWN_SHARED_PID_SPECIES = {"Ninjask", "Shedinja"}

# The real trainer name/id/money belong to whoever owns the (gitignored,
# never committed) save fixture this test runs against — they must not be
# hardcoded here since this file is tracked in a public repo. Instead, read
# them from the gitignored golden fixture at test time; if that file isn't
# present, test_trainer skips itself rather than failing against synthetic
# placeholders.
def _load_golden_trainer() -> dict | None:
    if not _GOLDEN_JSON.exists():
        return None
    with open(_GOLDEN_JSON, encoding="utf-8") as f:
        return json.load(f)["trainer"]


@unittest.skipUnless(_FIXTURE.exists(), "tests/fixtures/sapphire.srm not present")
class TestGoldenSave(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = parse(str(_FIXTURE))

    def _all_mons(self):
        for m in self.result["party"]:
            yield "party", m
        for box in self.result["boxes"]:
            for m in box["pokemon"]:
                yield f"box {box['box_index']}", m
        for m in self.result["daycare"]:
            yield "daycare", m

    # -- Ground truth: trainer / progress -------------------------------

    def test_trainer(self) -> None:
        golden_trainer = _load_golden_trainer()
        if golden_trainer is None:
            self.skipTest(
                f"{_GOLDEN_JSON} not present; test_trainer needs it for the "
                "expected (personal) trainer name/id/money instead of "
                "hardcoding them in this public file"
            )
        trainer = self.result["trainer"]
        self.assertEqual(trainer["name"], golden_trainer["name"])
        self.assertEqual(trainer["trainer_id"], golden_trainer["trainer_id"])
        self.assertEqual(trainer["money"], golden_trainer["money"])

    def test_badges(self) -> None:
        self.assertEqual(self.result["badges"]["count"], 6)

    def test_location(self) -> None:
        self.assertEqual(self.result["location"]["name"], "Route 117")
        self.assertTrue(self.result["location"]["known"])

    def test_pokedex(self) -> None:
        self.assertEqual(self.result["pokedex"]["seen"], 126)
        self.assertEqual(self.result["pokedex"]["caught"], 92)

    def test_save_metadata(self) -> None:
        meta = self.result["save_metadata"]
        self.assertTrue(meta["checksum_valid"])
        self.assertEqual(meta["invalid_sections"], [])

    # -- Ground truth: party ---------------------------------------------

    def test_party_species_and_levels(self) -> None:
        expected = {
            "Tropius": 26, "Altaria": 37, "Sableye": 37,
            "Azumarill": 36, "Manectric": 36, "Alakazam": 32,
        }
        actual = {m["species_name"]: m["level"] for m in self.result["party"]}
        self.assertEqual(actual, expected)

    def test_altaria_types(self) -> None:
        altaria = next(m for m in self.result["party"] if m["species_name"] == "Altaria")
        self.assertEqual(altaria["types"], ["Dragon", "Flying"])

    # -- Ground truth: daycare --------------------------------------------

    def test_daycare(self) -> None:
        # NOTE: the levels here are 20/22, not the 22/18 originally quoted as
        # "known ground truth". Daycare Pokemon have no stored level in Gen 3
        # save data -- the level is always derived from EXP + growth rate, and
        # the original 22/18 figures were themselves produced by the parser's
        # pre-fix growth_rates.json (Baltoy as medium_slow, Trapinch as slow).
        # Cross-checked against two independent decompilations (pret/pokeruby
        # and pret/pokeemerald), which both agree Baltoy is medium_fast and
        # Trapinch is medium_slow -- giving 20 and 22 respectively. See
        # scripts/verify_data_vs_pokeruby.py.
        expected = {"Baltoy": 20, "Trapinch": 22}
        actual = {m["species_name"]: m["level"] for m in self.result["daycare"]}
        self.assertEqual(actual, expected)

    # -- Ground truth: boxes ----------------------------------------------

    def test_box_counts(self) -> None:
        boxes = {b["box_index"]: len(b["pokemon"]) for b in self.result["boxes"]}
        self.assertEqual(boxes[0], 30)
        self.assertEqual(boxes[1], 30)
        self.assertEqual(boxes[2], 6)
        self.assertEqual(boxes[13], 1)

    def test_box14_is_sandshrew(self) -> None:
        box14 = next(b for b in self.result["boxes"] if b["box_index"] == 13)
        self.assertEqual(len(box14["pokemon"]), 1)
        self.assertEqual(box14["pokemon"][0]["species_name"], "Sandshrew")

    # -- Cross-checks -------------------------------------------------------

    def test_party_exp_derived_level_matches_stored_level(self) -> None:
        """Strong cross-check of the growth-rate tables: independently
        deriving each party mon's level from its EXP must match the level
        byte the game actually stored."""
        growth_rates = data_loader.load_growth_rates()
        for m in self.result["party"]:
            growth_rate = growth_rates.get(str(m["species_id"]), "medium_fast")
            derived = _estimate_level(m["experience"], growth_rate)
            with self.subTest(species=m["species_name"]):
                self.assertEqual(derived, m["level"])

    def test_every_mon_has_contract_keys(self) -> None:
        for where, mon in self._all_mons():
            with self.subTest(where=where, mon=mon.get("species_name")):
                missing = _COMMON_MON_KEYS - mon.keys()
                self.assertFalse(missing, f"{where} mon missing keys: {missing}")
                if where == "party":
                    missing_party = _PARTY_ONLY_KEYS - mon.keys()
                    self.assertFalse(missing_party, f"party mon missing keys: {missing_party}")

    def test_moves_have_pp_and_pp_max(self) -> None:
        for where, mon in self._all_mons():
            for move in mon["moves"]:
                with self.subTest(where=where, mon=mon.get("species_name"), move=move.get("name")):
                    self.assertIn("pp", move)
                    self.assertIn("pp_max", move)

    def test_no_unknown_ability_for_non_eggs(self) -> None:
        offenders = [
            (where, mon["species_name"])
            for where, mon in self._all_mons()
            if not mon["is_egg"] and mon["ability"] == "Unknown"
        ]
        self.assertEqual(offenders, [])

    def test_pid_unique_across_save(self) -> None:
        from collections import Counter

        pids = Counter(mon["pid"] for _, mon in self._all_mons())
        duplicates = {pid: count for pid, count in pids.items() if count > 1}

        for pid, count in duplicates.items():
            species = {mon["species_name"] for _, mon in self._all_mons() if mon["pid"] == pid}
            with self.subTest(pid=pid, species=species):
                # The only legitimate duplicate is Shedinja sharing its
                # personality value with the Ninjask it split from.
                self.assertTrue(
                    species <= _KNOWN_SHARED_PID_SPECIES,
                    f"Unexpected duplicate pid {pid} shared by {species}",
                )


# ---------------------------------------------------------------------------
# Full-output snapshot vs tests/fixtures/sapphire.golden.json
# ---------------------------------------------------------------------------

def _normalize(result: dict) -> dict:
    """Strip fields that legitimately change on every run."""
    result = copy.deepcopy(result)
    result.get("save_metadata", {}).pop("parsed_at", None)
    return result


def _diff_paths(actual, expected, path: str = "") -> list[str]:
    """Return a list of human-readable 'path: actual != expected' strings
    for every difference between two JSON-shaped values."""
    diffs: list[str] = []

    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(actual) | set(expected), key=str):
            sub_path = f"{path}.{key}" if path else str(key)
            if key not in actual:
                diffs.append(f"{sub_path}: missing in actual output (golden has {expected[key]!r})")
            elif key not in expected:
                diffs.append(f"{sub_path}: unexpected in actual output ({actual[key]!r}, not in golden)")
            else:
                diffs.extend(_diff_paths(actual[key], expected[key], sub_path))
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(actual) != len(expected):
            diffs.append(f"{path}: length {len(actual)} != golden length {len(expected)}")
        for i, (a, e) in enumerate(zip(actual, expected)):
            diffs.extend(_diff_paths(a, e, f"{path}[{i}]"))
    else:
        if actual != expected:
            diffs.append(f"{path}: {actual!r} != {expected!r}")

    return diffs


@unittest.skipUnless(_FIXTURE.exists(), "tests/fixtures/sapphire.srm not present")
class TestGoldenFullOutput(unittest.TestCase):
    """Compares the ENTIRE parser output for the real save against a frozen
    snapshot, not just the spot-checks above. See module docstring for how
    to (re)generate tests/fixtures/sapphire.golden.json."""

    def test_full_output_matches_golden(self) -> None:
        actual = _normalize(parse(str(_FIXTURE)))

        if os.environ.get("UPDATE_GOLDEN"):
            with open(_GOLDEN_JSON, "w", encoding="utf-8") as f:
                json.dump(actual, f, indent=2, ensure_ascii=False, sort_keys=True)
                f.write("\n")
            print(f"\nUPDATE_GOLDEN=1: wrote {_GOLDEN_JSON}")
            return

        if not _GOLDEN_JSON.exists():
            self.skipTest(
                f"{_GOLDEN_JSON} not present. Generate it with: "
                "UPDATE_GOLDEN=1 python3 -m unittest tests.test_parser_golden "
                "(after checking scripts/verify_golden.py is clean)"
            )

        with open(_GOLDEN_JSON, encoding="utf-8") as f:
            expected = json.load(f)

        diffs = _diff_paths(actual, expected)
        if diffs:
            preview = "\n".join(diffs[:50])
            more = f"\n... and {len(diffs) - 50} more" if len(diffs) > 50 else ""
            self.fail(f"Full output diverged from golden ({len(diffs)} differences):\n{preview}{more}")


if __name__ == "__main__":
    unittest.main()
