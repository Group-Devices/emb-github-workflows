#!/usr/bin/env bash
set -euo pipefail

build_folder=${TEST_BUILD_DIRECTORY:-coverage}
if [ -n "$TEST_BUILD_DIRECTORY" ] && [ -s "$TEST_BUILD_DIRECTORY/compile_commands.json" ]; then
  echo "Sonar reuses the test build; no additional compilation." >> "$GITHUB_STEP_SUMMARY"
else
  # Build checkout sources with tests disabled; never rebuild dependencies.
  # shellcheck disable=SC2086 # The context supplies a sequence of -c options.
  conan build . -pr:h default $CONAN_CONTEXT_CONF_ARGS \
    -s:h build_type=Release -c:h tools.build:skip_test=True --build=never \
    -c:h='tools.cmake.cmaketoolchain:extra_variables={"CMAKE_EXPORT_COMPILE_COMMANDS": "ON"}' \
    --output-folder "$build_folder" 2>&1 | tee sonar_build.log
  echo "Sonar uses a static-analysis build." >> "$GITHUB_STEP_SUMMARY"
fi
if [ ! -s "$build_folder/compile_commands.json" ]; then
  echo "::error::Missing $build_folder/compile_commands.json"
  exit 1
fi
printf 'database=%s/compile_commands.json\n' "$build_folder" >> "$GITHUB_OUTPUT"

if [ -n "$TEST_BUILD_DIRECTORY" ] && compgen -G "$TEST_BUILD_DIRECTORY/gcov/*.gcov" >/dev/null; then
  printf 'coverage-argument=--define sonar.cfamily.gcov.reportsPath="%s/gcov"\n' "$TEST_BUILD_DIRECTORY" >> "$GITHUB_OUTPUT"
  echo "Sonar GCOV coverage: $TEST_BUILD_DIRECTORY/gcov." >> "$GITHUB_STEP_SUMMARY"
else
  if [ -n "$TEST_BUILD_DIRECTORY" ]; then
    echo "::warning::Test build has no GCOV reports; coverage will not be imported"
  fi
  echo "Sonar runs static analysis without coverage import." >> "$GITHUB_STEP_SUMMARY"
fi
organization=${SONAR_ORG_INPUT:-$GITHUB_REPOSITORY_OWNER}
organization=${organization,,}
printf 'organization=%s\nproject-key=%s_%s\n' "$organization" "$organization" "${GITHUB_REPOSITORY#*/}" >> "$GITHUB_OUTPUT"
