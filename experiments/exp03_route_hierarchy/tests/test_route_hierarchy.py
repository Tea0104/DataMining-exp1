"""Source-grounded regressions and explicitly synthetic parser fixtures."""

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1]
ROOT = MODULE.parents[1]
sys.path.insert(0, str(MODULE / "src"))
from route_hierarchy import Extractor, compare, lcs_length, run, split_top_level, validate_evidence


class RouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = json.loads((ROOT / "data/processed/sample_v1.json").read_text(encoding="utf-8"))
        cls.records = {r["doc_id"]: r for r in cls.records if r["scenic_id"] == "huangshan"}
        cls.extractor = Extractor(json.loads((MODULE / "config/huangshan_pois.json").read_text(encoding="utf-8")))
        cls.official = cls.extractor.official(cls.records["HS_OFF_001"])
        cls.observed, cls.declared = cls.extractor.tourist(cls.records["HS_NOTE_001"])

    def fixture(self, text, kind="tourist_note"):
        # Synthetic input for regression testing, never written into shared data.
        return {"doc_id": "SYNTHETIC", "scenic_id": "huangshan", "scenic_name": "黄山风景区",
                "source_url": "synthetic:test", "text_type": kind, "clean_text": text}

    def test_official_or_is_choice_not_two_sequential_stops(self):
        choices = [s for s in self.official["steps"] if s.get("choices")]
        self.assertEqual(choices[0]["choices"], ["云谷索道", "太平索道"])
        self.assertNotIn("太平索道", [s["poi"] for s in self.official["steps"]])

    def test_optional_detour_returns_to_its_anchor(self):
        branch = self.official["optional_branches"][0]
        self.assertEqual([s["poi"] for s in branch["steps"]], ["光明顶", "天海"])
        self.assertTrue(branch["steps"][-1]["return_to_anchor"])
        self.assertIn(branch["anchor_step_id"], [s["step_id"] for s in self.official["steps"]])
        self.assertNotIn("光明顶", [s["poi"] for s in self.official["steps"]])

    def test_remote_view_is_not_an_actual_stop(self):
        self.assertEqual({s["poi"] for s in self.official["non_main_mentions"]}, {"光明顶", "飞来石"})
        self.assertNotIn("飞来石", [s["poi"] for s in self.official["steps"]])

    def test_negated_list_stop_keeps_both_source_evidences(self):
        self.assertNotIn("一线天", [s["poi"] for s in self.declared["steps"]])
        excluded = self.declared["excluded_steps"][0]
        self.assertEqual(excluded["poi"], "一线天")
        self.assertIn("未能前往", excluded["contradiction_evidence"]["text"])
        self.assertIn("一线天", excluded["evidence"]["text"])

    def test_future_and_other_travellers_do_not_become_visits(self):
        names = [s["poi"] for s in self.observed["steps"]]
        for name in ("迎客松", "前山", "后山", "东黄山旅游度假区"):
            self.assertNotIn(name, names)

    def test_retrospective_departure_does_not_fabricate_return(self):
        names = [s["poi"] for s in self.observed["steps"] if s["day"] == 2]
        self.assertEqual(names, ["西海饭店", "光明顶", "徽味楼"])

    def test_unknown_times_are_not_filled_by_route_order(self):
        self.assertTrue(all(s["time_period"] == "unknown" and s["time"] is None for s in self.official["steps"]))
        self.assertTrue(any(s["time_period"] == "morning" for s in self.observed["steps"]))
        self.assertEqual([d["day"] for d in self.observed["time_hierarchy"]], [1, 2])

    def test_conservative_normalization_preserves_parent_and_hotel(self):
        mentions = self.extractor.mentions("光明顶山庄、光明顶；天海宾馆、天海；云谷寺索道、云谷寺")
        self.assertEqual([m["name"] for m in mentions], ["光明顶山庄", "光明顶", "天海宾馆", "天海", "云谷索道", "云谷寺"])

    def test_nested_arrow_is_not_a_main_route_separator(self):
        text = "天海（如体力可行，光明顶→天海）→海心亭"
        self.assertEqual([text[a:b] for a, b in split_top_level(text)], ["天海（如体力可行，光明顶→天海）", "海心亭"])

    def test_numbered_format_and_explicit_time(self):
        result = self.extractor.official(self.fixture("1. 上午游览始信峰\n2. 下午游览光明顶", "official_route"))
        self.assertEqual(result["format"], "numbered")
        self.assertEqual([s["time_period"] for s in result["steps"]], ["morning", "afternoon"])

    def test_unicode_coordinates_after_non_bmp_emoji(self):
        record = self.fixture("⛰️😀 到了始信峰。")
        observed, declared = self.extractor.tourist(record)
        validate_evidence([observed, declared], {record["doc_id"]: record})
        step = observed["steps"][0]
        span = step["mention_span"]
        self.assertEqual(record["clean_text"][span["start"]:span["end"]], "始信峰")

    def test_all_exported_evidence_resolves_to_clean_text(self):
        validate_evidence([self.official, self.observed, self.declared], self.records)

    def test_lcs_retains_repeated_visits(self):
        self.assertEqual(lcs_length(["A", "B", "A"], ["A", "A"]), 2)
        self.assertEqual(lcs_length([], ["A"]), 0)
        self.assertEqual(lcs_length(["A"], ["B"]), 0)

    def test_order_not_reported_with_one_or_no_shared_poi(self):
        for route in (self.observed, self.declared):
            result = compare(self.official, route)
            self.assertIsNone(result["shared_order_lcs_dice"])
            self.assertGreaterEqual(result["poi_jaccard"], 0)
            self.assertLessEqual(result["poi_jaccard"], 1)

    def test_pipeline_filters_huangshan_and_is_deterministic(self):
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(StringIO()):
            target = Path(folder)
            result = run(ROOT / "data/processed/sample_v1.json", target)
            first = {p.name: p.read_bytes() for p in target.iterdir()}
            run(ROOT / "data/processed/sample_v1.json", target)
            self.assertEqual(first, {p.name: p.read_bytes() for p in target.iterdir()})
            self.assertEqual(set(result["input_doc_ids"]), {"HS_OFF_001", "HS_NOTE_001"})
            self.assertTrue(all(r["scenic_id"] == "huangshan" for r in result["routes"]))

    def test_other_scenic_area_requires_its_own_config(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "配置景区"):
                run(ROOT / "data/processed/sample_v1.json", Path(folder), "gugong")

    def test_missing_tourist_record_fails_before_export(self):
        with tempfile.TemporaryDirectory() as folder:
            input_path = Path(folder) / "input.json"
            input_path.write_text(json.dumps([self.records["HS_OFF_001"]]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "游客游记"):
                run(input_path, Path(folder) / "out")
            self.assertFalse((Path(folder) / "out").exists())


if __name__ == "__main__":
    unittest.main()
