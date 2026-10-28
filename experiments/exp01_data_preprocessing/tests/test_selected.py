"""Regression cases plus an independent check of the actual 30-document build.

Synthetic cases test rule boundaries; they are not evidence of corpus defects.
Full-corpus checks require the local snapshot/data package and otherwise skip.
"""
import copy
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import unittest

SRC = Path(__file__).resolve().parents[1] / 'src'
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SRC))
from text_blocks import extract_blocks, block_fingerprint
from preprocess_selected import (normalize_text, scope_blocks, validate_input,
                                 duplicate_groups, publication_metadata, PLAYER_RE)


class TextRules(unittest.TestCase):
    def test_preserves_route_semantics_and_emoji(self):
        source = '如体力不支，不去山顶→原路返回；☆☆☆；4--6小时；08:00/16:00；👩‍👩‍👧‍👦；e\u0301'
        result, _ = normalize_text(source)
        self.assertEqual(result, source.replace('e\u0301', 'é'))
        self.assertEqual(normalize_text(result)[0], result)

    def test_removes_technical_noise_without_gluing_words(self):
        actual, counts = normalize_text(' 甲\u00a0\u00a0乙\u200b\u200c\ufeff\x00\r\n\r\n丙\t丁，， ')
        self.assertEqual(actual, '甲 乙\n丙 丁，')
        self.assertEqual(counts['invisible_characters'], 3)
        self.assertEqual(counts['control_characters'], 1)

    def test_body_url_rule_keeps_chinese_punctuation(self):
        self.assertEqual(normalize_text('请看https://example.org/a?q=1，随后去东门。')[0], '请看，随后去东门。')

    def test_player_match_does_not_remove_real_hours(self):
        self.assertTrue(PLAYER_RE.fullmatch('00:00/00:00'))
        self.assertFalse(PLAYER_RE.fullmatch('08:00/16:00'))
        self.assertFalse(PLAYER_RE.fullmatch('当天00:00/00:00开始'))

    def test_html_blocks_keep_context_and_ignore_images(self):
        blocks = extract_blocks('<div><h3>第二天</h3><p>先去<b>东门</b>，<br>它没开。</p>'
                                '<img alt="不应补入的路线"><div class="graph_comment">山门图注</div>'
                                '<script>bad()</script><p>又返回东门。</p></div>')
        self.assertEqual([b.text for b in blocks], ['第二天','先去东门，\n它没开。','山门图注','又返回东门。'])
        self.assertEqual(blocks[2].role, 'caption')

    def test_scope_fingerprint_guards_body_change(self):
        blocks = extract_blocks('<div><p>先去东门。</p><p>又回东门。</p></div>')
        rule = {'expected_block_count':2, 'expected_block_fingerprint':block_fingerprint(blocks),
                'keep_ranges':[['B0001','B0002']], 'exclude_blocks':{}, 'clip_rules':[], 'notes':'测试'}
        self.assertEqual(len(scope_blocks(blocks, rule)[0]), 2)
        changed = extract_blocks('<div><p>先去西门。</p><p>又回东门。</p></div>')
        with self.assertRaisesRegex(ValueError, 'snapshot changed'):
            scope_blocks(changed, rule)

    def test_scope_invalid_ranges_fail(self):
        blocks = extract_blocks('<div><p>东门</p><p>西门</p></div>')
        rule = {'expected_block_count':2, 'expected_block_fingerprint':block_fingerprint(blocks),
                'keep_ranges':[['B0002','B0001']], 'notes':'测试'}
        with self.assertRaisesRegex(ValueError, 'range'):
            scope_blocks(blocks, rule)

    def test_ambiguous_clip_anchor_fails(self):
        blocks = extract_blocks('<div><p>山门STOP其它STOP</p></div>')
        rule = {'expected_block_count':1, 'expected_block_fingerprint':block_fingerprint(blocks),
                'keep_ranges':[['B0001','B0001']], 'notes':'测试',
                'clip_rules':[{'block_id':'B0001','end_before':'STOP','reason':'测试'}]}
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            scope_blocks(blocks, rule)

    def test_whitespace_variants_detect_document_duplicates(self):
        self.assertEqual(duplicate_groups([{'doc_id':'A','clean_text':'东门→西门'},
                                          {'doc_id':'B','clean_text':' 东门 → 西门\n'}]), [['A','B']])


