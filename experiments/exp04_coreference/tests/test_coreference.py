"""共指语义、字符位置和评价口径的回归测试。"""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from common import span, text_hash, validate_span
from detect import detect_record
from evaluate import compare, validate_gold
from resolve import choose, nominal_candidates, render_annotations


def record(text):
    return {'doc_id': 'demo', 'scenic_id': 'TEST', 'clean_text': text, 'source_url': 'local-test'}


class CoreferenceTests(unittest.TestCase):
    def test_occurrences_and_longest_pronoun(self):
        samples = detect_record(record('🐒猴子来了，它们看着它，它又跑走了。'))
        self.assertEqual([s['pronoun']['text'] for s in samples], ['它们', '它', '它'])
        self.assertEqual(len({s['sample_id'] for s in samples}), 3)
        for sample in samples:
            validate_span('🐒猴子来了，它们看着它，它又跑走了。', sample['pronoun'])

    def test_lexical_non_pronouns_are_excluded(self):
        self.assertEqual(detect_record(record('其他人应该这样走，因此无需那么急，此外还有他人。')), [])

    def test_animal_survives_intervening_object(self):
        text = '猴子拿着栗子，它跳走了。'
        candidates = nominal_candidates(record(text), [])
        sample = detect_record(record(text))[0]
        base, _, _ = choose(sample, text, candidates, 'v1')
        improved, _, _ = choose(sample, text, candidates, 'v2')
        self.assertEqual(base['text'], '栗子')
        self.assertEqual(improved['text'], '猴子')

    def test_female_does_not_link_to_boat(self):
        text = '女郎站在竹筏上，她表演特技。'
        ant, _, _ = choose(detect_record(record(text))[0], text, nominal_candidates(record(text), []), 'v2')
        self.assertEqual(ant['text'], '女郎')

    def test_no_candidate_means_abstention(self):
        text = '这里很好。'
        ant, _, _ = choose(detect_record(record(text))[0], text, [], 'v2')
        self.assertIsNone(ant)

    def test_forward_and_out_of_window_candidates_are_not_used(self):
        text = '这里有公园。'
        candidate = span(text, 3, 5, entity_type='place', source='test')
        ant, _, _ = choose(detect_record(record(text))[0], text, [candidate], 'v2')
        self.assertIsNone(ant)
        text = '公园。' + '风景很好。' * 100 + '这里很安静。'
        candidate = span(text, 0, 2, entity_type='place', source='test')
        ant, _, _ = choose(detect_record(record(text))[0], text, [candidate], 'v2', 50)
        self.assertIsNone(ant)

    def test_named_place_wins_over_embedded_city(self):
        text = '清风寺位于青城。这里很安静。'
        entities = [span(text, 0, 3, entity_type='POI')]
        ant, _, _ = choose(detect_record(record(text))[0], text, nominal_candidates(record(text), entities), 'v2')
        self.assertEqual(ant['text'], '清风寺')

    def test_missing_prediction_is_an_error_even_for_abstention(self):
        item = {'sample_id': 'x', 'doc_id': 'demo', 'pronoun': {'start': 0, 'end': 2, 'text': '这里'},
                'acceptable_antecedents': [], 'resolution_status': 'unresolved', 'reason': '无先行词', 'review_status': 'pending'}
        metrics, _ = compare([item], {})
        self.assertEqual(metrics['missing_predictions'], 1)
        self.assertEqual(metrics['end_to_end_accuracy'], 0)
        empty, _ = compare([], {})
        self.assertIsNone(empty['end_to_end_accuracy'])

    def test_same_text_different_positions_is_not_strict_match(self):
        p = {'start': 6, 'end': 8, 'text': '这里'}
        item = {'sample_id': 'x', 'doc_id': 'demo', 'pronoun': p, 'acceptable_antecedents':
                [{'start': 3, 'end': 5, 'text': '公园'}], 'resolution_status': 'resolved',
                'reason': '最近提及', 'review_status': 'pending'}
        pred = {'sample_id': 'x', 'doc_id': 'demo', 'pronoun': p,
                'antecedent': {'start': 0, 'end': 2, 'text': '公园'}, 'reason': '较早提及'}
        metrics, _ = compare([item], {'x': pred})
        self.assertEqual(metrics['end_to_end_accuracy'], 0)
        self.assertEqual(metrics['antecedent_text_accuracy_on_resolvable'], 1)

    def test_review_requires_reviewer_and_hash_rejects_stale_text(self):
        text = '这里很好。'
        gold = {'doc_scope': ['demo'], 'source_text_sha256': {'demo': text_hash(text)}, 'items': [{
            'sample_id': 'x', 'doc_id': 'demo', 'pronoun': span(text, 0, 2),
            'resolution_status': 'unresolved', 'acceptable_antecedents': [],
            'review_status': 'confirmed', 'reviewer': None}]}
        with self.assertRaises(ValueError):
            validate_gold(gold, {'demo': record(text)})
        gold['items'][0]['review_status'] = 'pending'
        with self.assertRaises(ValueError):
            validate_gold(gold, {'demo': record('改过的文本')})

    def test_annotated_view_does_not_change_original_spans(self):
        text = '公园很美，这里安静。'
        pronoun = span(text, 5, 7)
        prediction = {'pronoun': pronoun, 'antecedent': span(text, 0, 2)}
        annotated = render_annotations(text, [prediction])
        self.assertIn('这里〔指：公园〕', annotated)
        validate_span(text, pronoun)


if __name__ == '__main__':
    unittest.main()
