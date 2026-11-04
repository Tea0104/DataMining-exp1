"""全30篇v4复现；助手语义判定绑定预测哈希，变动后拒绝沿用旧分数。"""
import subprocess
import sys
from common import BASE, DATASET, DEFAULT_DOCS, OUTPUTS, load_records


def main():
    remaining = [r['doc_id'] for r in load_records(DATASET) if r['doc_id'] not in DEFAULT_DOCS]
    src, rest = BASE / 'src', OUTPUTS / 'remaining25'
    commands = [
        ('detect.py', []), ('resolve.py', ['--version', 'v4']),
        ('evaluate.py', ['--version', 'v4']),
        ('detect.py', ['--docs', *remaining, '--outputs', str(rest)]),
        ('resolve.py', ['--version', 'v4', '--samples', str(rest / 'samples.json'), '--outputs', str(rest)]),
        ('assess_v4.py', []), ('review.py', []), ('verify.py', [])]
    for script, args in commands:
        subprocess.run([sys.executable, str(src / script), *args], check=True)


if __name__ == '__main__':
    main()