@unittest.skipUnless((REPO/'data/raw/full/selected_v2/TS_OFF_001.json').exists(), 'Local snapshots required')
class RealInputChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = json.loads((REPO/'data/raw/full/selected_v2/TS_OFF_001.json').read_text(encoding='utf-8'))

    def test_null_optional_author_accepted(self):
        record = copy.deepcopy(self.raw)
        record['author'] = None
        validate_input(record)

    def test_missing_required_field_rejected(self):
        record = copy.deepcopy(self.raw)
        record['source_url'] = ''
        with self.assertRaisesRegex(ValueError, 'source_url'):
            validate_input(record)

    def test_invalid_date_and_abnormal_author_rejected(self):
        record = copy.deepcopy(self.raw)
        record['published_at'] = '2025-02-30'
        with self.assertRaisesRegex(ValueError, 'date'):
            validate_input(record)
        record['published_at'] = None; record['author'] = 42
        with self.assertRaisesRegex(ValueError, 'author'):
            validate_input(record)

    def test_corrupted_raw_body_rejected(self):
        record = copy.deepcopy(self.raw)
        record['raw_text'] += '新增文字'
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            validate_input(record)

    def test_explicit_publication_label_precedes_listing(self):
        raw = json.loads((REPO/'data/raw/full/selected_v2/TS_NOTE_004.json').read_text(encoding='utf-8'))
        value = publication_metadata(raw, REPO/'data/downloads/selected_v2/TS_NOTE_004.html')
        self.assertEqual(value['published_at'], '2025-01-04')
        self.assertTrue(value['date_conflict'])


@unittest.skipUnless((REPO/'data/processed/full/selected_v2/dataset.json').exists(), 'Build selected_v2 first')
class CorpusChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = REPO/'data/processed/full/selected_v2'
        cls.records = json.loads((cls.directory/'dataset.json').read_text(encoding='utf-8'))
        cls.by_id = {r['doc_id']:r for r in cls.records}

    def test_exact_three_by_five_plus_five(self):
        counts = Counter((r['scenic_id'],r['text_type']) for r in self.records)
        self.assertEqual(len(self.records), 30)
        self.assertEqual(len(self.by_id), 30)
        self.assertEqual(set(s for s,_ in counts), {'TAISHAN','WULINGYUAN','JINGYUETAN'})
        self.assertEqual(len(counts), 6)
        self.assertEqual(set(counts.values()), {5})

    def test_all_formats_hashes_offsets_and_audit(self):
        jsonl = [json.loads(line) for line in (self.directory/'dataset.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual(jsonl, self.records)
        for record in self.records:
            text = record['clean_text']
            self.assertEqual((self.directory/'texts'/(record['doc_id']+'.txt')).read_text(encoding='utf-8'), text)
            self.assertEqual(hashlib.sha256(text.encode('utf-8')).hexdigest(), record['clean_text_sha256'])
            self.assertEqual('\n\n'.join(b['text'] for b in record['blocks']), text)
            for block in record['blocks']:
                self.assertEqual(text[block['start']:block['end']], block['text'])
            audit = json.loads((self.directory/'audit'/(record['doc_id']+'.json')).read_text(encoding='utf-8'))
            self.assertEqual(len(audit['blocks']), record['metrics']['source_blocks'])

    def test_repeated_visits_preserved_caption_redundancy_removed(self):
        text = self.by_id['ZJJ_NOTE_001']['clean_text']
        self.assertIn('又折返', text)
        self.assertIn('只走到', text)
        self.assertEqual(text.count('杨家界的天然长城'), 1)

    def test_short_official_routes_not_discarded(self):
        self.assertIn('35分钟', self.by_id['JYT_OFF_005']['clean_text'])
        self.assertGreater(len(self.by_id['JYT_OFF_001']['clean_text']), 20)

    def test_original_contradiction_and_negation_not_rewritten(self):
        text = self.by_id['TS_NOTE_004']['clean_text']
        for evidence in ['23:00','01:40','03小时40分钟']:
            self.assertIn(evidence, text)
        self.assertTrue(self.by_id['TS_NOTE_004']['content_issues'])
        self.assertIn('不用担心它们不会抢背包和手机', self.by_id['ZJJ_NOTE_005']['clean_text'])

    def test_all_reviewed_scope_requirements(self):
        scope = json.loads((REPO/'data/metadata/selected_v2_scope_rules.json').read_text(encoding='utf-8'))
        for doc_id, rule in scope['rules'].items():
            text = self.by_id[doc_id]['clean_text']
            for evidence in rule['protected_evidence']:
                self.assertIn(evidence, text, doc_id)
            for evidence in rule['forbidden_independent_sections']:
                self.assertNotIn(evidence, text, doc_id)


if __name__ == '__main__':
    unittest.main(verbosity=2)
