# Company runtime release

The private entrypoint already lives on `codex/tuantd26/private-agent-server`.
This release layer changes no upstream Rust source or workspace profile. Keep
`company/agent-server/` and its one workflow as the company-owned overlay when
rebasing/syncing upstream. Resolve upstream changes first, then build and smoke
all three targets; do not cherry-pick the old PR #2 global profile override.

The workflow builds on native macOS ARM64, Ubuntu 22.04 x64 (glibc 2.35 baseline),
and Windows x64 runners. ADLC on macOS downloads these assets; it never needs
Rust or a cross compiler. Archives contain exactly one binary, its manifest,
LICENSE and NOTICE at the archive root. Windows also carries the two upstream-named
sandbox helpers with individual supportFiles hashes; these are helpers, not Codex CLI. Binary SHA256 and archive SHA256 are
separate checks. Preserve Apache attribution; branding does not remove licensing.

PR/workflow-dispatch builds upload artifacts only. After review, tag the intended
company commit `agent-server-v<version>` to publish all three assets together.
Never reuse a published tag. ADLC pins archive checksums/sourceCommit in its release
lock, so publishing a release alone does not change an installed application's engine.

Local build example (inside codex-rs):
`cargo --config ../company/agent-server/release.toml build --locked --profile adlc-release -p codex-app-server --bin v-adlc-agent-server`
Then run `company/agent-server/smoke.py` and `package.py` from the repository root.
