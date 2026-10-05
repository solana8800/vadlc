import importlib.util
import os
import pathlib
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location("agent_commands", pathlib.Path(__file__).parents[1] / "commands.py")
commands = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(commands)


class CommandsTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.responses = {
            ("git", "branch", "--show-current"): "v-agent-server",
            ("git", "status", "--porcelain"): "",
            ("git", "rev-parse", "HEAD"): "a" * 40,
            ("git", "rev-parse", "refs/remotes/origin/v-agent-server"): "a" * 40,
            ("git", "remote", "get-url", "origin"): "git@github.com:solana8800/vadlc.git",
        }
        self.runner = mock.patch.object(commands, "run", side_effect=self.run_command)
        self.runner.start()
        self.environment = mock.patch.dict(os.environ, {"VERSION": "0.2.34"})
        self.environment.start()
        self.addCleanup(self.runner.stop)
        self.addCleanup(self.environment.stop)

    def run_command(self, args, **kwargs):
        self.calls.append((args, kwargs))
        return self.responses.get(tuple(args), "")

    def test_release_tags_exact_pushed_commit_then_pushes_tag(self):
        commands.main("release")
        self.assertIn((["git", "tag", "-a", "agent-server-v0.2.34", "a" * 40,
                        "-m", "V-ADLC agent server 0.2.34"], {}), self.calls)
        self.assertEqual(self.calls[-1][0], ["git", "push", "origin", "refs/tags/agent-server-v0.2.34"])

    def test_release_rejects_dirty_wrong_branch_and_unpushed_changes(self):
        cases = [(('git', 'branch', '--show-current'), 'main'),
                 (('git', 'status', '--porcelain'), ' M source.rs'),
                 (('git', 'rev-parse', 'refs/remotes/origin/v-agent-server'), 'b' * 40),
                 (('git', 'remote', 'get-url', 'origin'), 'git@github.com:someone/else.git')]
        for key, value in cases:
            with self.subTest(key=key):
                previous = self.responses[key]
                self.responses[key] = value
                self.calls.clear()
                with self.assertRaises(ValueError):
                    commands.main("release")
                self.assertFalse(any(args[:2] == ['git', 'tag'] or args[:2] == ['git', 'push']
                                     for args, _ in self.calls))
                self.responses[key] = previous

    def test_existing_local_or_remote_tag_is_never_overwritten(self):
        for key in [("git", "tag", "--list", "agent-server-v0.2.34"),
                    ("git", "ls-remote", "--tags", "origin", "refs/tags/agent-server-v0.2.34")]:
            self.responses[key] = "existing tag"
            with self.assertRaises(ValueError):
                commands.main("release")
            self.assertFalse(any(args[:3] == ['git', 'tag', '-a'] for args, _ in self.calls))
            del self.responses[key]

    def test_invalid_version_never_invokes_git_or_shell(self):
        for value in ['', '../x', '1.2.3;touch /tmp/unsafe']:
            with mock.patch.dict(os.environ, {"VERSION": value}):
                with self.assertRaises(ValueError):
                    commands.main("release")
        self.assertEqual(self.calls, [])

    def test_ci_build_dispatches_only_to_company_branch_without_tag(self):
        commands.main("build-ci")
        self.assertEqual(self.calls[-1][0], ['gh', 'workflow', 'run', 'v-adlc-agent-server.yml',
                         '--repo', 'solana8800/vadlc', '--ref', 'v-agent-server', '-f', 'version=0.2.34'])
        self.assertFalse(any(args[:2] == ['git', 'tag'] for args, _ in self.calls))

    def test_mac_build_only_builds_private_app_server(self):
        with mock.patch.object(commands.sys, 'platform', 'darwin'), mock.patch.object(commands.platform, 'machine', return_value='arm64'):
            commands.main('build')
        cargo = [args for args, _ in self.calls if args[0] == 'cargo']
        self.assertEqual(len(cargo), 1)
        self.assertEqual(cargo[0][-4:], ['-p', 'codex-app-server', '--bin', 'v-adlc-agent-server'])
        self.assertIn('aarch64-apple-darwin', cargo[0])

    def test_windows_build_includes_required_sandbox_helpers(self):
        with mock.patch.object(commands.sys, 'platform', 'win32'), mock.patch.object(commands.platform, 'machine', return_value='AMD64'):
            commands.main('build')
        cargo = [args for args, _ in self.calls if args[0] == 'cargo']
        self.assertEqual(len(cargo), 2)
        self.assertIn('codex-windows-sandbox-setup', cargo[1])
        self.assertIn('codex-command-runner', cargo[1])

    def test_unsupported_native_platform_fails_before_cargo(self):
        with mock.patch.object(commands.sys, 'platform', 'darwin'), mock.patch.object(commands.platform, 'machine', return_value='x86_64'):
            with self.assertRaises(ValueError):
                commands.main('build')
        self.assertFalse(any(args[0] == 'cargo' for args, _ in self.calls))

    def test_package_rejects_source_changes_without_forging_manifest_identity(self):
        self.responses[("git", "status", "--porcelain")] = " M codex-rs/core/src/lib.rs"
        with self.assertRaises(ValueError):
            commands.main('package')
        self.assertFalse(any('company/agent-server/package.py' in args for args, _ in self.calls))

    def test_DIST13_release_status_reads_company_registry(self):
        commands.main('release-status')
        self.assertEqual(self.calls[-1][0], ['glab','api','projects/15759/packages?package_name=v-adlc-agent-server&per_page=5','--hostname','gitlab.vinsmartfuture.tech'])
        self.assertFalse(any(args[:2]==['gh','release'] for args,_ in self.calls))


if __name__ == '__main__':
    unittest.main()
