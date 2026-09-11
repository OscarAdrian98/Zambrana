"""Sintaxis PHP y JavaScript sin iniciar aplicaciones."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from check_repository import files

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--php', default='php')
parser.add_argument('--node', default='node')
args = parser.parse_args()
counts = {'php': 0, 'js': 0, 'inline': 0}
failed = False
for name in [args.php, args.node]:
    if not shutil.which(name):
        raise SystemExit(f'Required syntax checker is unavailable: {name}')
for path in files():
    if path.suffix == '.php':
        command = [args.php, '-n', '-l', str(path)]
        counts['php'] += 1
    elif path.suffix == '.js':
        command = [args.node, '--check', str(path)]
        counts['js'] += 1
    else:
        continue
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        print(f'{path.relative_to(ROOT)}: syntax failure')
        failed = True

scratch = ROOT/'.rebuild'
scratch.mkdir(exist_ok=True)
for path in files():
    if path.suffix not in {'.php', '.html', '.tpl'}:
        continue
    text = path.read_text(encoding='utf-8-sig')
    for number, body in enumerate(re.findall(r'<script\b[^>]*>(.*?)</script>', text, re.S | re.I), 1):
        body = re.sub(r'<\?php.*?\?>', 'null', body, flags=re.S)
        body = re.sub(r'\{\{.*?\}\}', 'null', body, flags=re.S)
        body = re.sub(r'\{%.*?%\}', '', body, flags=re.S)
        if not body.strip():
            continue
        counts['inline'] += 1
        with tempfile.TemporaryDirectory(dir=scratch) as temporary:
            script = Path(temporary)/'inline.js'
            script.write_text(body, encoding='utf-8')
            result = subprocess.run([args.node, '--check', str(script)], capture_output=True, text=True)
            if result.returncode:
                print(f'{path.relative_to(ROOT)}: inline script {number}: syntax failure')
                failed = True
print(f"Checked {counts['php']} PHP, {counts['js']} JavaScript and {counts['inline']} inline scripts.")
raise SystemExit(failed)
