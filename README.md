# Embedded Github Workflows

The Github workflows used by Embedded projects.

## Github configuration

This Github project must be accessible from others repositories of Kuba enterprise.

See https://github.com/Group-Devices/emb-github-workflows/settings/actions
where **Access** must be **Accessible from repositories in the 'KUBA' enterprise**

## Conan Workflow Contracts

### Source build context

The reusable Conan workflows exchange build provenance through `source_build_context`.

Current chain:

```json
{
  "package_context": {
    "repo": "Group-Devices/secretary.sdk",
    "owner": "Group-Devices",
    "run_id": "123456789",
    "run_number": "42",
    "run_attempt": "1",
    "sha": "abcdef...",
    "ref": "refs/heads/main",
    "actor": "user",
    "workflow": "CI"
  },
  "collector_context": {
    "repo": "Group-Devices/collect-secretary",
    "owner": "Group-Devices",
    "run_id": "123456999",
    "run_number": "314",
    "run_attempt": "1",
    "sha": "fedcba...",
    "ref": "refs/heads/main",
    "actor": "user",
    "workflow": "rebuild"
  }
}
```

Rules:
- package builds emit `package_context`
- collector rebuilds receive that payload and forward it unchanged while appending `collector_context`
- context delivery restores lockfile/cache from `collector_context`
- if `collector_context` is absent, restore falls back to `package_context`

### Lockfile and cache artifacts

Canonical artifact names:
- lockfile: `lock-<profile>`
- Conan cache: `cache-<profile>.tgz`

These names are produced by:
- `.github/actions/upload-conan-build-state`

And restored by:
- `.github/actions/restore-conan-build-state`

### Cache activation

Conan cache restore/save is controlled by `conan-context.yml`, not by individual package workflows.

Current setting:

```yaml
build:
  use_cache: true|false
```

Behavior:
- package build reads `build.use_cache` from the Conan context
- delivery/docs build reads the same setting from the context
- pull request runs do not upload lockfile/cache artifacts

### Compatibility

The preferred contract is `source_build_context`.

Legacy compatibility is still kept for now:
- `force-build` in `conan-library.yml`
- `built_package` in collector workflows

New integrations should use only `source_build_context`.

