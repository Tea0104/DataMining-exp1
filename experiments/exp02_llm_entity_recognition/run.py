"""运行独立 LLM 景点抽取，并在固定语料上对照 v3 和 v7。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = HERE.parent / 'exp02_entity_recognition'
sys.path.insert(0, str(BASE / 'src'))
from evaluate import gold_set, pred_set, prf

DATASET = ROOT / 'data/processed/full/selected_v2/dataset.json'
REFERENCE = BASE / 'outputs/gold_remaining25.json'
SCENICS = ('TAISHAN', 'WULINGYUAN', 'JINGYUETAN')
LOCAL_HOSTS = ('127.0.0.1', 'localhost', '::1')
POI_SCHEMA = {
    'type': 'object', 'required': ['pois'], 'additionalProperties': False,
    'properties': {'pois': {'type': 'array', 'maxItems': 96,
                            'items': {'type': 'string', 'maxLength': 60}}},
}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def chunks(text, size):
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            mid = start + size // 2
            boundary = max(text.rfind(c, mid, end) for c in '\n。！？；')
            if boundary < mid:
                boundary = max(text.rfind(c, mid, end) for c in '，、→')
            if boundary >= mid:
                end = boundary + 1
        yield start, text[start:end]
        start = end


def request_names(endpoint, model, api_key, prompt, content):
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    response_format = {'type': 'json_object'}
    host = urllib.parse.urlsplit(endpoint).hostname
    deepseek_flash = host == 'api.deepseek.com' and model == 'deepseek-flash'
    if host in LOCAL_HOSTS:
        response_format['schema'] = POI_SCHEMA
    payload = {
        'model': model, 'temperature': 0, 'max_tokens': 1280,
        'response_format': response_format,
        'messages': [
            {'role': 'system', 'content': prompt},
            {'role': 'user', 'content': content},
        ],
    }
    if deepseek_flash:
        payload['thinking'] = {'type': 'disabled'}
        payload['messages'][0]['content'] += '\n输出格式：json。'
    req = urllib.request.Request(endpoint, json.dumps(payload, ensure_ascii=False).encode(), headers)
    try:
        for _ in range(3 if deepseek_flash else 1):
            with urllib.request.urlopen(req, timeout=180) as res:
                choice = json.load(res)['choices'][0]
            raw = choice['message']['content']
            if choice['finish_reason'] != 'stop' or (raw and raw.strip()):
                break
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'模型接口返回 HTTP {exc.code}') from None
    except urllib.error.URLError as exc:
        raise RuntimeError('无法连接模型接口，请检查服务地址和运行状态') from exc
    if choice['finish_reason'] != 'stop':
        raise ValueError(f"模型响应未正常结束：{choice['finish_reason']}")
    if not raw or not raw.strip():
        raise ValueError('模型返回空的 JSON 内容')
    names = json.loads(raw)['pois']
    if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
        raise ValueError('模型响应须包含 pois 字符串数组')
    return names


def nonoverlap(candidates, occupied=()):
    kept = list(occupied)
    for candidate in sorted(candidates, key=lambda e: (e['start'] - e['end'], e['start'])):
        if not any(candidate['start'] < old['end'] and old['start'] < candidate['end'] for old in kept):
            kept.append(candidate)
    return sorted(kept, key=lambda e: (e['start'], e['end']))


def passage(text, start, end, context_size):
    left = text[max(0, start - context_size):start]
    right = text[end:end + context_size]
    return f'前文参考：{left}\n待抽取正文：\n{text[start:end]}\n后文参考：{right}'


def extract_doc(record, args, endpoint, api_key, prompt):
    proposals, audit = [], []
    text = record['clean_text']
    for offset, chunk in chunks(text, args.chunk_size):
        chunk_end = offset + len(chunk)
        content = f'目标景区：{record["scenic_name"]}\n' + passage(text, offset, chunk_end, args.context_size)
        names = request_names(endpoint, args.model, api_key, prompt, content)
        rejected = []
        for name in dict.fromkeys(names):
            if not 2 <= len(name) <= 60 or name != name.strip() or name not in chunk:
                rejected.append(name)
                continue
            for match in re.finditer(re.escape(name), chunk):
                start, end = offset + match.start(), offset + match.end()
                proposals.append({'doc_id': record['doc_id'], 'scenic_id': record['scenic_id'],
                                  'entity_type': 'POI', 'text': name, 'start': start, 'end': end,
                                  'method': 'llm_exact_text'})
        audit.append({'start': offset, 'end': chunk_end, 'returned_names': names,
                      'rejected_names': rejected})
    return {'doc_id': record['doc_id'], 'entities': nonoverlap(proposals), 'chunks': audit}


def verify_additions(record, result, baseline, args, endpoint, api_key, prompt):
    known_names = {e['text'] for e in baseline if e['entity_type'] == 'POI'}
    new = [e for e in nonoverlap(result['entities'], baseline)
           if e.get('method') == 'llm_exact_text' and e['text'] not in known_names]
    verified, audit = [], []
    for chunk in result['chunks']:
        start, end = chunk['start'], chunk['end']
        candidates = [e for e in new if start <= e['start'] < end]
        names = list(dict.fromkeys(e['text'] for e in candidates))
        if not names:
            continue
        context = passage(record['clean_text'], start, end, args.context_size)
        content = (f'目标景区：{record["scenic_name"]}\n候选：{json.dumps(names, ensure_ascii=False)}\n'
                   + context)
        accepted = request_names(endpoint, args.model, api_key, prompt, content)
        verified.extend(e for e in candidates if e['text'] in accepted)
        audit.append({'start': start, 'end': end, 'candidates': names, 'returned_names': accepted})
    return {'entities': verified, 'chunks': audit}


def pilot(records):
    """按文档编号选每个景区的首篇官方路线和首篇游客游记。"""
    chosen = {}
    for record in sorted(records, key=lambda r: r['doc_id']):
        chosen.setdefault((record['scenic_id'], record['text_type']), record)
    return list(chosen.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default=os.getenv('LLM_BASE_URL', 'http://127.0.0.1:8089/v1'))
    parser.add_argument('--model', default=os.getenv('LLM_MODEL', 'qwen3-4b-2507'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pilot', action='store_true')
    parser.add_argument('--chunk-size', type=int, default=550)
    parser.add_argument('--context-size', type=int, default=110)
    parser.add_argument('--prompt', type=Path, default=HERE / 'prompt.txt',
                        help='抽取提示词文件，默认使用本目录的 prompt.txt')
    parser.add_argument('--input', type=Path, default=DATASET,
                        help='与实验一 dataset.json 同结构的正文；自定义输入仅运行独立抽取')
    args = parser.parse_args()
    if args.chunk_size < 100:
        parser.error('--chunk-size 至少为100')
    if args.context_size < 0:
        parser.error('--context-size 不能为负数')
    host = urllib.parse.urlsplit(args.base_url)
    local = host.hostname in LOCAL_HOSTS
    if host.scheme not in ('http', 'https') or not host.hostname or host.username or host.password or host.query or host.fragment:
        parser.error('--base-url 须为不含凭据、查询参数或片段的 HTTP(S) 地址')
    api_key = os.getenv('LLM_API_KEY')
    if not local and (host.scheme != 'https' or not api_key):
        parser.error('云端接口需要 HTTPS 和环境变量 LLM_API_KEY')
    endpoint = args.base_url.rstrip('/') + '/chat/completions'
    prompt = args.prompt.read_text(encoding='utf-8')
    verify_prompt = (HERE / 'verify_prompt.txt').read_text(encoding='utf-8')
    records = read(args.input)
    ref = None
    if args.input.resolve() == DATASET.resolve():
        ref = read(REFERENCE)
        scope = set(ref['doc_scope'])
        records = [r for r in records if r['doc_id'] in scope]
        if {r['doc_id'] for r in records} != scope:
            raise ValueError('输入数据和参考文档范围不一致')
        for r in records:
            if sha(r['clean_text'].encode()) != ref['source_text_sha256'][r['doc_id']]:
                raise ValueError(f"正文与参考版本不一致：{r['doc_id']}")
    if len({r['doc_id'] for r in records}) != len(records):
        raise ValueError('输入数据中存在重复文档编号')
    if args.pilot:
        records = pilot(records)
    ids = {r['doc_id'] for r in records}
    baseline = {}
    paths = []
    if ref:
        for version in ('v3', 'v7'):
            by_doc = {doc_id: [] for doc_id in ids}
            for scenic in SCENICS:
                path = BASE / f'outputs/entities_{scenic}_{version}.json'
                paths.append(path)
                for e in read(path):
                    if e['doc_id'] in ids:
                        by_doc[e['doc_id']].append(e)
            baseline[version] = by_doc
    settings = {'model': args.model, 'base_url': args.base_url, 'chunk_size': args.chunk_size,
                'context_size': args.context_size, 'input_sha256': sha(args.input.read_bytes()),
                'prompt_sha256': sha(prompt.encode()), 'runner_sha256': sha(Path(__file__).read_bytes()),
                'verify_prompt_sha256': sha(verify_prompt.encode()) if ref else None,
                'reference_sha256': sha(REFERENCE.read_bytes()) if ref else None,
                'baseline_sha256': {p.name: sha(p.read_bytes()) for p in paths},
                'documents': sorted(ids)}
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / 'manifest.json'
    if manifest.exists() and read(manifest) != settings:
        raise ValueError('该目录已有不同配置的运行，请换输出目录')
    write(manifest, settings)
    docs = out / 'documents'
    docs.mkdir(exist_ok=True)
    standalone, audit, verified = [], [], []
    verification_requests = 0
    hybrid = {version: [] for version in baseline}
    for record in records:
        doc_id = record['doc_id']
        if not re.fullmatch(r'[A-Za-z0-9_-]+', doc_id):
            raise ValueError(f'无效文档编号：{doc_id}')
        path = docs / f'{doc_id}.json'
        if path.exists():
            result = read(path)
        else:
            print(f'抽取 {doc_id}（{len(record["clean_text"])} 字符）', flush=True)
            result = extract_doc(record, args, endpoint, api_key, prompt)
            write(path, result)
        if ref:
            if 'v7_verification' not in result:
                result['v7_verification'] = verify_additions(
                    record, result, baseline['v7'][doc_id], args, endpoint, api_key, verify_prompt)
                write(path, result)
            review = result['v7_verification']
            verified.extend(nonoverlap(review['entities'], baseline['v7'][doc_id]))
            verification_requests += len(review['chunks'])
        standalone.extend(result['entities'])
        for version, by_doc in baseline.items():
            hybrid[version].extend(nonoverlap(result['entities'], by_doc[doc_id]))
        audit.extend(result['chunks'])
        print(f'{doc_id} 完成，模型定位 {len(result["entities"])} 处', flush=True)
    write(out / 'llm_entities.json', standalone)
    if not ref:
        return
    truth = {item for item in gold_set(ref) if item[0] in ids and item[1] == 'POI'}
    scores = {}
    predictions = {'llm': standalone}
    for version, by_doc in baseline.items():
        predictions[version] = [e for group in by_doc.values() for e in group]
        predictions[f'{version}_plus_llm'] = hybrid[version]
        filename = 'hybrid_entities.json' if version == 'v3' else 'v7_hybrid_entities.json'
        write(out / filename, hybrid[version])
    predictions['v7_plus_verified_llm'] = verified
    write(out / 'v7_verified_entities.json', verified)
    for label, entities in predictions.items():
        pred = {item for item in pred_set(entities) if item[1] == 'POI'}
        scores[label] = {**prf(pred, truth), 'missed': sorted(truth - pred),
                         'unmatched_predictions': sorted(pred - truth)}
    write(out / 'evaluation.json', {
        'documents': sorted(ids), 'reference_status': ref['annotated_by'],
        'reference_human_reviewed': ref['human_reviewed'],
        'evaluation_level': 'document_type_surface_name', 'reference_poi': len(truth),
        'requests': len(audit), 'verification_requests': verification_requests,
        'rejected_names': sum(len(c['rejected_names']) for c in audit),
        'scores': scores,
    })
    print({k: {m: v[m] for m in ('tp', 'fp', 'fn', 'precision', 'recall', 'f1')}
           for k, v in scores.items()}, flush=True)


if __name__ == '__main__':
    main()
