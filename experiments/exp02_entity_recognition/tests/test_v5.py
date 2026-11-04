"""以陌生名称核验 v5 的新增句式和边界。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import recognize_entities as base
import recognize_v3 as v3
import recognize_v5 as v5


class PoiRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.examples = {
            'alias': '鹭湾书院，旧称砚山馆、春汀阁。',
            'heading': '云笺书院（苔痕）\n银鹭石坊\n今天继续前往观景台。',
            'route': '住宿建议：北门\n08:40 栖潮阁 / 回风亭\n随后从北门入园。',
            'boundary': '参观流云石刻，之后乘轻轨7号线，休息四十多分钟。',
            'inscription': '石碑“潮回十里”。',
            'negative': '到达酒店后休整；游览方式：公路乘车上山。景色就像一幅画。',
            'station': '从市中心汽车站乘17路车到云溪竹馆站下车。之后走了四个多小时。',
            'scenery': '附近山谷以“林海、雪山、碧水”闻名，山坡上覆盖着苍柏。接着到达云岫气象站。',
        }
        groups = base.build_lexicon({'scenics': {'NEW': {'poi': {
            '流云石': 'landmark', '苍柏': 'landmark', '云岫气象站': 'facility',
        }}}}, 'NEW')
        stop = base.build_stopwords({}, 'NEW')
        records = [{'doc_id': doc, 'clean_text': text} for doc, text in cls.examples.items()]
        cls.before, _ = v3.extract(records, groups, stop, 'NEW')
        cls.after, _ = v5.extract(records, groups, stop, 'NEW')

    def names(self, doc):
        return {e['text'] for e in self.after if e['doc_id'] == doc and e['entity_type'] == 'POI'}

    def test_aliases_and_headings(self):
        self.assertTrue({'砚山馆', '春汀阁'} <= self.names('alias'))
        self.assertTrue({'苔痕', '银鹭石坊'} <= self.names('heading'))
        self.assertNotIn('观景台', self.names('heading'))

    def test_route_and_inscription(self):
        self.assertTrue({'北门', '栖潮阁', '回风亭'} <= self.names('route'))
        self.assertIn('潮回十里', self.names('inscription'))

    def test_boundary_and_other_types(self):
        self.assertIn('流云石刻', self.names('boundary'))
        self.assertNotIn('流云石', self.names('boundary'))
        self.assertEqual([e for e in self.before if e['doc_id'] == 'boundary' and e['entity_type'] != 'POI'],
                         [e for e in self.after if e['doc_id'] == 'boundary' and e['entity_type'] != 'POI'])
        self.assertFalse(any(e['doc_id'] == 'negative' and e['method'].startswith('v5_')
                             for e in self.after))
        ends = {}
        for entity in self.after:
            doc, start, end = entity['doc_id'], entity['start'], entity['end']
            self.assertEqual(self.examples[doc][start:end], entity['text'])
            self.assertLessEqual(ends.get(doc, 0), start)
            ends[doc] = end

    def test_station_names_and_transport_fragments(self):
        entities = {(e['entity_type'], e['text']): e['canonical']
                    for e in self.after if e['doc_id'] == 'station'}
        self.assertEqual(entities['POI', '云溪竹馆站'], '云溪竹馆')
        self.assertIn(('TRANSPORT', '17路车'), entities)
        self.assertNotIn(('TRANSPORT', '汽车'), entities)
        self.assertIn(('TIME', '四个多小时'), entities)

    def test_vegetation_and_non_transit_station(self):
        self.assertFalse({'雪山', '苍柏'} & self.names('scenery'))
        station = next(e for e in self.after if e['doc_id'] == 'scenery' and e['text'] == '云岫气象站')
        self.assertEqual(station['canonical'], '云岫气象站')
