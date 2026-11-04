"""用不同名称和句式测试v3规则，不读取开发集标注。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from common import span
from context_rules import expand_candidates, choose_context
from detect import detect_record
from resolve import nominal_candidates, choose


class ContextRulesTests(unittest.TestCase):
    def resolve(self, text, names=(), index=-1):
        record = {'doc_id': 'unseen', 'scenic_id': 'TEST', 'clean_text': text, 'source_url': ''}
        entities = []
        for name in names:
            start = 0
            while (start := text.find(name, start)) >= 0:
                entities.append(span(text, start, start + len(name), entity_type='POI'))
                start += len(name)
        pool = expand_candidates(text, nominal_candidates(record, entities))
        sample = detect_record(record)[index]
        ant, _, _ = choose_context(sample, text, pool, choose)
        if ant:
            self.assertEqual(text[ant['start']:ant['end']], ant['text'])
            self.assertLessEqual(ant['end'], sample['pronoun']['start'])
        return ant

    def test_route_in_current_clause(self):
        ant = self.resolve('从东门到西门这段路比较平坦。', ('东门', '西门'))
        self.assertEqual(ant['text'], '从东门到西门')

    def test_route_keeps_continuing_movement(self):
        ant = self.resolve('从北门到游客站，再继续步行到湖边，这段路需要半小时。', ('北门', '游客站', '湖边'))
        self.assertEqual(ant['text'], '从北门到游客站，再继续步行到湖边')

    def test_timed_route_crosses_lines(self):
        ant = self.resolve('8点15分走到松亭\n\n9点半到达石桥\n\n这段路很费体力。', ('松亭', '石桥'))
        self.assertEqual(ant['text'], '8点15分走到松亭\n\n9点半到达石桥')

    def test_route_stops_before_description(self):
        ant = self.resolve('从西门往水榭方向走，一路都是树林，走这条路线的人很少。', ('西门', '水榭'))
        self.assertEqual(ant['text'], '从西门往水榭方向走')

    def test_plural_places_are_not_last_place_only(self):
        ant = self.resolve('路线：乘车上山→松亭→石桥→湖岸。我们游览了这几个地方。', ('松亭', '石桥', '湖岸'))
        self.assertEqual(ant['text'], '松亭→石桥→湖岸')

    def test_time_demonstrative_targets_transition_event(self):
        ant = self.resolve('列车驶入站台。那一瞬间，大家欢呼起来。')
        self.assertEqual(ant['text'], '列车驶入站台')

    def test_conditional_scenario_preserves_whole_event(self):
        ant = self.resolve('如果是下雪的时候步行游览山谷，那是另一番景象。')
        self.assertEqual(ant['text'], '下雪的时候步行游览山谷')

    def test_latest_same_name_retains_mention_position(self):
        text = '第一站：松亭\n松亭是休息点。经过石桥后回到松亭。这里有座椅。'
        ant = self.resolve(text, ('松亭', '石桥'))
        self.assertEqual(ant['text'], '松亭')
        self.assertEqual(ant['start'], text.rfind('松亭'))

    def test_place_compound_does_not_drop_suffix(self):
        ant = self.resolve('清泉峪坊，题字很清晰。到这里已经是中午。', ('清泉峪',))
        self.assertEqual(ant['text'], '清泉峪坊')

    def test_unknown_picture_path_is_not_destination(self):
        self.assertIsNone(self.resolve('远处是青云寺。\n走这里去青云寺\n', ('青云寺',)))

    def test_path_with_textual_antecedent_is_resolvable(self):
        ant = self.resolve('前面是林间步道。\n走这里去青云寺\n', ('林间步道', '青云寺'))
        self.assertEqual(ant['text'], '林间步道')

    def test_new_picture_inscription_is_not_previous_person(self):
        self.assertIsNone(self.resolve('诗人曾在此游览。此题刻在石壁上。', ('石壁',)))

    def test_summary_refers_to_subject_not_last_list_item(self):
        ant = self.resolve('青湖有树林、竹筏码头，还有小滑雪场；这是北方的城市公园。', ('青湖', '竹筏码头', '小滑雪场'))
        self.assertEqual(ant['text'], '青湖')

    def test_site_subject_is_not_containing_city_or_park(self):
        ant = self.resolve('青云园暨植物保护中心，坐落在春江市的白鹭公园内。林木繁茂，该园开放参观。', ('青云园', '春江市', '白鹭公园'))
        self.assertEqual(ant['text'], '青云园')

    def test_short_place_caption_updates_current_location(self):
        ant = self.resolve('9点到达青石坊。\n\n白鹭桥\n\n走到这里就能看见湖面。', ('青石坊',))
        self.assertEqual(ant['text'], '白鹭桥')


if __name__ == '__main__':
    unittest.main()
