"""核验 v6 的新语境规则和原文跨度。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import recognize_entities as base
import recognize_v5 as v5
import recognize_v6 as v6


class ContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texts = {
            'inscription': '岩壁一侧的石碑上面写着“潮声入梦”。旁边是著名的“云霞留痕”碑刻。随后读了《山居杂记》。',
            'location': '鹭羽驿站坐落在栖云岩和北鸣岭之间。沿路临近凝露瀑。小溪位于岚山东麓芦汀村。以后可以去一次苍月峰。',
            'alias': '第三站：鹭汀广场（溪声旧渡）\n下车后步行两小时。',
            'calendar': '大年初一出发，计划在九月底再来。初秋是旅游旺季。',
        }
        records = [{'doc_id': doc_id, 'clean_text': text} for doc_id, text in cls.texts.items()]
        groups = base.build_lexicon({'scenics': {}}, 'NEW')
        stop = base.build_stopwords({}, 'NEW')
        cls.previous, _ = v5.extract(records, groups, stop, 'NEW')
        cls.entities, _ = v6.extract(records, groups, stop, 'NEW')

    def names(self, doc_id, kind):
        return {e['text'] for e in self.entities if e['doc_id'] == doc_id and e['entity_type'] == kind}

    def test_inscriptions_and_ordinary_quote(self):
        names = self.names('inscription', 'POI')
        self.assertTrue({'潮声入梦', '云霞留痕'} <= names)
        self.assertNotIn('山居杂记', names)

    def test_positions_and_station_alias(self):
        names = self.names('location', 'POI')
        self.assertTrue({'栖云岩', '北鸣岭', '凝露瀑', '芦汀村'} <= names)
        self.assertNotIn('栖云岩和北鸣岭', names)
        self.assertNotIn('岚山东麓芦汀村', names)
        self.assertNotIn('一次苍月峰', names)
        self.assertIn('溪声旧渡', self.names('alias', 'POI'))

    def test_calendar_and_entity_spans(self):
        self.assertTrue({'大年初一', '九月底', '初秋', '旺季'} <= self.names('calendar', 'TIME'))
        self.assertTrue(all(entity in self.entities for entity in self.previous))
        ends = {}
        for entity in self.entities:
            doc_id, start, end = (entity[key] for key in ('doc_id', 'start', 'end'))
            self.assertEqual(self.texts[doc_id][start:end], entity['text'])
            self.assertLessEqual(ends.get(doc_id, 0), start)
            ends[doc_id] = end
