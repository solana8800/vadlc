"""Maintainer commands for the company engine; no upstream CLI dependency."""
import os
import pathlib
import platform
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
BRANCH = "v-agent-server"
REPOSITORY = "solana8800/vadlc"
WORKFLOW = "v-adlc-agent-server.yml"


def run(args, *, capture=False, cwd=ROOT):
    result = subprocess.run(args, cwd=cwd, check=True, text=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else ""


def require_branch():
    if run(["git", "branch", "--show-current"], capture=True) != BRANCH:
        raise ValueError(f"Checkout {BRANCH} before building or releasing the company engine")


def version():
    value = os.environ.get("VERSION", "")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][a-zA-Z0-9.-]+)?", value):
        raise ValueError("Supply VERSION, for example: make release VERSION=0.2.34")
    return value


def native_target():
    key = (sys.platform, platform.machine().lower())
    targets = {("darwin", "arm64"): ("darwin-arm64", "aarch64-apple-darwin"),
               ("linux", "x86_64"): ("linux-x64", "x86_64-unknown-linux-gnu"),
               ("win32", "amd64"): ("win32-x64", "x86_64-pc-windows-msvc"),
               ("win32", "x86_64"): ("win32-x64", "x86_64-pc-windows-msvc")}
    if key not in targets:
        raise ValueError("Supported native builds: macOS ARM64, Linux x64, Windows x64")
    return targets[key]


def require_pushed_clean_commit():
    require_branch()
    if run(["git", "status", "--porcelain"], capture=True):
        raise ValueError("Commit/push or preserve local changes before CI build/release")
    # gh always targets the company repository: check that origin is the same.
    origin = run(["git", "remote", "get-url", "origin"], capture=True)
    if origin not in (f"git@github.com:{REPOSITORY}.git", f"https://github.com/{REPOSITORY}.git",
                      f"https://github.com/{REPOSITORY}"):
        raise ValueError("origin must be the company vadlc GitHub repository")
    run(["git", "fetch", "origin", f"refs/heads/{BRANCH}:refs/remotes/origin/{BRANCH}"])
    head = run(["git", "rev-parse", "HEAD"], capture=True)
    remote = run(["git", "rev-parse", f"refs/remotes/origin/{BRANCH}"], capture=True)
    if head != remote:
        raise ValueError(f"Local HEAD must match origin/{BRANCH}; pull/push first")
    return head


def main(action):
    if action == "help":
        print("make build                         Build private App Server on this OS (Rust required)\n"
              "make smoke                         Check private policy and stdio initialize\n"
              "make package VERSION=0.2.34         Build/test/package this OS into dist/agent-server\n"
              "make test                          Run company release contract tests\n"
              "make build-ci VERSION=0.2.34        Build all three OS in CI; artifacts only\n"
              "make release VERSION=0.2.34         Tag pushed clean v-agent-server; CI publishes all OS to GitLab\n"
              "make release-status                Show recent native CI runs and releases")
    elif action == "build":
        require_branch()
        target_platform, target = native_target()
        command = ["cargo", "--config", "../company/agent-server/release.toml", "build", "--locked",
                   "--profile", "adlc-release", "--target", target]
        run([*command, "-p", "codex-app-server", "--bin", "v-adlc-agent-server"], cwd=ROOT / "codex-rs")
        if target_platform == "win32-x64":
            run([*command, "-p", "codex-windows-sandbox", "--bin", "codex-windows-sandbox-setup",
                 "--bin", "codex-command-runner"], cwd=ROOT / "codex-rs")
    elif action == "smoke":
        require_branch()
        run([sys.executable, "company/agent-server/smoke.py"])
    elif action == "package":
        require_branch()
        release_version = version()
        if run(["git", "status", "--porcelain"], capture=True):
            raise ValueError("Commit local changes first so the package sourceCommit identifies its source")
        target_platform, target = native_target()
        binary = "v-adlc-agent-server" + (".exe" if target_platform == "win32-x64" else "")
        run([sys.executable, "company/agent-server/package.py", "--binary",
             f"codex-rs/target/{target}/adlc-release/{binary}", "--platform", target_platform,
             "--version", release_version, "--out", "dist/agent-server"])
    elif action in ("build-ci", "release"):
        release_version = version()
        head = require_pushed_clean_commit()
        if action == "build-ci":
            run(["gh", "workflow", "run", WORKFLOW, "--repo", REPOSITORY,
                 "--ref", BRANCH, "-f", f"version={release_version}"])
        else:
            tag = f"agent-server-v{release_version}"
            if (run(["git", "tag", "--list", tag], capture=True) or
                    run(["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}"], capture=True)):
                raise ValueError("Release tag already exists; choose a new VERSION")
            run(["git", "tag", "-a", tag, head, "-m", f"V-ADLC agent server {release_version}"])
            run(["git", "push", "origin", f"refs/tags/{tag}"])
            print(f"Queued native release for {head}. Publication completes only after all three CI builds pass.")
    elif action == "release-status":
        run(["gh", "run", "list", "--repo", REPOSITORY, "--workflow", WORKFLOW, "--limit", "5"])
        run(["glab", "api", "projects/15759/packages?package_name=v-adlc-agent-server&per_page=5", "--hostname", "gitlab.vinsmartfuture.tech"])
    else:
        raise ValueError("Unknown company command")


if __name__ == "__main__":
    try:
        main(sys.argv[1] if len(sys.argv) == 2 else "help")
    except (ValueError, subprocess.CalledProcessError, FileNotFoundError) as error:
        print(f"Agent server command failed: {error}", file=sys.stderr)
        sys.exit(1)
