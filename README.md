# Embedded Github Workflows

The Github workflows used by Embedded projects.

## Github configuration

This Github project must be accessible from others repositories of Kuba enterprise.

See https://github.com/Group-Devices/emb-github-workflows/settings/actions
where **Access** must be **Accessible from repositories in the 'KUBA' enterprise**

## Layered Build

The Conan pipeline is layered so each stage validates a different integration level.

### Package build

The package workflow builds one repository in isolation and publishes its Conan package.

It also emits the build state reused by downstream stages:
- `source_build_context.package_context`
- lockfile
- optional Conan cache

This stage answers:
- can this package be built and published on its own

### Collector build

The collector workflow is the bundle consistency step.

When a package changes, the collector is rebuilt while reusing the build state coming from that exact package build. This lets the collector rebuild against the newly built package instead of only relying on what is already published in Conan repositories.

This stage answers:
- does the collector still build correctly with the updated package
- is the dependency graph still coherent at bundle level

### Context build

The context workflow is the final delivery step. It starts from the collector build state and produces the final bundle outputs:
- Conan install and deploy
- APT delivery
- generated documentation site

This stage answers:
- can the full delivery be produced from the updated collector state
- are package delivery, APT publication and docs generation still coherent together

### Why `source_build_context` exists

The chained `source_build_context` keeps the provenance across:
- package build
- collector build
- context build

That lets each stage restore the lockfile and optional cache from the previous relevant stage and makes the final delivery traceable back to the package build that triggered it.

### Conan context configuration

Conan configuration is not hardcoded in the reusable workflows. It comes from the Conan context package selected by the bundle.

The selection point is the `bundle` field in the `conanfile.py` of package and collector repositories. That bundle resolves to the Conan context package, which provides the shared build configuration used by the workflows.

That context provides in particular:
- Conan remotes
- Conan profiles
- shared build options such as cache activation

So the flow is:
- package or collector recipe declares its bundle
- the bundle resolves the Conan context package
- the reusable workflow reads that context
- Conan is configured from that context before build, collector rebuild, or delivery

This keeps repository workflows generic while centralizing environment-specific Conan setup in the context package used by the bundle.

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
