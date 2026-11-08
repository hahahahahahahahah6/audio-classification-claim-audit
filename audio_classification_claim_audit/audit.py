"""Deterministic documentation and single-module AST inspection."""
import argparse
import ast
import json
from pathlib import Path
import re
import sys
from . import __version__
from .phrases import AUDIOCLASSIFICATION, NOAUDIOCLASSIFICATION, GENERIC_NAMES, DEDICATED_NAMES


def match_phrases(text, phrases):
    text = text.lower()
    hits = []
    for phrase in sorted(phrases, key=len, reverse=True):
        start = text.find(phrase)
        while start >= 0:
            hits.append(phrase)
            text = text[:start] + ' ' * len(phrase) + text[start + len(phrase):]
            start = text.find(phrase)
    return hits, text


def claims(text):
    prose = []
    fenced = False
    for line in text.splitlines():
        if re.match(r'^\s*```', line):
            fenced = not fenced
        elif not fenced:
            prose.append(line.replace('`', ''))
    negative, remaining = match_phrases('\n'.join(prose), NOAUDIOCLASSIFICATION)
    positive, _ = match_phrases(remaining, AUDIOCLASSIFICATION)
    return positive, negative


def evidence(source):
    tree = ast.parse(source)
    aliases = {}
    shadow = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split('.')[0]] = alias.name if alias.asname else alias.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                aliases[alias.asname or alias.name] = (node.module or '') + '.' + alias.name

    def resolve(node):
        if isinstance(node, ast.Name):
            if node.id in shadow:
                return ''
            return aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            base = resolve(node.value)
            if not base or node.attr in shadow:
                return ''
            return base + '.' + node.attr
        return ''

    def construction(node):
        if not isinstance(node, ast.Call):
            return False
        name = resolve(node.func).split('.')[-1]
        if name == 'from_pretrained' and isinstance(node.func, ast.Attribute):
            name = resolve(node.func.value).split('.')[-1]
        if name in DEDICATED_NAMES:
            return True
        if name == 'pipeline':
            task = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == 'task'), None)
            return isinstance(task, ast.Constant) and task.value == 'audio-classification'
        return False

    instances = set()
    # Resolve assignment aliases to a fixed point without joining module files.
    for _ in range(len(list(ast.walk(tree)))):
        previous = set(instances)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                if construction(value) or isinstance(value, ast.Name) and value.id in instances:
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    instances.update(t.id for t in targets if isinstance(t, ast.Name) and t.id not in shadow)
        if instances == previous:
            break
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = resolve(node.func).split('.')[-1]
        if name in GENERIC_NAMES:
            if isinstance(node.func, ast.Attribute) or isinstance(node.func, ast.Name) and node.func.id in aliases:
                return True
        target = node.func
        if isinstance(target, ast.Attribute) and target.attr in ('forward', '__call__'):
            target = target.value
        if construction(target) or isinstance(target, ast.Name) and target.id in instances:
            return True
    return False


EXCLUDED = {'.git', '__pycache__', '.venv', 'venv', 'env', '.env', 'virtualenv', '.tox', '.nox'}


def scan(repo, ignore=(), verbose=False):
    repo = Path(repo)
    if not repo.is_dir():
        raise OSError('Repository is not a directory: ' + str(repo))
    positives, negatives, fixture_hits = [], [], []
    has_evidence = False
    for path in sorted(repo.rglob('*')):
        rel = path.relative_to(repo)
        if any(part in EXCLUDED for part in rel.parts) or any((repo.joinpath(*rel.parts[:i]) / 'pyvenv.cfg').exists() for i in range(1, len(rel.parts))):
            continue
        if any(rel.as_posix().startswith(prefix) for prefix in ignore):
            if verbose:
                print('skip ' + rel.as_posix(), file=sys.stderr)
            continue
        if not path.is_file():
            continue
        doc = rel.as_posix() == 'README.md' or rel.parts[0] == 'docs' and path.suffix == '.md'
        fixture = 'tests' in rel.parts and path.suffix in ('.md', '.py', '.txt', '.rst')
        if not (doc or fixture or path.suffix == '.py'):
            continue
        if verbose:
            print('scan ' + rel.as_posix(), file=sys.stderr)
        text = path.read_text(encoding='utf-8')
        if doc or fixture:
            pos, neg = claims(text)
            if doc:
                positives.extend(pos)
                negatives.extend(neg)
            elif fixture:
                fixture_hits.extend(pos)
        if path.suffix == '.py':
            try:
                has_evidence = evidence(text) or has_evidence
            except SyntaxError:
                if verbose:
                    print('invalid Python: ' + rel.as_posix(), file=sys.stderr)
    findings = []
    def add(rule, severity, message):
        findings.append(dict(rule=rule, severity=severity, verdict='FAIL', message=message))
    if positives and not has_evidence:
        add('documented-audio-classification-claim-false', 'high', 'Documentation asserts the checked feature without source evidence.')
    elif fixture_hits and not has_evidence:
        add('documented-audio-classification-claim-false', 'medium', 'Only test fixtures assert the checked feature without source evidence.')
    if negatives and has_evidence:
        add('documented-no-audio-classification-claim-false', 'high', 'Documentation denies the checked feature despite source evidence.')
    return findings


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, self.prog + ': error: ' + message + '\n')


def main(argv=None):
    parser = Parser(prog='audio-classification-claim-audit')
    parser.add_argument('--version', action='version', version=__version__)
    sub = parser.add_subparsers(dest='command', required=True, parser_class=Parser)
    audit = sub.add_parser('audit')
    audit.add_argument('repo', nargs='?', default='.')
    audit.add_argument('--json', action='store_true')
    audit.add_argument('--verbose', action='store_true')
    audit.add_argument('--ignore', action='append', default=[], metavar='PREFIX')
    audit.add_argument('--fail-on', choices=('high', 'medium'), default='high')
    args = parser.parse_args(argv)
    try:
        if args.verbose:
            print('Scope: README.md, docs/**/*.md, tests fixtures, and Python sources under ' + str(Path(args.repo).resolve()), file=sys.stderr)
        findings = scan(args.repo, args.ignore, args.verbose)
    except (OSError, UnicodeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(findings, indent=2))
    elif findings:
        for finding in findings:
            print('{severity}: {rule}: {message}'.format(**finding))
    else:
        print('PASS')
    return 2 if any(f['severity'] == 'high' or args.fail_on == 'medium' for f in findings) else 0
