"""Offline end-to-end replay, byte comparison and regression test evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import unittest

from lxml import etree

ROOT = Path(__file__).resolve().parents[3]


def run_step(name, arguments, log_dir):
    result = subprocess.run([sys.executable, *arguments], cwd=ROOT, capture_output=True,
                            text=True, encoding='utf-8', errors='strict',
                            env={**os.environ, 'PYTHONIOENCODING':'utf-8'})
    (log_dir/(name+'.log')).write_text(result.stdout+result.stderr, encoding='utf-8')
    if result.returncode:
        raise RuntimeError(name+' failed; see '+str(log_dir/(name+'.log')))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replay-dir', type=Path, default=ROOT/'data/processed/full/selected_v2_replay')
    parser.add_argument('--report', type=Path, default=ROOT/'data/metadata/selected_v2_verification.json')
    args = parser.parse_args()
    replay = args.replay_dir.resolve()
    original = ROOT/'data/processed/full/selected_v2'
    if replay == original.resolve() or original.resolve() in replay.parents:
        raise ValueError('Replay must use a separate directory outside the reference dataset')
    replay.mkdir(parents=True, exist_ok=True)
    src = 'experiments/exp01_data_preprocessing/src/'
    run_step('acquisition', [src+'capture_selected_sources.py', '--offline',
                           '--raw-output', str(replay/'raw'), '--report', str(replay/'acquisition_report.json')], replay)
    run_step('preprocessing', [src+'preprocess_selected.py', '--raw-input', str(replay/'raw'),
                             '--output', str(replay/'processed'), '--report', str(replay/'quality_report.json')], replay)
    paths = sorted(p.relative_to(original) for p in original.rglob('*') if p.is_file())
    reproduced = {p.relative_to(replay/'processed') for p in (replay/'processed').rglob('*') if p.is_file()}
    different = [str(path) for path in paths if path not in reproduced or (original/path).read_bytes() != (replay/'processed'/path).read_bytes()]
    extra = [str(path) for path in reproduced-set(paths)]
    if different or extra or not paths:
        raise ValueError('Replay differs: '+repr({'different':different, 'extra':extra}))
    suite = unittest.defaultTestLoader.discover(str(ROOT/'experiments/exp01_data_preprocessing/tests'))
    with (replay/'tests.log').open('w', encoding='utf-8') as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    if not result.wasSuccessful() or result.skipped:
        raise ValueError('Tests failed or skipped; see '+str(replay/'tests.log'))
    acquisition = json.loads((replay/'acquisition_report.json').read_text(encoding='utf-8'))
    report = {'status':'pass', 'python_version':platform.python_version(), 'lxml_version':list(etree.LXML_VERSION),
              'test_count':result.testsRun, 'failures':len(result.failures), 'errors':len(result.errors),
              'skipped':len(result.skipped), 'offline_acquisition_success':acquisition['successful_documents'],
              'reproduced_output_files':len(paths), 'byte_identical_files':len(paths)-len(different),
              'mismatched_files':different, 'unexpected_files':extra,
              'dataset_json_sha256':hashlib.sha256((original/'dataset.json').read_bytes()).hexdigest(),
              'dataset_jsonl_sha256':hashlib.sha256((original/'dataset.jsonl').read_bytes()).hexdigest(),
              'definition':'独立输出目录从30份缓存HTML重新提取再清洗，与正式输出逐文件字节比较；不重新联网。'}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(report,ensure_ascii=False))


if __name__ == '__main__':
    main()
