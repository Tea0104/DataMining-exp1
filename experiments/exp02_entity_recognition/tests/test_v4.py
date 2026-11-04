"""用虚构景区和空景点词表检查目的地、地点介绍和名称边界。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import recognize_entities as base
import recognize_v3 as v3
import recognize_v4 as v4


CASES = {
    'movement': ('从墨汀驿站出发，途经鸢羽石窟，抵达云砚书院。', {'墨汀驿站', '鸢羽石窟', '云砚书院'}),
    'visit': ('上午参观瑶灯故居，下午造访溯雨古村。', {'瑶灯故居', '溯雨古村'}),
    'description': ('苔笺书院坐落于山间。纸鸢遗址始建于明代。', {'苔笺书院', '纸鸢遗址'}),
    'quoted': ('前往「归篷」打卡。这处遗址名为“苔痕”。', {'归篷', '苔痕'}),
    'fields': ('目的地：流霞、折汀\n景点名称：静砂', {'流霞', '折汀', '静砂'}),
    'boundary': ('到了墨篱古镇附近，走到雾栖观景平台拍照。', {'墨篱古镇', '雾栖观景平台'}),
    'generic': ('去了一个古镇，又到了游客中心。前往博物馆，抵达观景台。', set()),
    'verbs': ('前往可以休息的地方。想参观一座书院，到了山顶再找入口。', set()),
    'types': ('乘轻轨7号线，四十多分钟后抵达雨纹石窟。', {'雨纹石窟'}),
    'prose_list': ('我们参观了苔漪书院、鸣帆石窟和云旌故居。', {'苔漪书院', '鸣帆石窟', '云旌故居'}),
    'activity': ('我们在青鸾坞附近看日落。穿过萤湾步道，最后在折苇坪合影。', {'青鸾坞', '萤湾步道', '折苇坪'}),
    'modifiers': ('前往当地博物馆、著名古镇。目的地：休息\n到附近的新建展馆。', set()),
}


class ContextualPoiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scenic = 'UNSEEN'
        groups = base.build_lexicon({'scenics': {}}, scenic)
        stop = base.build_stopwords({}, scenic)
        records = [{'doc_id': doc, 'clean_text': text} for doc, (text, _) in CASES.items()]
        cls.before, _ = v3.extract(records, groups, stop, scenic)
        cls.after, _ = v4.extract(records, groups, stop, scenic)

    def test_novel_places_and_generic_negatives(self):
        for doc, (_, expected) in CASES.items():
            with self.subTest(doc=doc):
                actual = {e['text'] for e in self.after if e['doc_id'] == doc and e['entity_type'] == 'POI'}
                self.assertEqual(actual, expected)

    def test_traffic_and_time_remain_unchanged(self):
        self.assertEqual([e for e in self.after if e['entity_type'] != 'POI'],
                         [e for e in self.before if e['entity_type'] != 'POI'])
        self.assertTrue(all(entity in self.after for entity in self.before))

    def test_spans_and_non_overlap(self):
        ends = {}
        for entity in self.after:
            doc, start, end = entity['doc_id'], entity['start'], entity['end']
            self.assertEqual(CASES[doc][0][start:end], entity['text'])
            self.assertLessEqual(ends.get(doc, 0), start)
            ends[doc] = end


if __name__ == '__main__':
    unittest.main()
