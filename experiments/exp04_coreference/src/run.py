"""从仓库根目录一键运行五篇检测、四版预测、评价和复核表。"""
import subprocess
import sys
from pathlib import Path


def main():
    src = Path(__file__).resolve().parent
    for script, arguments in [
        ('detect.py', []),
        ('resolve.py', ['--version', 'v1']), ('resolve.py', ['--version', 'v2']),
        ('resolve.py', ['--version', 'v3']),
        ('resolve.py', ['--version', 'v4']),
        ('evaluate.py', ['--version', 'v1']), ('evaluate.py', ['--version', 'v2']),
        ('evaluate.py', ['--version', 'v3']),
        ('evaluate.py', ['--version', 'v4']),
        ('review.py', []),
        ('verify.py', []),
    ]:
        subprocess.run([sys.executable, str(src / script), *arguments], check=True)


if __name__ == '__main__':
    main()
