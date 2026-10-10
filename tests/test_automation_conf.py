"""Tests for automation/automation_conf.py: reading an automation folder's settings.

Plain unittest, so the Linux check can run it without pytest.
"""

import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "automation"))

import automation_conf  # noqa: E402

VALID = """\
# a test folder
side=test
branch = development   # spaces and comments are fine

replace_existing=yes
wrapper=yes
"""


class Parse(unittest.TestCase):
    def test_reads_every_setting(self):
        self.assertEqual(
            automation_conf.parse(VALID),
            {"side": "test", "branch": "development", "replace_existing": "yes", "wrapper": "yes"},
        )

    def refused(self, text, fragment):
        with self.assertRaises(automation_conf.ConfError) as caught:
            automation_conf.parse(text)
        self.assertIn(fragment, str(caught.exception))

    def test_refuses_a_missing_setting(self):
        self.refused(VALID.replace("wrapper=yes\n", ""), "missing setting(s): wrapper")

    def test_refuses_an_unknown_setting(self):
        self.refused(VALID + "replace_exisitng=no\n", "unknown setting 'replace_exisitng'")

    def test_refuses_an_unknown_value(self):
        self.refused(VALID.replace("side=test", "side=staging"), "side must be test or production, not 'staging'")

    def test_refuses_a_setting_given_twice(self):
        self.refused(VALID + "side=production\n", "side is set twice")

    def test_refuses_a_line_without_an_equals_sign(self):
        self.refused(VALID + "wrapper\n", "expected key=value")

    def test_refuses_a_branch_name_that_would_need_quoting(self):
        for branch in ("-x", "feat x", "a;b", "", "$x", "`x`", "a:b", "HEAD"):
            with self.subTest(branch=branch):
                self.refused(VALID.replace("branch = development", f"branch={branch}"), "branch name")


class Render(unittest.TestCase):
    def test_round_trips_both_sides_defaults(self):
        for side, settings in automation_conf.DEFAULTS.items():
            with self.subTest(side=side):
                self.assertEqual(automation_conf.parse(automation_conf.render(settings)), settings)

    def test_production_never_replaces_and_has_no_wrapper_yet(self):
        production = automation_conf.DEFAULTS["production"]
        self.assertEqual(
            (production["side"], production["branch"], production["replace_existing"], production["wrapper"]),
            ("production", "master", "no", "no"),
        )

    def test_refuses_to_write_invalid_settings(self):
        with self.assertRaises(automation_conf.ConfError):
            automation_conf.render(dict(automation_conf.DEFAULTS["test"], branch="-x"))

    def test_refuses_a_value_that_would_read_back_differently(self):
        for branch in ("dev#x", "dev #x", " development", "development\n"):
            with self.subTest(branch=branch), self.assertRaises(automation_conf.ConfError):
                automation_conf.render(dict(automation_conf.DEFAULTS["test"], branch=branch))

    def test_a_long_branch_name_keeps_a_space_before_its_comment(self):
        text = automation_conf.render(dict(automation_conf.DEFAULTS["test"], branch="feat/automation-in-repo"))
        self.assertIn("branch=feat/automation-in-repo # ", text)


class Example(unittest.TestCase):
    def test_the_example_is_a_valid_test_folder(self):
        example = REPO_ROOT / "automation" / "automation.conf.example"
        self.assertEqual(automation_conf.read(example), automation_conf.DEFAULTS["test"])

    def test_the_example_shows_the_production_defaults(self):
        text = (REPO_ROOT / "automation" / "automation.conf.example").read_text(encoding="utf-8")
        block = text.split("sets:\n", 1)[1].replace("#   ", "")
        self.assertEqual(automation_conf.parse(block), automation_conf.DEFAULTS["production"])

    def test_render_matches_the_example_lines(self):
        example = (REPO_ROOT / "automation" / "automation.conf.example").read_text(encoding="utf-8")
        for line in automation_conf.render(automation_conf.DEFAULTS["test"]).splitlines()[2:]:
            self.assertIn(line + "\n", example)


class GetCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conf = Path(self.tmp.name) / "automation.conf"

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = automation_conf.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_prints_one_setting(self):
        self.conf.write_text(VALID, encoding="utf-8")
        self.assertEqual(self.run_main("get", str(self.conf), "branch"), (0, "development\n", ""))

    def test_an_invalid_file_exits_2_with_the_reason(self):
        self.conf.write_text(VALID.replace("side=test", "side=staging"), encoding="utf-8")
        code, out, err = self.run_main("get", str(self.conf), "branch")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("staging", err)

    def test_a_missing_file_exits_2(self):
        code, out, err = self.run_main("get", str(self.conf), "branch")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("can't read", err)

    def test_reads_a_file_saved_with_a_byte_order_mark(self):
        self.conf.write_text(VALID, encoding="utf-8-sig")
        self.assertEqual(self.run_main("get", str(self.conf), "branch"), (0, "development\n", ""))

    def test_a_file_that_is_not_utf8_exits_2(self):
        # What PowerShell 5.1's > writes
        self.conf.write_bytes(VALID.encode("utf-16"))
        code, out, err = self.run_main("get", str(self.conf), "branch")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("isn't UTF-8 text", err)

    def test_usage(self):
        self.conf.write_text(VALID, encoding="utf-8")
        for args in (("get", str(self.conf)), ("get", str(self.conf), "colour"), ("put", str(self.conf), "branch")):
            with self.subTest(args=args):
                code, out, err = self.run_main(*args)
                self.assertEqual((code, out), (2, ""))
                self.assertIn("usage:", err)

    def test_the_script_exits_as_the_launcher_expects(self):
        script = REPO_ROOT / "automation" / "automation_conf.py"
        self.conf.write_text(VALID, encoding="utf-8")
        ok = subprocess.run([sys.executable, str(script), "get", str(self.conf), "branch"], capture_output=True, text=True)
        self.assertEqual((ok.returncode, ok.stdout), (0, "development\n"))
        self.conf.write_text(VALID.replace("side=test", "side=staging"), encoding="utf-8")
        bad = subprocess.run([sys.executable, str(script), "get", str(self.conf), "branch"], capture_output=True, text=True)
        self.assertEqual((bad.returncode, bad.stdout), (2, ""))
        self.assertIn("staging", bad.stderr)


if __name__ == "__main__":
    unittest.main()
