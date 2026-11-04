"""用未注册的地名检验 v7 的路线和命名规则。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import recognize_entities as base
import recognize_v7 as v7


class NamingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texts = {
            'titles': '赵师傅题的“溪映晨霞”，许先生题的听松问月等石刻。另有”渔火满湾“匾额。读了《山居杂记》。',
            'route': '自迎潮坡至白雁岭为“慢九弯”，再至飞虹桥为“不紧不慢又九弯”。观光车终点站雾川小集。等车后乘观光车，坐二十分钟。',
            'list': '景点的名字，如“白鹿听泉、双雁照水、孤帆峰”等，很有意思。南门和东门的车分别进站。',
            'boundary': '云岭鹭台书院，始建于明代。该书院，位于南峰极顶，始建年代无考。',
        }
        records = [{'doc_id': doc, 'clean_text': text} for doc, text in cls.texts.items()]
        groups = base.build_lexicon({'scenics': {'NEW': {'poi': {'鹭台书院': 'facility'}}}}, 'NEW')
        stop = base.build_stopwords({}, 'NEW')
        cls.entities, _ = v7.extract(records, groups, stop, 'NEW')

    def names(self, doc, kind='POI'):
        return {e['text'] for e in self.entities if e['doc_id'] == doc and e['entity_type'] == kind}

    def test_inscriptions_and_poi_lists(self):
        self.assertTrue({'溪映晨霞', '听松问月', '渔火满湾'} <= self.names('titles'))
        self.assertNotIn('山居杂记', self.names('titles'))
        self.assertTrue({'白鹿听泉', '双雁照水', '孤帆峰', '南门', '东门'} <= self.names('list'))

    def test_route_labels_and_roles(self):
        self.assertTrue({'迎潮坡', '白雁岭', '飞虹桥', '慢九弯', '不紧不慢又九弯', '雾川小集'} <= self.names('route'))
        self.assertIn('二十分钟', self.names('route', 'TIME'))

    def test_full_name_and_offsets(self):
        self.assertIn('云岭鹭台书院', self.names('boundary'))
        self.assertNotIn('位于南峰极顶', self.names('boundary'))
        ends = {}
        for entity in self.entities:
            doc, start, end = (entity[key] for key in ('doc_id', 'start', 'end'))
            self.assertEqual(self.texts[doc][start:end], entity['text'])
            self.assertLessEqual(ends.get(doc, 0), start)
            ends[doc] = end
