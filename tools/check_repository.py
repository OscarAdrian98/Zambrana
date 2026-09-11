"""Verificación estática del árbol publicable. Nunca imprime valores sensibles."""
from __future__ import annotations
import ast
from collections import Counter
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'.git', '.rebuild', '.venv', 'venv', 'node_modules'}
FORBIDDEN_DIRS = {'__pycache__', '.pytest_cache', 'logs', 'backups', 'build', 'dist', 'instance', 'data'}
FORBIDDEN_SUFFIXES = {'.pyc', '.pyo', '.exe', '.dll', '.msi', '.zip', '.7z', '.rar', '.db',
                      '.sqlite', '.sqlite3', '.log', '.pdf', '.xlsx', '.xls', '.pem', '.key', '.p12', '.pfx', '.old'}
TEXT = {'.py', '.php', '.js', '.css', '.html', '.tpl', '.svg', '.xml', '.md', '.txt', '.json',
        '.ini', '.mako', '.csv', '.yml', '.yaml', '.lock', '.example', '.cmd'}
GRAPHICS = {'.png', '.jpg'}
RULES = {
    'private-key': r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'api-token': r'\b(?:gsk_|ghp_|github_pat_|sk-proj-)[A-Za-z0-9_-]{20,}',
    'webhook': r'https://(?:discord(?:app)?\.com)/api/webhooks/\d+/[A-Za-z0-9_-]+',
    'internal-ip': r'\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b',
    'personal-path': r'(?i)\b[A-Z]:\\(?:Users|TRABAJO|Oscar|laragon)\\',
    'connection-credential': r'://[^/\s:]+:[^@\s{}]+@',
    'bank-account': r'\b[A-Z]{2}\d{2}(?:[ -]?\d){16,30}\b',
}
SECRET_FIELD = re.compile(r'(?i)(?:password|passwd|secret_key|api_key|webhook|semilla_privada|private_key|pass_ambar|pass_prest)$')
PLACEHOLDER = re.compile(r'(?i)^(?:|change_me|your_[a-z_]+|example_[a-z_]+|test[-_ ].*|.*(?:test-only|for-tests|testing-only).*)$')

def files():
    for directory, dirs, names in os.walk(ROOT):
        dirs[:] = sorted(d for d in dirs if d not in SKIP)
        for name in sorted(names):
            yield Path(directory)/name

def entropy(value):
    counts = Counter(value)
    return -sum((n/len(value))*math.log2(n/len(value)) for n in counts.values())

def check():
    issues = []
    count = 0
    def issue(path, line, rule):
        issues.append(f'{path}:{line}: {rule}')
    for path in files():
        rel = path.relative_to(ROOT).as_posix()
        count += 1
        if any(p in FORBIDDEN_DIRS for p in path.relative_to(ROOT).parts):
            issue(rel, 0, 'generated-directory')
        if path.suffix.lower() in FORBIDDEN_SUFFIXES or (path.name.startswith('.env') and path.name != '.env.example'):
            issue(rel, 0, 'forbidden-artifact')
        if path.suffix.lower() == '.csv' and 'examples' not in path.parts and 'fixtures' not in path.parts:
            issue(rel, 0, 'operational-csv')
        if path.suffix.lower() in GRAPHICS:
            if not rel.startswith('mxz_ruedas/img/'):
                issue(rel, 0, 'unreviewed-image')
            continue
        if path.suffix.lower() not in TEXT and path.name not in {'.gitignore', '.gitattributes', 'NOTICE'}:
            issue(rel, 0, 'unreviewed-file-type')
            continue
        try:
            text = path.read_text(encoding='utf-8-sig')
        except UnicodeError:
            issue(rel, 0, 'non-text-file')
            continue
        for name, pattern in RULES.items():
            for match in re.finditer(pattern, text):
                if name == 'connection-credential' and ':change_me@' in match[0]:
                    continue
                issue(rel, text.count('\n', 0, match.start())+1, name)
        for match in re.finditer(r'[\w.+-]+@([\w.-]+\.[A-Za-z]{2,})', text):
            if not re.fullmatch(r'(?:(?:[a-z0-9-]+\.)*-?example\.{1,2}(?:com|test|invalid)|test\.(?:com|local))', match[1], re.I):
                issue(rel, text.count('\n', 0, match.start())+1, 'non-example-email')
        if path.suffix == '.py':
            try:
                tree = ast.parse(text, filename=rel)
            except SyntaxError as error:
                issue(rel, error.lineno, 'python-syntax')
                continue
            fixture = '/tests/' in '/'+rel or rel.endswith('config/test_config.py')
            for node in ast.walk(tree):
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    value = node.value
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        if any(SECRET_FIELD.search(ast.unparse(t)) for t in targets):
                            if not fixture and not PLACEHOLDER.fullmatch(value.value):
                                issue(rel, node.lineno, 'credential-literal')
        # Entropía: hashes de integridad públicos de CDN se revisan por separado.
        for num, line in enumerate(text.splitlines(), 1):
            if 'integrity=' in line or rel.startswith('tools/'):
                continue
            for token in re.findall(r'(?<![\w])[A-Za-z0-9+/=_-]{40,}(?![\w])', line):
                if '_' not in token and any(c.isdigit() for c in token) and entropy(token) > 4.5:
                    issue(rel, num, 'high-entropy-review')
        if path.suffix == '.json':
            try: json.loads(text)
            except ValueError: issue(rel, 0, 'invalid-json')
    for item in sorted(set(issues)):
        print(item)
    print(f'Checked {count} files; {len(set(issues))} findings. Values are never printed.')
    return bool(issues)

if __name__ == '__main__':
    raise SystemExit(check())
