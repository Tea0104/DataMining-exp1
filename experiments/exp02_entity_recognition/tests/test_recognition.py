"""识别语义和评估入口回归：python -m unittest discover -s 本目录 -v。"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, BASE / 'src' / f'{name}.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


recognizer = module('recognize_entities')
evaluation = module('evaluate')


class RecognitionTests(unittest.TestCase):
    def extract(self, text, scenic='JINGYUETAN', version='v2'):
        groups = recognizer.build_lexicon(
            recognizer.load_json(recognizer.CONFIG / 'lexicon.json'), scenic)
        stop = recognizer.build_stopwords(
            recognizer.load_json(recognizer.CONFIG / 'stopwords.json'), scenic)
        entities, _ = recognizer.extract(
            [{'doc_id': 'sample', 'clean_text': text}], version, groups, stop, scenic)
        for entity in entities:
            self.assertEqual(text[entity['start']:entity['end']], entity['text'])
        return entities

    def test_complete_clocks_and_ranges(self):
        entities = self.extract('十一点半出发，9—10点入园，12点半离开，23:00-01:40登山。')
        self.assertEqual([(e['text'], e['subtype']) for e in entities],
                         [(t, 'clock') for t in ['十一点半', '9—10点', '12点半', '23:00-01:40']])

    def test_compound_and_chinese_durations(self):
        entities = self.extract('步行4小时30分钟，休息十分钟，再走半小时，等一刻钟，耗时1.5-2小时。')
        self.assertEqual([e['text'] for e in entities if e['entity_type'] == 'TIME'],
                         ['4小时30分钟', '十分钟', '半小时', '一刻钟', '1.5-2小时'])

    def test_numbers_and_invalid_times_are_not_clocks(self):
        self.assertEqual(self.extract('2023年，115元，7000级，2078米，99:99，24:70，三十三点。'), [])

    def test_point_can_be_a_non_time_expression(self):
        self.assertEqual(self.extract('这样玩一点都不累，还有三点建议，这一点很好。'), [])
        self.assertEqual(self.extract('近一点，轻松一点吧，有一点遗憾。一日游路线，一天然石穴。'), [])

    def test_itinerary_days_and_full_day_duration(self):
        entities = self.extract('Day4出发，第四天游玩，第五天返回，前一天玩了一整天。')
        self.assertEqual([(e['text'], e['subtype']) for e in entities],
                         [('Day4', 'day'), ('第四天', 'day'), ('第五天', 'day'),
                          ('前一天', 'day'), ('一整天', 'duration')])

    def test_long_names_win_over_transport_words(self):
        self.assertEqual([(e['text'], e['entity_type']) for e in self.extract('途经徒步惊喜。')],
                         [('徒步惊喜', 'POI')])
        self.assertEqual([(e['text'], e['entity_type']) for e in
                          self.extract('乘天子山索道。', scenic='WULINGYUAN')],
                         [('天子山索道', 'TRANSPORT')])

    def test_generic_alias_requires_visit_context(self):
        self.assertEqual(self.extract('生态类型包括湿地，附近有滑雪场。'), [])
        entities = self.extract('依次游玩了月塔楼 湿地 瓦萨滑雪博物馆 滑雪场。')
        self.assertEqual([e['text'] for e in entities],
                         ['月塔楼', '湿地', '瓦萨滑雪博物馆', '滑雪场'])

    def test_new_poi_and_transport(self):
        entities = self.extract('到凌空观景台，再到地质博物馆、吴家峪，坐景区车。', 'WULINGYUAN')
        self.assertEqual([e['text'] for e in entities],
                         ['凌空观景台', '地质博物馆', '吴家峪', '景区车'])

    def test_versions_and_scenics_do_not_pollute_tokenization(self):
        text = '徒步惊喜，天子山索道，月塔楼。'
        baseline = self.extract(text, version='v1')
        before = self.extract(text)
        self.extract(text, scenic='WULINGYUAN')
        self.assertEqual(baseline, self.extract(text, version='v1'))
        self.assertEqual(before, self.extract(text))


class EvaluationTests(unittest.TestCase):
    def test_explicit_scope_keeps_documents_without_gold_entities(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'entities_TEST_v2.json').write_text(json.dumps([
                {'doc_id': 'empty', 'entity_type': 'POI', 'text': 'wrong'}]), encoding='utf-8')
            gold_path = root / 'gold_TEST.json'
            gold_path.write_text(json.dumps({'doc_scope': ['empty'], 'items': []}), encoding='utf-8')
            self.assertEqual(evaluation.evaluate('v2', 'TEST', gold_path, root)['overall']['fp'], 1)

    def test_cli_preserves_both_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'gold_TEST.json').write_text(json.dumps({
                'doc_scope': ['doc'], 'items': [
                    {'doc_id': 'doc', 'entity_type': 'POI', 'text': 'node'}]}), encoding='utf-8')
            (root / 'dataset.json').write_text(json.dumps([
                {'doc_id': 'doc', 'clean_text': 'node'}]), encoding='utf-8')
            for version in ('v2', 'v1'):
                (root / f'entities_TEST_{version}.json').write_text(json.dumps([
                    {'doc_id': 'doc', 'entity_type': 'POI', 'text': 'node'}]), encoding='utf-8')
                completed = subprocess.run([
                    sys.executable, '-B', str(BASE / 'src/evaluate.py'), '--version', version,
                    '--scenic', 'TEST', '--outputs', str(root), '--dataset', str(root / 'dataset.json')],
                    capture_output=True)
                self.assertEqual(completed.returncode, 0, completed.stderr)
            index = json.loads((root / 'evaluation.json').read_text(encoding='utf-8'))
            self.assertEqual(set(index['versions']), {'v1', 'v2'})
            self.assertEqual(json.loads((root / 'evaluation_v2.json').read_text(encoding='utf-8'))
                             ['overall']['tp'], 1)


if __name__ == '__main__':
    unittest.main()
