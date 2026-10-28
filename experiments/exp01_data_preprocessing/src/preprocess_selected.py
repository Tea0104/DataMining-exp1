"""Build the 30-document, text-only dataset from verified local snapshots.

Run from the repository root. Scope review is a versioned input, not an
automatic claim of relevance. Every omitted block is accounted for in audit/.
"""

import argparse
from collections import Counter
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlparse

from lxml import html

from probe_sources import decode_body
from text_blocks import extract_blocks, block_fingerprint


URL_RE = re.compile(r'(?:https?://|www\.)[^\s<>「」『』【】（）()，。；！？、]+', re.I)
HTML_RE = re.compile(r'</?[A-Za-z][^>]*>')
PLAYER_RE = re.compile(r'^00:00\s*/\s*00:00$')
PLACEHOLDER_RE = re.compile(r'^(?:添加图片描(?:述)?|来自航拍视频|Image|图片加载中[.。…]*|点击查看大图)$', re.I)
INVISIBLE = {'\u200b', '\u200c', '\u2060', '\ufeff', '\u00ad'}
REQUIRED = ('doc_id', 'scenic_id', 'scenic_name', 'text_type', 'title',
            'source_url', 'publisher', 'collected_at', 'license')
OPTIONAL = ('author', 'published_at', 'license_url', 'list_publication_date')


