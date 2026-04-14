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

### Lockfile semantics

The lockfile follows the same staged flow as the build context.

Rules:
- package build creates the initial lockfile for the package build graph
- collector rebuild restores that package lockfile and rebuilds the collector against the newly built package
- context delivery restores the collector build state and reuses its lockfile for delivery and docs generation

Delivery uses:
- `-l conan-lockfile.json --lockfile-partial`

Partial mode is expected there because the collector package being installed in delivery is not part of the original package lockfile. The lockfile still constrains the dependency graph inherited from the previous stage, while allowing the collector package itself to be added at delivery time.

This means:
- package stage fixes the initial dependency graph
- collector stage validates that graph with the updated package inserted
- context stage reuses the collector graph for final APT delivery and documentation generation

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

## Consumer Migration

When moving a package, collector, or context repository to the reusable workflows on `release/v1.0`, the expected migration is:

- switch reusable workflow references from `@main` to `@release/v1.0`
- use `source_build_context` when dispatching downstream rebuilds
- keep `built_package` or `force-build` only while older consumers still require them
- declare `enabled_doxygen = True` in `conanfile.py` for packages that should publish API documentation

Typical migration by repository type:

- package repository:
  - use `conan-library.yml@release/v1.0`
  - set `enabled_doxygen = True` when Doxygen output is part of the package contract
- collector repository:
  - accept `source_build_context`
  - keep `built_package` as a temporary compatibility alias if older package workflows still send it
  - forward `source_build_context` to the reusable workflow
- context repository:
  - use `conan-context-delivery.yml@release/v1.0`
  - forward `source_build_context`
  - keep wrapper workflow permissions aligned with the reusable workflow requirements

The target state is:
- one canonical chained payload: `source_build_context`
- lockfile and optional cache restored from that chained context
- legacy aliases removed once all consumers have migrated

## Reusable Actions

The repository also contains reusable helper actions used by the workflows.

- `.github/actions/gh-auth-owner`
  - resolves the GitHub token to use for a given owner and authenticates `gh`
- `.github/actions/configure-conan`
  - configures Conan from the selected Conan context package
- `.github/actions/generate-conan-context`
  - resolves and materializes the Conan context used by package, collector, and delivery workflows
- `.github/actions/build-source-build-context`
  - creates or extends the chained `source_build_context` payload
- `.github/actions/restore-conan-build-state`
  - restores the lockfile and optional Conan cache from a previous workflow run
- `.github/actions/upload-conan-build-state`
  - uploads the lockfile and optional Conan cache produced by a workflow run
- `.github/actions/build-bundle-docs`
  - builds the generated documentation site used by context delivery

These actions exist to keep the reusable workflows focused on orchestration while moving repeated contracts and shell logic into versioned helpers.
