"""实验四共享的数据读取、句子边界与位置校验。"""
import hashlib
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[1]
DATASET = ROOT / 'data/processed/full/selected_v2/dataset.json'
OUTPUTS = BASE / 'outputs'
DEFAULT_DOCS = ('TS_NOTE_001', 'TS_NOTE_005', 'ZJJ_NOTE_005', 'JYT_NOTE_001', 'JYT_NOTE_004')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n',
                    encoding='utf-8', newline='\n')


def sentences(text):
    result = []
    for match in re.finditer(r'[^。！？!?；;\n]+[。！？!?；;\n]*', text):
        if match.group().strip():
            result.append({'sentence_id': len(result) + 1, 'start': match.start(),
                           'end': match.end(), 'text': match.group()})
    return result


def span(text, start, end, **extra):
    if not (0 <= start < end <= len(text)):
        raise ValueError(f'非法字符范围: {start}:{end}')
    return {'start': start, 'end': end, 'text': text[start:end], **extra}


def validate_span(text, value):
    if not (0 <= value['start'] < value['end'] <= len(text)):
        raise ValueError(f'非法字符范围: {value}')
    if text[value['start']:value['end']] != value['text']:
        raise ValueError(f'位置与原文不符: {value}')


def text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def load_records(path=DATASET):
    records = read_json(path)
    ids = [r['doc_id'] for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError('数据集中存在重复 doc_id')
    return records
