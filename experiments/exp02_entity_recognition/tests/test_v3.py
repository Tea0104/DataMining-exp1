"""v3的可复用规则回归；使用未列入景区词典的示例，不以金标充当词典。"""
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
import recognize_entities as base
import recognize_v3 as v3


class V3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.groups = base.build_lexicon(base.load_json(base.CONFIG/'lexicon.json'), 'JINGYUETAN')
        cls.stop = base.build_stopwords(base.load_json(base.CONFIG/'stopwords.json'), 'JINGYUETAN')

    def extract(self, text):
        entities, _ = v3.extract([{'doc_id':'synthetic', 'clean_text':text}], self.groups, self.stop, 'JINGYUETAN')
        for e in entities:
            self.assertEqual(text[e['start']:e['end']], e['text'])
        for a,b in zip(entities, entities[1:]):
            self.assertLessEqual(a['end'], b['start'])
        return entities

    def names(self, text, kind):
        return [e['text'] for e in self.extract(text) if e['entity_type']==kind]

    def test_fuzzy_durations(self):
        self.assertEqual(self.names('等四十多分钟，步行一个半小时多，休息十几分钟，搭电梯88秒。', 'TIME'),
                         ['四十多分钟','一个半小时多','十几分钟','88秒'])

    def test_clock_after_label_colon(self):
        self.assertEqual(self.names('开放时间：20:00-21:20；游玩时间：1-2小时。', 'TIME'),
                         ['20:00-21:20','1-2小时'])

    def test_dates_and_weekdays(self):
        self.assertEqual(self.names('2025.7.22出发，9月15日返回，周五晚上休息。', 'TIME'),
                         ['2025.7.22','9月15日','周五晚上'])

    def test_seasons_and_relative_days(self):
        self.assertEqual(self.names('今天看日出，冬季开放，次日早返回，每逢整点发车。', 'TIME'),
                         ['今天','日出','冬季','次日早','整点'])

    def test_poetry_and_non_time_numbers(self):
        result=self.names('九天云气映斯亭；一天下雨，一天然石穴。2023年，115元，99:99，一点都不累。', 'TIME')
        self.assertEqual(result, [])

    def test_unseen_route_nodes(self):
        for name in ('青岚谷','松风亭','云溪站'):
            self.assertNotIn(name,self.groups['poi'])
        self.assertEqual(self.names('路线：青岚谷→松风亭→云溪站。', 'POI'),['青岚谷','松风亭','云溪站'])

    def test_name_extension(self):
        self.assertEqual(self.names('到观潭山站，再到朝夕水岸码头。', 'POI'),['观潭山站','朝夕水岸码头'])

    def test_transport_and_named_lines(self):
        self.assertEqual(self.names('打车到站，乘轻轨7号线，再坐游览车。', 'TRANSPORT'),
                         ['打车','轻轨7号线','游览车'])

    def test_named_transport_subtype(self):
        groups=base.build_lexicon(base.load_json(base.CONFIG/'lexicon.json'),'WULINGYUAN')
        stop=base.build_stopwords(base.load_json(base.CONFIG/'stopwords.json'),'WULINGYUAN')
        entities,_=v3.extract([{'doc_id':'synthetic','clean_text':'乘坐十里画廊观光小火车。'}],groups,stop,'WULINGYUAN')
        self.assertEqual([(e['text'],e['entity_type'],e['subtype']) for e in entities],
                         [('十里画廊观光小火车','TRANSPORT','train')])

    def test_transport_action_is_not_a_line_name(self):
        self.assertEqual(self.names('乘坐索道，换乘索道，搭乘索道。','TRANSPORT'),['索道','索道','索道'])

    def test_alias_candidate(self):
        self.assertIn('听涛峰',self.names('该山峰又称“听涛峰”，景色优美。','POI'))

    def test_prose_dashes_and_generic_facilities(self):
        self.assertEqual(self.names('我们决定休息——点外卖。地貌为“平台—峰墙—峰林”。到火车站和索道站。','POI'),[])

    def test_historical_and_figurative_time(self):
        self.assertEqual(self.names('1948年10月19日，长春解放。明天启六年重建。一时爽，一秒变身。','TIME'),[])


if __name__ == '__main__':
    unittest.main()
