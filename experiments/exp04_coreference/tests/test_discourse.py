"""新名称、干扰信息及无文本先行词的篇章消解回归。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from common import span, validate_span
from context_rules import expand_candidates, choose_context
from detect import detect_record
from discourse import expand_discourse, infer
from resolve import nominal_candidates, choose


class DiscourseTests(unittest.TestCase):
    def resolve(self, text, names=(), title='青湖旅行记', text_type='tourist_note', index=-1):
        record = {'doc_id': 'novel', 'scenic_id': 'TEST', 'clean_text': text,
                  'title': title, 'text_type': text_type, 'source_url': ''}
        entities = []
        for name in names:
            start = 0
            while (start := text.find(name, start)) >= 0:
                entities.append(span(text, start, start + len(name), entity_type='POI'))
                start += len(name)
        original = expand_candidates(text, nominal_candidates(record, entities))
        expanded = expand_discourse(record, original)
        sample = detect_record(record)[index]
        def fallback():
            ant, reason, ranking = choose_context(sample, text, original, choose)
            return {'antecedent': ant, 'reason': reason, 'ranked_candidates': ranking}
        result = infer(record, sample, expanded, fallback)
        if result['antecedent']:
            validate_span(text, result['antecedent'])
            self.assertLessEqual(result['antecedent']['end'], sample['pronoun']['start'])
        return result

    def test_trip_is_not_station(self):
        result = self.resolve('从东站出发。这次旅行很开心。', ('东站',))
        self.assertIsNone(result['antecedent'])
        self.assertEqual(result['referent']['kind'], 'trip')

    def test_article_is_document(self):
        result = self.resolve('这一篇记录了徒步经验。')
        self.assertEqual(result['referent']['kind'], 'document')

    def test_named_route_beats_endpoint(self):
        result = self.resolve('青湖游览路，即东门—石桥—北亭，是最省力的登顶路线。可沿此路线上山。',
                              ('东门', '石桥', '北亭'))
        self.assertEqual(result['antecedent']['text'], '东门—石桥—北亭')

    def test_parentheses_route_is_complete(self):
        result = self.resolve('我选择的路线是东门（步行）-石桥-北亭（乘车）-西门，这条路线很轻松。')
        self.assertEqual(result['antecedent']['text'], '东门（步行）-石桥-北亭（乘车）-西门')

    def test_title_route_has_no_fabricated_body_span(self):
        result = self.resolve('这条路线适合亲子家庭。', title='青湖—石桥环线', text_type='official_route')
        self.assertIsNone(result['antecedent'])
        self.assertEqual(result['referent']['description'], '青湖—石桥环线')
        self.assertEqual(result['referent']['evidence_source'], 'title')

    def test_current_sentence_beats_old_heading(self):
        result = self.resolve('青云寺\n\n离开寺庙。到达北亭，这里可以休息。', ('青云寺', '北亭'))
        self.assertEqual(result['antecedent']['text'], '北亭')

    def test_historical_city_does_not_change_official_topic(self):
        result = self.resolve('清泉寺\n\n此寺旧时曾请杭州工匠建造。这里有古树。',
                              ('清泉寺', '杭州'), text_type='official_route')
        self.assertEqual(result['antecedent']['text'], '清泉寺')

    def test_animals_are_not_scenic_area(self):
        result = self.resolve('在青湖见到了猕猴，它们在吃果子。', ('青湖',))
        self.assertEqual(result['antecedent']['text'], '猕猴')

    def test_plant_personification(self):
        result = self.resolve('姊妹松\n\n古树已有六百年历史。她依旧挺立。')
        self.assertEqual(result['antecedent']['text'], '姊妹松')

    def test_female_human_beats_plant(self):
        result = self.resolve('姊妹松\n\n小女孩站在旁边，她在微笑。')
        self.assertEqual(result['antecedent']['text'], '小女孩')

    def test_hotel_is_not_park(self):
        result = self.resolve('预定的清风酒店位置很好。从青湖公园回来还是住这个酒店。', ('青湖公园',))
        self.assertEqual(result['antecedent']['text'], '清风酒店')

    def test_full_place_suffix(self):
        result = self.resolve('到了北门小广场，这里有游客中心。', ('北门',))
        self.assertEqual(result['antecedent']['text'], '北门小广场')

    def test_event_instead_of_nearby_noun(self):
        result = self.resolve('全程徒步需要耐力，对此应做好准备。')
        self.assertEqual(result['antecedent']['text'], '全程徒步需要耐力')

    def test_filler_does_not_replace_previous_event(self):
        result = self.resolve('我没有带雨具。事实证明，这不一定是好习惯。')
        self.assertEqual(result['antecedent']['text'], '我没有带雨具')

    def test_function_instead_of_building(self):
        result = self.resolve('高台原本应该是拍摄全景的地点，却因浓雾失去该作用。')
        self.assertEqual(result['antecedent']['text'], '拍摄全景的地点')

    def test_scene_needs_no_invented_textual_antecedent(self):
        result = self.resolve('这两棵树长得很好。')
        self.assertIsNone(result['antecedent'])
        self.assertEqual(result['referent']['kind'], 'situational_deixis')

    def test_season_does_not_become_park(self):
        result = self.resolve('游览了青湖公园，尽赏这个季节的风光。', ('青湖公园',))
        self.assertEqual(result['referent']['kind'], 'time')

    def test_fixed_expression_is_not_human(self):
        result = self.resolve('走这条路，无他，只因清静。')
        self.assertEqual(result['referent']['kind'], 'non_pronoun')

    def test_prefixed_subject_opens_new_official_section(self):
        result = self.resolve('黄石洞\n\n寺院北面的白云洞，里面有泉水。洞旁题刻说松到此始鸣。',
                              ('黄石洞', '白云洞'), text_type='official_route')
        self.assertEqual(result['antecedent']['text'], '白云洞')

    def test_subordinate_trip_preserves_description(self):
        result = self.resolve('这是全程最后一篇，也是整个假期最精彩的一段旅程，其他安排都是这个的附属品。')
        self.assertEqual(result['antecedent']['text'], '整个假期最精彩的一段旅程')

    def test_day_heading_survives_metadiscourse(self):
        result = self.resolve('Day3青湖徒步\n\n从东门走到西亭。虽然写下来很快，但现实是，走这一天很累。')
        self.assertEqual(result['antecedent']['text'], 'Day3青湖徒步')
        self.assertEqual(result['referent']['kind'], 'time')


if __name__ == '__main__':
    unittest.main()