def sha_text(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def nonspace_len(value):
    return len(re.sub(r'\s+', '', value))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def valid_date(value):
    if value is None:
        return True
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def validate_input(record):
    for field in REQUIRED:
        if not isinstance(record.get(field), str) or not record[field].strip():
            raise ValueError(f'{field}: missing or invalid required string')
    if not re.fullmatch(r'[A-Z0-9_]+', record['doc_id']):
        raise ValueError('Unsafe document ID')
    if record['text_type'] not in {'official_route', 'tourist_note'}:
        raise ValueError('Unknown text_type')
    parsed = urlparse(record['source_url'])
    if parsed.scheme not in {'https', 'http'} or not parsed.netloc:
        raise ValueError('Invalid source URL')
    if datetime.fromisoformat(record['collected_at']).utcoffset() is None:
        raise ValueError('Collection time requires timezone')
    for field in ('published_at', 'list_publication_date'):
        if not valid_date(record.get(field)):
            raise ValueError(f'{field}: invalid ISO date')
    for field in ('author', 'license_url'):
        if record.get(field) is not None and (not isinstance(record[field], str) or not record[field].strip()):
            raise ValueError(f'{field}: expected a nonempty string or null')
    if record.get('license_url'):
        parsed_license = urlparse(record['license_url'])
        if parsed_license.scheme not in {'http', 'https'} or not parsed_license.netloc:
            raise ValueError('Invalid license URL')
    if not isinstance(record.get('raw_html'), str) or not record.get('raw_text', '').strip():
        raise ValueError('Missing raw article content')
    if record.get('raw_text_sha256') != sha_text(record['raw_text']):
        raise ValueError('Raw body hash mismatch')
    if record.get('content_modality') != 'text_only':
        raise ValueError('Input must use the agreed text-only scope')


def normalize_text(text):
    """Conservative character cleanup. Keep arrows, emoji, negation and units."""
    stats = Counter()
    value = unicodedata.normalize('NFC', text)
    if value != text:
        stats['nfc_blocks'] += 1
    value, n = re.subn(r'\r\n?', '\n', value)
    stats['line_endings'] += n
    chars = []
    for char in value:
        if char in INVISIBLE:
            stats['invisible_characters'] += 1
        elif unicodedata.category(char) == 'Cc' and char not in '\n\t':
            stats['control_characters'] += 1
        elif char.isspace() and char != '\n':
            chars.append(' ')
            if char != ' ':
                stats['special_spaces'] += 1
        else:
            chars.append(char)
    value = ''.join(chars)
    value, n = URL_RE.subn('', value)
    stats['body_urls'] += n
    # Repeated commas are accidental punctuation; ellipses, dashes and route
    # connectors have meaning and must remain unchanged.
    value, n = re.subn(r'，{2,}', '，', value)
    stats['duplicate_comma_groups'] += n
    before = value
    lines = [re.sub(r' +', ' ', line).strip() for line in value.split('\n')]
    value = '\n'.join(line for line in lines if line).strip()
    if value != before:
        stats['whitespace_blocks'] += 1
    return value, {key: number for key, number in stats.items() if number}


def scope_blocks(blocks, rule):
    if len(blocks) != rule['expected_block_count'] or block_fingerprint(blocks) != rule['expected_block_fingerprint']:
        raise ValueError('Scope snapshot changed; review the article and update scope rules explicitly')
    indices = {block.block_id: i for i, block in enumerate(blocks)}
    keep = set()
    for first, last in rule['keep_ranges']:
        if first not in indices or last not in indices or indices[first] > indices[last]:
            raise ValueError('Invalid scope range')
        keep.update(block.block_id for block in blocks[indices[first]:indices[last]+1])
    if set(rule.get('exclude_blocks', {})) - set(indices):
        raise ValueError('Unknown excluded block')
    keep.difference_update(rule.get('exclude_blocks', {}))
    clips = {clip['block_id']: clip for clip in rule.get('clip_rules', [])}
    if len(clips) != len(rule.get('clip_rules', [])) or set(clips) - keep:
        raise ValueError('Invalid/duplicate clip rule')
    selected, audit = [], []
    for block in blocks:
        event = {'block_id': block.block_id, 'role': block.role, 'xpath': block.xpath,
                 'source_chars': nonspace_len(block.text), 'source_sha256': sha_text(block.text)}
        if block.block_id not in keep:
            event.update(scope_action='exclude', reason=rule.get('exclude_blocks', {}).get(block.block_id, rule['notes']))
        else:
            text = block.text
            if block.block_id in clips:
                clip = clips[block.block_id]
                anchor = clip['end_before']
                if text.count(anchor) != 1:
                    raise ValueError('Clip anchor missing or ambiguous: ' + block.block_id)
                text = text[:text.index(anchor)]
                event.update(scope_action='clip', reason=clip['reason'], clip_anchor=anchor)
            else:
                event.update(scope_action='keep', reason=rule['notes'])
            event['selected_chars'] = nonspace_len(text)
            selected.append((block, text))
        audit.append(event)
    return selected, audit


def publication_metadata(raw, cache_path):
    """Separate listing dates from explicit article dates; never infer from URL."""
    encoded = cache_path.read_bytes()
    if hashlib.sha256(encoded).hexdigest() != raw['response_sha256']:
        raise ValueError('HTML snapshot hash mismatch')
    decoded, _ = decode_body(encoded, raw.get('snapshot_encoding'))
    tree = html.fromstring(decoded, parser=html.HTMLParser(no_network=True))
    candidates = []
    if raw['publisher'] == '携程攻略':
        # Footer explicitly says 发布; the travel date in journal_detail is not
        # necessarily publication time. Keep both when they disagree.
        for node in tree.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," travels_end ")]'):
            matches = re.findall(r'(20\d{2}-\d{2}-\d{2})\s*发布', node.text_content())
            candidates.extend({'value': item, 'basis': 'article_footer_publication_label'} for item in matches)
    if raw.get('published_at'):
        candidates.append({'value': raw['published_at'], 'basis': 'source_manifest_record'})
    if raw.get('detail_displayed_date'):
        candidates.append({'value': raw['detail_displayed_date'], 'basis': 'article_detail_displayed_date'})
    if raw.get('list_publication_date'):
        candidates.append({'value': raw['list_publication_date'], 'basis': 'source_listing_date'})
    for item in candidates:
        if not valid_date(item['value']):
            raise ValueError('Abnormal date candidate')
    chosen = next((item for item in candidates if item['basis'] != 'source_listing_date'), None)
    return {'published_at': chosen['value'] if chosen else None,
            'published_at_basis': chosen['basis'] if chosen else 'unknown',
            'date_candidates': candidates,
            'date_conflict': len({item['value'] for item in candidates}) > 1}


