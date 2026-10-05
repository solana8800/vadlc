# Company runtime release

The company integration branch is `v-agent-server` (renamed from
`codex/tuantd26/private-agent-server` without changing its history). Target company
PRs at this branch, then pull it before a build or release. Upstream `main` stays
separate for fork synchronization.
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

## Maintainer Makefile

From the repository root, on `v-agent-server`:

```sh
make help
make build                            # Rust toolchain; current OS only
make smoke                            # No model/network calls
make package VERSION=0.2.34            # Local archive under dist/agent-server
make test
make build-ci VERSION=0.2.34           # gh login; all three OS, artifacts only
make release VERSION=0.2.34            # New immutable tag; all three OS + release
make release-status
```

Use a new version for each release. CI build/release requires a clean checkout
whose HEAD matches the pushed `origin/v-agent-server`; release refuses existing
tags. Publication is asynchronous: `make release` queues CI, it does not mean the
three assets are already available. Check `make release-status` before importing.
Local Make targets need Python 3 and GNU/BSD make (Windows can use Git Bash with
make). Cross-platform builds use GitHub's native runners, not cross compilation
on the Mac. The Makefile only builds the private App Server and Windows sandbox
helpers, never Codex CLI.

After publication, inside ADLC (Python >=3.10):

```sh
python3 publish/packaging/pin-agent-server-release.py \
  --version 0.2.34 --source-commit <full-vadlc-release-commit>
make installers
```

Commit the verified ADLC release lock with the ADLC change. A new vadlc release
does not automatically replace ADLC's pinned engine.

## Company GitLab distribution

Source and tags stay on GitHub (`solana8800/vadlc`, branch `v-agent-server`).
`make release-gitlab VERSION=<new-version>` tags the pushed source and runs the
existing three-OS GitHub Actions matrix. Publication now targets the company
GitLab distribution project `vsf-qtvhdl/common/engineering/aidlc` (15759):

- Generic package: `v-adlc-agent-server/<version>` (three archives + SHA256SUMS.txt).
- GitHub source tag: `agent-server-v<version>`; `release-metadata.json` records the exact source commit.
- No runtime object is added to the ADLC Releases page; Desktop permalink/latest remains Desktop.
- ADLC Desktop releases keep separate `v-adlc-<version>` tags/packages.

Configure the repository Actions secret `GITLAB_RELEASE_TOKEN` with a narrowly
scoped company token allowed to publish generic packages on project 15759.
Do not put credentials in source or URLs. The runner must reach company GitLab;
if hosted runners cannot, move the publish job to an approved self-hosted runner.
No new GitHub or ADLC Desktop Release object is created. A failed publication fails the job; inspect it
before retrying or advancing the ADLC runtime pin.

For importing already verified archives locally:
`GITLAB_RELEASE_TOKEN=<token> python3 company/agent-server/publish_gitlab.py --directory <archives> --version <version> --source-commit <40-char-sha>`.
Archives require adjacent `.sha256` files for all three targets. Do not rerun an
existing release tag with different bytes.
