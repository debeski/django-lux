import importlib.util
import io
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase


SCRIPT_PATH = Path(__file__).resolve().parents[2] / 'scripts' / 'find_template_comments.py'


def load_script():
    spec = importlib.util.spec_from_file_location('find_template_comments', SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TTYInput(io.StringIO):
    def isatty(self):
        return True


class TemplateCommentFinderTests(TestCase):
    def test_help_renders_template_delimiters(self):
        finder = load_script()

        help_text = finder.build_parser().format_help()

        self.assertIn('{# #}', help_text)
        self.assertIn('{% comment %}', help_text)

    def test_finds_both_django_comment_styles_with_line_numbers(self):
        finder = load_script()
        source = (
            '<main>{# inline note #}</main>\n'
            '{% comment "context" %}\n'
            'block note\n'
            '{% endcomment %}\n'
        )

        comments = finder.find_comments(source)

        self.assertEqual([comment.kind for comment in comments], ['short', 'block'])
        self.assertEqual((comments[0].start_line, comments[0].end_line), (1, 1))
        self.assertEqual((comments[1].start_line, comments[1].end_line), (2, 4))

    def test_finds_leaking_wrong_closers_and_unclosed_short_comments(self):
        finder = load_script()
        source = (
            '{# Usage: {% include "safe.html" %} #}\n'
            '<p>{# leaking comment %}kept</p>\n'
            '{# unclosed comment\n'
        )

        comments = finder.find_comments(source)

        self.assertEqual(
            [comment.kind for comment in comments],
            ['short', 'malformed-short-wrong-closer', 'malformed-short-unclosed'],
        )
        self.assertEqual(comments[1].text, '{# leaking comment %}')
        self.assertEqual(comments[2].text, '{# unclosed comment')

    def test_removal_preserves_markup_around_inline_comments(self):
        finder = load_script()
        source = (
            '{# standalone #}\n'
            '<p>before {# middle #} after</p>\n'
            '{% comment %}\nblock note\n{% endcomment %}\n'
            '<footer>kept</footer>\n'
        )

        cleaned = finder.remove_comments(source, finder.find_comments(source))

        self.assertEqual(
            cleaned,
            '<p>before  after</p>\n<footer>kept</footer>\n',
        )

    def test_interactive_run_lists_comments_and_removes_after_confirmation(self):
        finder = load_script()
        with TemporaryDirectory() as temporary_directory:
            template = Path(temporary_directory) / 'example.html'
            template.write_text('<div>kept</div>\n{# remove me %}\n', encoding='utf-8')
            output = io.StringIO()

            status = finder.main(
                [str(template)],
                stdin=TTYInput('y\n'),
                stdout=output,
                stderr=io.StringIO(),
            )

            self.assertEqual(status, 0)
            self.assertIn('example.html:2 [malformed-short-wrong-closer]', output.getvalue())
            self.assertIn('{# remove me %}', output.getvalue())
            self.assertIn('Removed 1 comment from 1 file.', output.getvalue())
            self.assertEqual(template.read_text(encoding='utf-8'), '<div>kept</div>\n')

    def test_check_mode_reports_without_writing(self):
        finder = load_script()
        with TemporaryDirectory() as temporary_directory:
            template = Path(temporary_directory) / 'example.html'
            original = '{# keep during check %}\n'
            template.write_text(original, encoding='utf-8')
            output = io.StringIO()

            status = finder.main(
                ['--check', str(template)],
                stdin=io.StringIO(),
                stdout=output,
                stderr=io.StringIO(),
            )

            self.assertEqual(status, 1)
            self.assertIn('Found 1 comment in 1 file.', output.getvalue())
            self.assertIn('Re-run with --remove', output.getvalue())
            self.assertEqual(template.read_text(encoding='utf-8'), original)

    def test_valid_comments_are_optional_in_cli_reports(self):
        finder = load_script()
        with TemporaryDirectory() as temporary_directory:
            template = Path(temporary_directory) / 'example.html'
            template.write_text('{# valid and server-stripped #}\n', encoding='utf-8')

            default_status = finder.main(
                ['--check', str(template)],
                stdin=io.StringIO(),
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )
            inclusive_status = finder.main(
                ['--check', '--include-valid', str(template)],
                stdin=io.StringIO(),
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )

            self.assertEqual(default_status, 0)
            self.assertEqual(inclusive_status, 1)

    def test_directory_scan_skips_archives_and_virtual_environments(self):
        finder = load_script()
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            visible = root / 'templates' / 'visible.html'
            archived = root / '.xpose' / 'archived.html'
            dependency = root / '.venv' / 'dependency.html'
            for path in (visible, archived, dependency):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('{# note #}\n', encoding='utf-8')

            files, errors = finder.collect_template_files([root])

            self.assertEqual(errors, [])
            self.assertEqual(files, [visible])
