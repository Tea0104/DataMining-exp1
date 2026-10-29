"""Exercise real project 2 consumption, validation and identity preservation."""

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
from entity_source import EntityIndex
from route_hierarchy import Extractor, run, validate_evidence


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.input_path = ROOT / "data/processed/sample_v1.json"
        cls.entity_path = ROOT / "experiments/exp02_entity_recognition/outputs/entities_v2.json"
        cls.raw_entities = json.loads(cls.entity_path.read_text(encoding="utf-8"))
        cls.records = {r["doc_id"]: r for r in json.loads(cls.input_path.read_text(encoding="utf-8")) if r["scenic_id"] == "huangshan"}
        cls.index = EntityIndex(cls.entity_path, cls.records)
        cls.extractor = Extractor(json.loads((MODULE / "config/huangshan_pois.json").read_text(encoding="utf-8")), cls.index)
        cls.observed, cls.declared = cls.extractor.tourist(cls.records["HS_NOTE_001"])
        cls.official = cls.extractor.official(cls.records["HS_OFF_001"])

    def test_all_hundred_mentions_have_valid_original_positions(self):
        self.assertEqual(self.index.metadata["entity_mentions"], 100)
        self.assertEqual(self.index.metadata["by_type"], {"POI": 65, "TRANSPORT": 23, "TIME": 12})
        validate_evidence(self.index.entities, self.records)

    def test_shared_canonical_does_not_merge_named_cableways(self):
        first = self.official["steps"][0]
        self.assertEqual(first["choices"], ["云谷索道", "太平索道"])
        ids = [m["source_entity_id"] for m in first["choice_mentions"]]
        self.assertEqual(len(set(ids)), 2)
        source = {e["entity_id"]: e for e in self.index.entities}
        self.assertEqual({source[e]["canonical"] for e in ids}, {"索道"})

    def test_exp02_clock_is_attached_to_trip_end_not_a_scenic_stop(self):
        ends = [s for s in self.observed["steps"] if s["extraction_rule"] == "explicit_trip_end"]
        self.assertEqual(len(ends), 1)
        self.assertEqual((ends[0]["day"], ends[0]["time"], ends[0]["time_period"]), (2, "21:00", "evening"))
        self.assertIsNone(ends[0]["poi"])
        self.assertTrue(ends[0]["assigned_time_entity_ids"])

    def test_duration_does_not_become_stop_duration(self):
        self.assertTrue(all(s["duration_minutes"] is None for s in self.observed["steps"]))
        self.assertEqual(len([e for e in self.index.entities if e["subtype"] == "duration"]), 2)

    def test_split_place_and_cableway_is_flagged_without_forced_alias(self):
        self.assertNotIn("云谷索道", [s["poi"] for s in self.observed["steps"]])
        self.assertNotIn("云谷寺", [s["poi"] for s in self.observed["steps"]])
        self.assertTrue(any(s["visit_status"] == "boundary_ambiguous" for s in self.observed["non_main_mentions"]))
        transport = next(s for s in self.observed["steps"] if s["extraction_rule"] == "unresolved_transport_activity")
        self.assertTrue(transport["transport_entity_ids"])

    def test_every_named_step_points_to_a_real_upstream_mention(self):
        source = {e["entity_id"]: e for e in self.index.entities}
        for route in (self.observed, self.declared, self.official):
            for step in route["steps"]:
                if step["poi"]:
                    entity = source[step["source_entity_id"]]
                    self.assertEqual(entity["text"], step["surface"])
                    self.assertEqual(entity["start"], step["mention_span"]["start"])

    def test_deleting_upstream_poi_changes_parser_output_without_lexicon_fallback(self):
        modified = [e for e in self.raw_entities if e["text"] != "海心亭"]
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(StringIO()):
            path = Path(folder) / "entities.json"
            path.write_text(json.dumps(modified), encoding="utf-8")
            result = run(self.input_path, Path(folder) / "out", entities_path=path)
            self.assertTrue(all(s["poi"] != "海心亭" for r in result["routes"] for s in r["steps"]))
            self.assertEqual(result["entity_source"], "exp02_entities_v2")

    def test_stale_or_corrupt_entity_span_fails_before_export(self):
        modified = [dict(e) for e in self.raw_entities]
        modified[0]["start"] += 1
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "entities.json"
            path.write_text(json.dumps(modified), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "clean_text不一致"):
                run(self.input_path, Path(folder) / "out", entities_path=path)
            self.assertFalse((Path(folder) / "out").exists())

    def test_entity_types_and_doc_ids_are_validated(self):
        for field, value in (("entity_type", "INVALID"), ("doc_id", "GG_NOTE_001")):
            modified = [dict(e) for e in self.raw_entities]
            modified[0][field] = value
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "entities.json"
                path.write_text(json.dumps(modified), encoding="utf-8")
                with self.assertRaises(ValueError):
                    EntityIndex(path, self.records)

    def test_missing_upstream_file_is_not_silently_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileNotFoundError):
                run(self.input_path, Path(folder) / "out", entities_path=Path(folder)/"missing.json")

    def test_html_contains_clock_end_event_and_no_duplicate_step_numbering(self):
        from route_hierarchy import render_html
        rendered = render_html([self.observed])
        self.assertIn("行程结束", rendered)
        self.assertNotIn("<ol>", rendered)


if __name__ == "__main__":
    unittest.main()