def process_document(raw, rule, scope_version, cache_path):
    validate_input(raw)
    blocks = extract_blocks(raw['raw_html'])
    if re.sub(r'\s+', '', ''.join(b.text for b in blocks)) != re.sub(r'\s+', '', raw['raw_text']):
        raise ValueError('Block extraction lost or introduced body text')
    selected, audit = scope_blocks(blocks, rule)
    normalized = [(block, text, *normalize_text(text)) for block, text in selected]
    body_texts = {clean for block, _, clean, _ in normalized if block.role != 'caption'}
    caption_seen = set()
    retained, examples, statistics = [], [], Counter()
    audit_by_id = {event['block_id']: event for event in audit}
    for block, before, clean, counts in normalized:
        event = audit_by_id[block.block_id]
        event['normalization'] = counts
        statistics.update(counts)
        action = 'retain'
        if not clean:
            action = 'remove_empty'
        elif PLAYER_RE.fullmatch(clean):
            action = 'remove_player'
        elif PLACEHOLDER_RE.fullmatch(clean):
            action = 'remove_placeholder'
        elif block.role == 'caption' and (clean in caption_seen or clean in body_texts):
            action = 'remove_duplicate_caption'
        event['cleaning_action'] = action
        event['normalized_chars'] = nonspace_len(clean)
        if action == 'retain':
            retained.append((block, clean))
            if block.role == 'caption':
                caption_seen.add(clean)
        else:
            statistics[action] += 1
        if before != clean or action != 'retain':
            examples.append({'doc_id': raw['doc_id'], 'block_id': block.block_id,
                             'rule_counts': counts, 'action': action,
                             'before': before, 'after': clean if action == 'retain' else ''})
    clean_text = '\n\n'.join(clean for _, clean in retained)
    spans, offset = [], 0
    for block, clean in retained:
        spans.append({'block_id': block.block_id, 'role': block.role, 'xpath': block.xpath,
                      'start': offset, 'end': offset+len(clean), 'text': clean})
        offset += len(clean)+2
    if not clean_text:
        raise ValueError('Empty cleaned document')
    for anchor in rule['protected_evidence']:
        if anchor not in clean_text:
            raise ValueError('Protected evidence lost: ' + repr(anchor))
    for anchor in rule['forbidden_independent_sections']:
        if anchor in clean_text:
            raise ValueError('Unrelated independent section retained: ' + repr(anchor))
    raw_scope = '\n\n'.join(text for _, text in selected)
    metrics = {'source_chars': nonspace_len(raw['raw_text']), 'scope_chars': nonspace_len(raw_scope),
               'clean_chars': nonspace_len(clean_text), 'source_blocks': len(blocks),
               'scope_blocks': len(selected), 'clean_blocks': len(spans), 'rules': dict(statistics)}
    record = {field: raw.get(field) for field in REQUIRED+OPTIONAL}
    record.update(publication_metadata(raw, cache_path))
    flags = set(raw.get('review_flags', []))
    # Earlier acquisition flags describe the full raw body, not necessarily the
    # selected scope; carry that distinction explicitly.
    flags.discard('repeated_paragraph_or_caption')
    flags.discard('invisible_unicode_present')
    if record['date_conflict']:
        flags.add('publication_date_candidates_disagree')
    if raw['text_type'] == 'tourist_note' and metrics['clean_chars'] < 800:
        flags.add('short_selected_tourist_scope_reviewed')
    if any(event['scope_action'] != 'keep' for event in audit):
        flags.add('scenic_scope_selected_from_full_article')
    record.update(raw_text=raw_scope, clean_text=clean_text, blocks=spans,
                  content_scope='reviewed_scenic_scope_from_article', processing_scope='text_only',
                  scope_version=scope_version, content_issues=rule['content_issues'],
                  review_flags=sorted(flags), final_url=raw['final_url'],
                  source_response_sha256=raw['response_sha256'], source_raw_text_sha256=raw['raw_text_sha256'],
                  raw_scope_sha256=sha_text(raw_scope), clean_text_sha256=sha_text(clean_text),
                  metrics=metrics, image_information_status=raw['image_information_status'],
                  source_image_element_count=raw['image_element_count'], duplicate_of=None,
                  notes=rule['notes']+' 原日序、代词、否定与条件保留；原文事实疑点另列content_issues。')
    return record, {'doc_id': raw['doc_id'], 'scope_version': scope_version, 'blocks': audit,
                    'metrics': metrics}, examples


