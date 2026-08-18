#!/usr/bin/env python3
"""Find Django template comments and optionally remove them."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, TextIO


DEFAULT_EXCLUDED_DIRS = {
    '.git',
    '.mypy_cache',
    '.pytest_cache',
    '.venv',
    '.xpose',
    '__pycache__',
    'build',
    'dist',
    'node_modules',
    'static_root',
    'staticfiles',
    'venv',
}

VALID_COMMENT_PATTERN = re.compile(
    r'{%\s*comment(?:\s+.*?)?\s*%}.*?{%\s*endcomment\s*%}|{#.*?#}',
    re.DOTALL,
)
WRONG_SHORT_CLOSER_PATTERN = re.compile(r'{#[^\r\n]*?%}')
SHORT_OPENER_PATTERN = re.compile(r'{#')


@dataclass(frozen=True)
class TemplateComment:
    start: int
    end: int
    start_line: int
    end_line: int
    kind: str
    text: str

    @property
    def malformed(self) -> bool:
        return self.kind.startswith('malformed-')


@dataclass(frozen=True)
class ScannedTemplate:
    path: Path
    source: str
    comments: tuple[TemplateComment, ...]


def _build_comment(source: str, start: int, end: int, kind: str) -> TemplateComment:
    start_line = source.count('\n', 0, start) + 1
    end_line = source.count('\n', 0, max(start, end - 1)) + 1
    return TemplateComment(start, end, start_line, end_line, kind, source[start:end])


def _covered(position: int, comments: Iterable[TemplateComment]) -> bool:
    return any(comment.start <= position < comment.end for comment in comments)


def find_comments(source: str) -> list[TemplateComment]:
    comments = []
    for match in VALID_COMMENT_PATTERN.finditer(source):
        kind = 'short' if match.group(0).startswith('{#') else 'block'
        comments.append(_build_comment(source, match.start(), match.end(), kind))

    for match in WRONG_SHORT_CLOSER_PATTERN.finditer(source):
        if not _covered(match.start(), comments):
            comments.append(_build_comment(
                source,
                match.start(),
                match.end(),
                'malformed-short-wrong-closer',
            ))

    for match in SHORT_OPENER_PATTERN.finditer(source):
        if _covered(match.start(), comments):
            continue
        line_break = source.find('\n', match.start())
        end = len(source) if line_break == -1 else line_break
        comments.append(_build_comment(
            source,
            match.start(),
            end,
            'malformed-short-unclosed',
        ))

    return sorted(comments, key=lambda comment: comment.start)


def _removal_span(source: str, comment: TemplateComment) -> tuple[int, int]:
    line_start = source.rfind('\n', 0, comment.start) + 1
    line_break = source.find('\n', comment.end)
    line_end = len(source) if line_break == -1 else line_break
    if not source[line_start:comment.start].strip() and not source[comment.end:line_end].strip():
        return line_start, len(source) if line_break == -1 else line_break + 1
    return comment.start, comment.end


def remove_comments(source: str, comments: Iterable[TemplateComment]) -> str:
    cleaned = source
    spans = (_removal_span(source, comment) for comment in comments)
    for start, end in sorted(spans, reverse=True):
        cleaned = cleaned[:start] + cleaned[end:]
    return cleaned


def collect_template_files(
    paths: Iterable[Path | str],
    excluded_dirs: Iterable[str] = DEFAULT_EXCLUDED_DIRS,
) -> tuple[list[Path], list[str]]:
    excluded = set(excluded_dirs)
    collected: dict[Path, Path] = {}
    errors = []

    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            errors.append(f'Path does not exist: {path}')
            continue
        if path.is_file():
            collected[path.resolve()] = path
            continue
        if not path.is_dir():
            errors.append(f'Path is not a regular file or directory: {path}')
            continue

        try:
            candidates = path.rglob('*.html')
            for candidate in candidates:
                relative_parts = candidate.relative_to(path).parts[:-1]
                if any(part in excluded for part in relative_parts):
                    continue
                if candidate.is_file():
                    collected[candidate.resolve()] = candidate
        except OSError as error:
            errors.append(f'Could not scan {path}: {error}')

    return sorted(collected.values(), key=lambda item: str(item)), errors


def _read_source(path: Path) -> str:
    with path.open('r', encoding='utf-8', newline='') as handle:
        return handle.read()


def _write_source(path: Path, source: str) -> None:
    with path.open('w', encoding='utf-8', newline='') as handle:
        handle.write(source)


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path.resolve())


def _print_comment_report(scanned: Iterable[ScannedTemplate], stdout: TextIO) -> None:
    for template in scanned:
        for comment in template.comments:
            line_label = (
                str(comment.start_line)
                if comment.start_line == comment.end_line
                else f'{comment.start_line}-{comment.end_line}'
            )
            print(f'{_display_path(template.path)}:{line_label} [{comment.kind}]', file=stdout)
            for line in comment.text.strip().splitlines():
                print(f'    {line}', file=stdout)


def _summary(action: str, comment_count: int, file_count: int) -> str:
    comment_label = 'comment' if comment_count == 1 else 'comments'
    file_label = 'file' if file_count == 1 else 'files'
    preposition = 'from' if action == 'Removed' else 'in'
    return f'{action} {comment_count} {comment_label} {preposition} {file_count} {file_label}.'


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='List malformed Django short comments that can leak into HTML and optionally remove them.',
    )
    parser.add_argument(
        'paths',
        nargs='*',
        default=['.'],
        help='Files or directories to scan (default: current directory; directories scan *.html recursively).',
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        '--check',
        action='store_true',
        help='Report comments without prompting; exits 1 when comments are found.',
    )
    mode.add_argument(
        '--remove',
        action='store_true',
        help='Remove every reported comment without prompting.',
    )
    parser.add_argument(
        '--exclude',
        action='append',
        default=[],
        metavar='DIR_NAME',
        help='Skip an additional directory name while scanning recursively (repeatable).',
    )
    parser.add_argument(
        '--include-valid',
        action='store_true',
        help='Also list correctly closed {# #} and {%% comment %%} comments.',
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    args = build_parser().parse_args(argv)
    excluded_dirs = DEFAULT_EXCLUDED_DIRS | set(args.exclude)
    files, errors = collect_template_files(args.paths, excluded_dirs)

    scanned = []
    for path in files:
        try:
            source = _read_source(path)
        except (OSError, UnicodeError) as error:
            errors.append(f'Could not read {path}: {error}')
            continue
        found_comments = find_comments(source)
        comments = tuple(
            found_comments
            if args.include_valid
            else (comment for comment in found_comments if comment.malformed)
        )
        if comments:
            scanned.append(ScannedTemplate(path, source, comments))

    if errors:
        for error in errors:
            print(error, file=stderr)
        return 2

    if not scanned:
        qualifier = 'Django template' if args.include_valid else 'malformed Django template'
        print(f'No {qualifier} comments found in {len(files)} files.', file=stdout)
        return 0

    _print_comment_report(scanned, stdout)
    comment_count = sum(len(template.comments) for template in scanned)
    print('', file=stdout)
    print(_summary('Found', comment_count, len(scanned)), file=stdout)

    if args.check:
        print('No files changed. Re-run with --remove to delete them.', file=stdout)
        return 1

    should_remove = args.remove
    if not should_remove:
        if not stdin.isatty():
            print('No files changed. Re-run with --remove to delete them.', file=stdout)
            return 1
        print('Remove all listed comments? [y/N] ', end='', file=stdout, flush=True)
        should_remove = stdin.readline().strip().casefold() in {'y', 'yes'}

    if not should_remove:
        print('No files changed.', file=stdout)
        return 1

    for template in scanned:
        try:
            current_source = _read_source(template.path)
        except (OSError, UnicodeError) as error:
            print(f'Could not re-read {template.path}: {error}', file=stderr)
            return 2
        if current_source != template.source:
            print(f'Refusing to overwrite a file changed during review: {template.path}', file=stderr)
            return 2

    try:
        for template in scanned:
            _write_source(
                template.path,
                remove_comments(template.source, template.comments),
            )
    except OSError as error:
        print(f'Could not remove comments: {error}', file=stderr)
        return 2

    print(_summary('Removed', comment_count, len(scanned)), file=stdout)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
