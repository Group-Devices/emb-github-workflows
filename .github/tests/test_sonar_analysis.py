"""Test analysis preparation locally; no GitHub secrets or Conan downloads required."""

from pathlib import Path
import json
import os
import subprocess
import tempfile
import textwrap
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "actions/sonar-analysis/prepare.sh"


class SonarAnalysisTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sonar checks ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.checkout = self.root / "checkout"
        self.checkout.mkdir()
        (self.checkout / "source.cpp").write_text("int value() { return 1; }\n")
        self.tools = self.root / "bin"
        self.tools.mkdir()
        self.output = self.root / "output"
        self.summary = self.root / "summary"
        self.environment = dict(os.environ, GITHUB_WORKSPACE=str(self.checkout),
            GITHUB_REPOSITORY="Example/Package", GITHUB_REPOSITORY_OWNER="Example",
            RUNNER_TEMP=str(self.root), GITHUB_OUTPUT=str(self.output),
            GITHUB_STEP_SUMMARY=str(self.summary), SONAR_ORG_INPUT="",
            CONAN_CONTEXT_CONF_ARGS="", TEST_BUILD_DIRECTORY="coverage",
            PATH=str(self.tools) + os.pathsep + os.environ["PATH"])
        # Model only Conan's build output; preparation and validation run unmodified.
        conan = self.tools / "conan"
        conan.write_text("""#!/usr/bin/env python3
import json, os, pathlib, sys
pathlib.Path('conan-arguments.json').write_text(json.dumps(sys.argv[1:]))
folder = pathlib.Path(sys.argv[sys.argv.index('--output-folder') + 1])
source = str(pathlib.Path('source.cpp').resolve())
(folder / 'compile_commands.json').write_text(json.dumps([
    {'file': source, 'directory': os.getcwd(), 'command': 'c++ -c ' + source}]))
""")
        conan.chmod(0o755)

    def database(self, directory="coverage", entries=None):
        directory = self.checkout / directory
        directory.mkdir(parents=True, exist_ok=True)
        if entries is None:
            entries = [{"file": "source.cpp", "directory": str(self.checkout), "command": "c++ -c source.cpp"}]
        (directory / "compile_commands.json").write_text(json.dumps(entries))

    def run_prepare(self, expected=0):
        result = subprocess.run(["bash", str(SCRIPT)], cwd=self.checkout,
                                env=self.environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def test_script_detection_does_not_require_a_dummy_file(self):
        # Execute the exact detection shell from the workflow, without a runner.
        workflow = SCRIPT.parents[2] / "workflows/conan-library.yml"
        source = workflow.read_text().split("      - name: Detect unit tests\n", 1)[1]
        source = source.split("        run: |\n", 1)[1].split("      - name:", 1)[0]
        command = textwrap.dedent(source)
        subprocess.run(["bash", "-e", "-c", command], cwd=self.checkout,
                       env=self.environment, check=True, capture_output=True)
        self.assertIn("no test.sh", self.summary.read_text())
        self.assertFalse(self.output.exists())
        # Executability is not required: the workflow invokes bash explicitly.
        (self.checkout / "test.sh").write_text("exit 0\n")
        subprocess.run(["bash", "-e", "-c", command], cwd=self.checkout,
                       env=self.environment, check=True, capture_output=True)
        self.assertEqual(self.output.read_text(), "enabled=true\n")

    def test_reuses_test_build_and_passes_coverage_without_conan(self):
        self.database()
        reports = self.checkout / "coverage/gcov"
        reports.mkdir()
        (reports / "example.gcov").write_text("        -:    0:Source:source.cpp\n        1:    1:int value() { return 1; }\n")
        self.run_prepare()
        self.assertFalse((self.checkout / "conan-arguments.json").exists())
        self.assertIn('sonar.cfamily.gcov.reportsPath="coverage/gcov"', self.output.read_text())
        self.assertIn("project-key=example_Package", self.output.read_text())
        self.assertIn("no additional compilation", self.summary.read_text())

    def test_no_tests_builds_analysis_only_without_dependency_builds(self):
        self.environment["TEST_BUILD_DIRECTORY"] = ""
        self.run_prepare()
        arguments = json.loads((self.checkout / "conan-arguments.json").read_text())
        self.assertIn("--build=never", arguments)
        self.assertIn("tools.build:skip_test=True", arguments)
        self.assertIn("build_type=Release", arguments)
        self.assertNotIn("coverage-argument", self.output.read_text())
        self.assertIn("without coverage import", self.summary.read_text())

    def test_analysis_build_failure_is_not_hidden_by_tee(self):
        self.environment["TEST_BUILD_DIRECTORY"] = ""
        (self.tools / "conan").write_text("#!/bin/sh\nexit 42\n")
        self.run_prepare(expected=42)
        self.assertFalse((self.checkout / "compile_commands.json").exists())

    def test_old_test_build_without_database_falls_back(self):
        (self.checkout / "coverage").mkdir()
        self.run_prepare()
        self.assertTrue((self.checkout / "conan-arguments.json").exists())

    def test_test_database_without_reports_remains_usable(self):
        self.database()
        self.run_prepare()
        self.assertFalse((self.checkout / "conan-arguments.json").exists())
        self.assertNotIn("coverage-argument", self.output.read_text())

    def test_empty_database_is_rejected(self):
        self.database(entries=[])
        self.run_prepare(expected=1)
        self.assertFalse((self.checkout / "compile_commands.json").exists())

    def test_ambiguous_database_is_rejected(self):
        self.database()
        self.database("coverage/other")
        self.run_prepare(expected=1)

    def test_cached_sources_outside_checkout_are_rejected(self):
        outside = self.root / "cached.cpp"
        outside.write_text("int cached;\n")
        self.database(entries=[{"file": str(outside), "directory": str(self.root), "command": "c++"}])
        self.run_prepare(expected=1)

    def test_explicit_organization_is_used(self):
        self.database()
        self.environment["SONAR_ORG_INPUT"] = "Custom-Organization"
        self.run_prepare()
        self.assertIn("organization=custom-organization", self.output.read_text())


if __name__ == "__main__":
    unittest.main()