def duplicate_groups(records):
    groups = {}
    for record in records:
        # Whitespace-only differences do not make a different article.
        digest = sha_text(re.sub(r'\s+', '', record['clean_text']))
        groups.setdefault(digest, []).append(record['doc_id'])
    return [group for group in groups.values() if len(group) > 1]


def near_duplicates(records, threshold=0.82):
    features = {}
    for record in records:
        compact = re.sub(r'\s+', '', record['clean_text'])
        features[record['doc_id']] = {compact[i:i+5] for i in range(max(1, len(compact)-4))}
    result = []
    for i, first in enumerate(records):
        for second in records[i+1:]:
            if first['scenic_id'] != second['scenic_id']:
                continue
            a, b = features[first['doc_id']], features[second['doc_id']]
            similarity = len(a & b)/len(a | b) if a | b else 1
            if similarity >= threshold:
                result.append({'doc_ids': [first['doc_id'], second['doc_id']], 'jaccard_5gram': round(similarity, 4)})
    return result


def quality_report(records, manifest, audits):
    counts = Counter((r['scenic_id'], r['text_type']) for r in records)
    duplicates = duplicate_groups(records)
    expected_ids = {s['doc_id'] for s in manifest['sources']}
    problems = []
    if len(records) != 30 or {r['doc_id'] for r in records} != expected_ids or len(expected_ids) != 30:
        problems.append('document_identity_or_count')
    if len(counts) != 6 or any(count != 5 for count in counts.values()):
        problems.append('scenic_type_counts')
    if duplicates:
        problems.append('exact_duplicate_documents')
    if len({r['source_url'] for r in records}) != len(records):
        problems.append('duplicate_source_urls')
    for r in records:
        text = r['clean_text']
        if any(not r.get(key) for key in REQUIRED):
            problems.append(r['doc_id']+':required_fields')
        if HTML_RE.search(text) or URL_RE.search(text) or '\ufffd' in text:
            problems.append(r['doc_id']+':html_url_or_replacement_character')
        if any(char in INVISIBLE or (unicodedata.category(char)=='Cc' and char!='\n') for char in text):
            problems.append(r['doc_id']+':technical_control_character')
        if any(normalize_text(b['text'])[0] != b['text'] for b in r['blocks']):
            problems.append(r['doc_id']+':normalization_not_idempotent')
        if any(text[b['start']:b['end']] != b['text'] for b in r['blocks']):
            problems.append(r['doc_id']+':block_offsets')
        if not valid_date(r['published_at']):
            problems.append(r['doc_id']+':published_date')
    totals = Counter()
    rules = Counter()
    for r in records:
        totals.update({key: r['metrics'][key] for key in ('source_chars','scope_chars','clean_chars','source_blocks','scope_blocks','clean_blocks')})
        rules.update(r['metrics']['rules'])
    for name in ('nfc_blocks', 'line_endings', 'invisible_characters', 'control_characters',
                 'special_spaces', 'body_urls', 'duplicate_comma_groups', 'whitespace_blocks',
                 'remove_empty', 'remove_player', 'remove_placeholder', 'remove_duplicate_caption'):
        rules.setdefault(name, 0)
    return {'version': 'selected_v2_text_only_1', 'processing_scope': 'text_only',
            'status': 'pass' if not problems else 'fail', 'problems': problems,
            'expected_documents': 30, 'actual_documents': len(records),
            'counts': [{'scenic_id': k[0], 'text_type': k[1], 'count': n} for k,n in sorted(counts.items())],
            'totals': dict(totals), 'cleaning_rule_counts': dict(rules),
            'scope_removed_chars': totals['source_chars']-totals['scope_chars'],
            'cleaning_removed_chars': totals['scope_chars']-totals['clean_chars'],
            'required_field_missing': {key: sum(not r.get(key) for r in records) for key in REQUIRED},
            'optional_field_nulls': {key: sum(r.get(key) is None for r in records) for key in OPTIONAL},
            'exact_duplicate_groups': duplicates, 'near_duplicate_threshold': 0.82,
            'near_duplicate_warnings': near_duplicates(records),
            'date_conflicts': [{'doc_id': r['doc_id'], 'candidates': r['date_candidates']} for r in records if r['date_conflict']],
            'content_issues': [{'doc_id': r['doc_id'], **issue} for r in records for issue in r['content_issues']],
            'review_flags': [{'doc_id': r['doc_id'], 'flags': r['review_flags']} for r in records if r['review_flags']],
            'documents': [{key:r[key] for key in ('doc_id','scenic_id','text_type','published_at','published_at_basis','clean_text_sha256','metrics')} for r in records],
            'validation_notes': ['30份输入内容哈希和范围指纹已核对', '正文结构抽取文字与原采集文字逐字一致（忽略空白）',
                                 '所有配置保护短语仍在，排除章节短语不在', '段落偏移、清洗幂等、必填字段和格式检查通过才标记pass',
                                 '统计检查不等于事实正确率；不是实体、共指或路线关系金标准', '未把范围删减计为字符清洗效果']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path('data/metadata/selected_v2_sources.json'))
    parser.add_argument('--scope-rules', type=Path, default=Path('data/metadata/selected_v2_scope_rules.json'))
    parser.add_argument('--raw-input', type=Path, default=Path('data/raw/full/selected_v2'))
    parser.add_argument('--cache', type=Path, default=Path('data/downloads/selected_v2'))
    parser.add_argument('--output', type=Path, default=Path('data/processed/full/selected_v2'))
    parser.add_argument('--report', type=Path, default=Path('data/metadata/selected_v2_quality_report.json'))
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    scope = json.loads(args.scope_rules.read_text(encoding='utf-8'))
    if scope['processing_scope'] != 'text_only' or set(scope['rules']) != {s['doc_id'] for s in manifest['sources']}:
        raise ValueError('Scope and source manifest do not match')
    records, audits, examples = [], [], []
    for source in manifest['sources']:
        did = source['doc_id']
        raw = json.loads((args.raw_input/(did+'.json')).read_text(encoding='utf-8'))
        for key in ('doc_id','scenic_id','scenic_name','text_type','title','source_url','publisher'):
            if raw.get(key) != source[key]:
                raise ValueError(did+': source manifest mismatch in '+key)
        record, audit, changes = process_document(raw, scope['rules'][did], scope['version'], args.cache/(did+'.html'))
        records.append(record); audits.append(audit); examples.extend(changes)
    report = quality_report(records, manifest, audits)
    write_json(args.report, report)
    if report['status'] != 'pass':
        raise ValueError('Quality checks failed: '+repr(report['problems']))
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output/'dataset.json', records)
    (args.output/'dataset.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records), encoding='utf-8', newline='\n')
    for record, audit in zip(records, audits):
        text_path = args.output/'texts'/(record['doc_id']+'.txt')
        text_path.parent.mkdir(parents=True, exist_ok=True)
        text_path.write_text(record['clean_text'], encoding='utf-8', newline='\n')
        write_json(args.output/'audit'/(record['doc_id']+'.json'), audit)
    write_json(args.output/'before_after_examples.json', examples)
    write_json(args.output/'quality_report.json', report)
    print(json.dumps({'status':report['status'], 'documents':len(records), 'totals':report['totals'],
                      'date_conflicts':len(report['date_conflicts']), 'output':str(args.output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
