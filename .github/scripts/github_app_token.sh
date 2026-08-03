#!/usr/bin/env bash

# Encode stdin as base64url without padding.
github_app_b64url() {
  openssl base64 -A | tr '+/' '-_' | tr -d '='
}

# Register sensitive values for masking in GitHub Actions logs.
github_actions_add_mask() {
  local value="$1"

  if [ -n "${value}" ] && [ "${GITHUB_ACTIONS:-}" = "true" ]; then
    # Use stderr to avoid interfering with callers that capture stdout.
    printf '%s\n' "::add-mask::${value}" >&2
  fi
}

# Build a short-lived GitHub App JWT.
github_app_build_jwt() {
  local app_id="$1"
  local app_private_key="$2"

  local now iat exp header payload unsigned key_file signature
  now=$(date +%s)
  iat=$((now - 60))
  exp=$((now + 540))
  header='{"alg":"RS256","typ":"JWT"}'
  payload="{\"iat\":${iat},\"exp\":${exp},\"iss\":\"${app_id}\"}"

  unsigned="$(printf '%s' "${header}" | github_app_b64url).$(printf '%s' "${payload}" | github_app_b64url)"
  key_file=$(mktemp)
  printf '%s\n' "${app_private_key}" > "${key_file}"
  signature=$(printf '%s' "${unsigned}" | openssl dgst -binary -sha256 -sign "${key_file}" | github_app_b64url)
  rm -f "${key_file}"

  printf '%s' "${unsigned}.${signature}"
}

# Resolve installation id for an organization or user owner.
github_app_get_installation_id() {
  local owner="$1"
  local jwt="$2"
  local api_url="${3:-${GITHUB_API_URL:-https://api.github.com}}"

  local installation_id
  installation_id=$(curl --fail -sS \
    -H "Authorization: Bearer ${jwt}" \
    -H "Accept: application/vnd.github+json" \
    "${api_url}/orgs/${owner}/installation" | jq -r '.id // empty')

  if [ -z "${installation_id}" ]; then
    installation_id=$(curl --fail -sS \
      -H "Authorization: Bearer ${jwt}" \
      -H "Accept: application/vnd.github+json" \
      "${api_url}/users/${owner}/installation" | jq -r '.id // empty')
  fi

  printf '%s' "${installation_id}"
}

# Generate an installation token for a given owner.
github_app_token_for_owner() {
  local owner="$1"
  local app_id="$2"
  local app_private_key="$3"
  local api_url="${4:-${GITHUB_API_URL:-https://api.github.com}}"

  if [ -z "${owner}" ] || [ -z "${app_id}" ] || [ -z "${app_private_key}" ]; then
    echo "Not able to create a GitHub App token: owner, app_id and app_private_key are required" >&2
    return 1
  fi

  local jwt installation_id token
  jwt=$(github_app_build_jwt "${app_id}" "${app_private_key}")
  installation_id=$(github_app_get_installation_id "${owner}" "${jwt}" "${api_url}")

  if [ -z "${installation_id}" ]; then
    echo "No GitHub App installation found for owner ${owner}, please contact your administrator." >&2
    return 1
  fi

  token=$(curl --fail -sS -X POST \
    -H "Authorization: Bearer ${jwt}" \
    -H "Accept: application/vnd.github+json" \
    "${api_url}/app/installations/${installation_id}/access_tokens" | jq -r '.token')

  if [ -z "${token}" ] || [ "${token}" = "null" ]; then
    echo "Failed to generate GitHub App token for owner ${owner}, please contact your administrator." >&2
    return 1
  fi

  github_actions_add_mask "${token}"
  printf '%s' "${token}"
}

# Resolve GitHub App credentials from variables/secrets payloads and scope.
# App ID comes from variables only.
# Precedence for private key:
# - scope-specific secret (<PREFIX>_PRIVATE_KEY_<SCOPE>)
# - default secret (<PREFIX>_PRIVATE_KEY)
#
# Prefix defaults to GIT_GITHUB_APP and can be overridden.
# Variable names:
# - <PREFIX>_ID
# - <PREFIX>_ID_<SCOPE>
# Secret names:
# - <PREFIX>_PRIVATE_KEY
# - <PREFIX>_PRIVATE_KEY_<SCOPE>
# Prints two lines to stdout: app_id then app_private_key.
github_app_resolve_credentials_from_payloads() {
  local json_variables="$1"
  local json_secrets="$2"
  local credential_scope="${3:-default}"
  local credential_prefix="${4:-GIT_GITHUB_APP}"

  local scope_upper prefix_upper app_id app_private_key
  scope_upper=$(echo "${credential_scope}" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
  prefix_upper=$(echo "${credential_prefix}" | tr '[:lower:]' '[:upper:]' | tr '-' '_')

  if [ "${credential_scope}" = "default" ]; then
    app_id=$(echo "${json_variables}" | jq -r ".${prefix_upper}_ID // empty")
    app_private_key=$(echo "${json_secrets}" | jq -r ".${prefix_upper}_PRIVATE_KEY // empty")
  else
    app_id=$(echo "${json_variables}" | jq -r ".${prefix_upper}_ID_${scope_upper} // empty")
    [ -z "${app_id}" ] && app_id=$(echo "${json_variables}" | jq -r ".${prefix_upper}_ID // empty")

    app_private_key=$(echo "${json_secrets}" | jq -r ".${prefix_upper}_PRIVATE_KEY_${scope_upper} // empty")
    [ -z "${app_private_key}" ] && app_private_key=$(echo "${json_secrets}" | jq -r ".${prefix_upper}_PRIVATE_KEY // empty")
  fi

  if [ -z "${app_id}" ] || [ -z "${app_private_key}" ]; then
    if [ "${credential_scope}" = "default" ]; then
      echo "Missing GitHub App credentials. Ask your administrator to configure variable ${prefix_upper}_ID and secret ${prefix_upper}_PRIVATE_KEY." >&2
    else
      echo "Missing scoped GitHub App credentials for '${credential_scope}'. Ask your administrator to configure variable ${prefix_upper}_ID_${scope_upper} and secret ${prefix_upper}_PRIVATE_KEY_${scope_upper}, or default ${prefix_upper}_ID/${prefix_upper}_PRIVATE_KEY." >&2
    fi
    return 1
  fi

  printf '%s\n%s\n' "${app_id}" "${app_private_key}"
}

# Generate an installation token from variables+secrets payloads using a credential scope.
github_app_token_for_owner_from_payloads() {
  local owner="$1"
  local json_variables="$2"
  local json_secrets="$3"
  local credential_scope="${4:-default}"
  local credential_prefix="${5:-GIT_GITHUB_APP}"
  local api_url="${6:-${GITHUB_API_URL:-https://api.github.com}}"

  local resolved app_id app_private_key
  resolved=$(github_app_resolve_credentials_from_payloads "${json_variables}" "${json_secrets}" "${credential_scope}" "${credential_prefix}") || return 1

  app_id="${resolved%%$'\n'*}"
  app_private_key="${resolved#*$'\n'}"

  if [ -z "${app_id}" ] || [ -z "${app_private_key}" ] || [ "${app_private_key}" = "${resolved}" ]; then
    echo "Failed to parse GitHub App credentials from payloads" >&2
    return 1
  fi

  github_app_token_for_owner "${owner}" "${app_id}" "${app_private_key}" "${api_url}"
}
