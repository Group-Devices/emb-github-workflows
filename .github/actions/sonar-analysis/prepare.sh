#!/usr/bin/env bash
set -euo pipefail

# test.sh normally uses coverage/. An empty directory input means tests did not run.
databases=()
if [ -n "${TEST_BUILD_DIRECTORY}" ] && [ -d "${TEST_BUILD_DIRECTORY}" ]; then
  mapfile -d '' databases < <(find "${TEST_BUILD_DIRECTORY}" -type f -name compile_commands.json -print0)
fi
if [ "${#databases[@]}" -eq 0 ]; then
  build_folder=$(mktemp -d "${RUNNER_TEMP}/sonar-build.XXXXXX")
  # Build checkout sources, never a source copy from Conan's package cache.
  # shellcheck disable=SC2086 # The context supplies a sequence of -c options.
  conan build . -pr:h default $CONAN_CONTEXT_CONF_ARGS \
    -s:h build_type=Release -c:h tools.build:skip_test=True --build=never \
    -c:h='tools.cmake.cmaketoolchain:extra_variables={"CMAKE_EXPORT_COMPILE_COMMANDS": "ON"}' \
    --output-folder "${build_folder}" 2>&1 | tee sonar_build.log
  mapfile -d '' databases < <(find "${build_folder}" -type f -name compile_commands.json -print0)
  echo "Sonar uses a static-analysis build (no reusable test compilation database)." >> "$GITHUB_STEP_SUMMARY"
else
  echo "Sonar reuses the test build; no additional compilation." >> "$GITHUB_STEP_SUMMARY"
fi
if [ "${#databases[@]}" -ne 1 ]; then
  echo "Expected one compilation database, found ${#databases[@]}" >&2
  exit 1
fi
if ! jq -e 'type == "array" and length > 0' "${databases[0]}" >/dev/null; then
  echo "Sonar compilation database must be a non-empty JSON array" >&2
  exit 1
fi
source_paths=$(jq -r '.[] | if (.file | startswith("/")) then .file else .directory + "/" + .file end' "${databases[0]}")
checkout_source_found=false
while IFS= read -r source_path; do
  if [ -f "$source_path" ] && [[ "$(realpath "$source_path")" == "${GITHUB_WORKSPACE}/"* ]]; then
    checkout_source_found=true
    break
  fi
done <<< "$source_paths"
if [ "$checkout_source_found" != true ]; then
  echo "Compilation database does not reference existing checkout sources" >&2
  exit 1
fi
cp "${databases[0]}" ./compile_commands.json

# Reports remain in this job's checkout; no coverage artifact transfer is needed.
if [ -n "${TEST_BUILD_DIRECTORY}" ] && [ -d "${TEST_BUILD_DIRECTORY}/gcov" ] &&
   [ -n "$(find "${TEST_BUILD_DIRECTORY}/gcov" -maxdepth 1 -name '*.gcov' -type f -print -quit)" ]; then
  printf 'coverage-argument=--define sonar.cfamily.gcov.reportsPath="%s/gcov"\n' "$TEST_BUILD_DIRECTORY" >> "$GITHUB_OUTPUT"
  echo "Sonar GCOV coverage: ${TEST_BUILD_DIRECTORY}/gcov." >> "$GITHUB_STEP_SUMMARY"
else
  if [ -n "${TEST_BUILD_DIRECTORY}" ]; then
    echo "::warning::Test build has no GCOV reports; coverage will not be imported"
  else
    echo "::notice::No test build; running static analysis without coverage import"
  fi
  echo "Sonar runs static analysis without coverage import." >> "$GITHUB_STEP_SUMMARY"
fi
organization=${SONAR_ORG_INPUT:-$GITHUB_REPOSITORY_OWNER}
organization=$(printf '%s' "$organization" | tr '[:upper:]' '[:lower:]')
printf 'organization=%s\nproject-key=%s_%s\n' "$organization" "$organization" "${GITHUB_REPOSITORY#*/}" >> "$GITHUB_OUTPUT"
