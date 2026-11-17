"""Exercise the Sonar action's preparation against isolated consumer checkouts."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


PREPARE = Path(__file__).resolve().parents[1] / "actions/sonar-analysis/prepare.sh"


class SonarPreparationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "coverage/gcov").mkdir(parents=True)
        (self.root / "coverage/compile_commands.json").write_text("[]\n")
        (self.root / "coverage/gcov/example.cpp.gcov").write_text("coverage fixture\n")
        (self.root / "src").mkdir()
        (self.root / "tests").mkdir()
        (self.root / "runner").mkdir()

    def prepare(self, **overrides):
        env = {
            **os.environ,
            "TEST_BUILD_DIRECTORY": "coverage",
            "SONAR_ORG_INPUT": "",
            "GITHUB_REPOSITORY": "Group-Devices/example",
            "GITHUB_REPOSITORY_OWNER": "Group-Devices",
            "GITHUB_OUTPUT": str(self.root / "outputs"),
            "GITHUB_STEP_SUMMARY": str(self.root / "summary"),
            "RUNNER_TEMP": str(self.root / "runner"),
            **overrides,
        }
        subprocess.run(["bash", str(PREPARE)], cwd=self.root, env=env, check=True,
                       capture_output=True, text=True)
        return dict(line.split("=", 1) for line in
                    (self.root / "outputs").read_text().splitlines())

    def test_native_test_build_keeps_coverage_and_uses_default_scope(self):
        outputs = self.prepare()
        self.assertEqual(Path(outputs["settings"]).read_text(),
                         "sonar.sources=src\nsonar.tests=tests\n")
        self.assertEqual(outputs["database"], "coverage/compile_commands.json")
        self.assertEqual(outputs["coverage-argument"],
                         "--define sonar.cfamily.gcov.reportsPath=coverage/gcov")
        self.assertEqual(outputs["project-key"], "group-devices_example")
        self.assertEqual(outputs["project-name"], "example")
        self.assertFalse((self.root / "sonar-project.properties").exists())

    def test_repository_properties_override_defaults_without_rewriting_syntax(self):
        (self.root / "src").rmdir()
        custom = ("# Library layout\nsonar.sources=lib,\\\n  include\n"
                  "sonar.tests=unit-tests\nsonar.exclusions=lib/generated/**")
        path = self.root / "sonar-project.properties"
        path.write_text(custom)
        outputs = self.prepare()
        self.assertTrue(Path(outputs["settings"]).read_text().endswith(custom + "\n"))
        self.assertEqual(path.read_text(), custom)

    def test_missing_test_directory_does_not_create_an_invalid_test_scope(self):
        (self.root / "tests").rmdir()
        outputs = self.prepare()
        self.assertEqual(Path(outputs["settings"]).read_text(), "sonar.sources=src\n")

    def test_missing_gcov_keeps_static_analysis_without_coverage(self):
        (self.root / "coverage/gcov/example.cpp.gcov").unlink()
        outputs = self.prepare()
        self.assertNotIn("coverage-argument", outputs)
        self.assertIn("without coverage import", (self.root / "summary").read_text())

    def test_static_analysis_build_uses_the_same_scope_configuration(self):
        tools = self.root / "bin"
        tools.mkdir()
        conan = tools / "conan"
        conan.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > conan-arguments\n')
        conan.chmod(0o755)
        outputs = self.prepare(TEST_BUILD_DIRECTORY="", CONAN_CONTEXT_CONF_ARGS="",
                               PATH=str(tools) + os.pathsep + os.environ["PATH"])
        self.assertIn("--build=never", (self.root / "conan-arguments").read_text())
        self.assertEqual(Path(outputs["settings"]).read_text(),
                         "sonar.sources=src\nsonar.tests=tests\n")
        self.assertNotIn("coverage-argument", outputs)


if __name__ == "__main__":
    unittest.main()
