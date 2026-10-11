"""scripts/deploy_lib.sh: the parts of deploy.sh that can be tested without Docker.

O2-5 (board host paths / opt-in), O2-7 (CAPVSAR_STATE_DIR), and the
"do not source .env as shell" fix. Each case runs the real shell functions in
a scratch directory.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "scripts" / "deploy_lib.sh"


def sh(script, cwd, env=None):
    full = {"PATH": os.environ["PATH"], "HOME": str(cwd)}
    full.update(env or {})
    return subprocess.run(["bash", "-c", f'. "{LIB}"\n{script}'], cwd=cwd, env=full,
                          capture_output=True, text=True)


class Scratch(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, True)


class EnvGet(Scratch):
    def get(self, text, key="K"):
        (self.d / ".env").write_text(text)
        r = sh(f"env_get {key}", self.d)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_values_are_not_expanded_or_mangled(self):
        self.assertEqual(self.get("K=pa$word#1\n"), "pa$word#1")
        self.assertEqual(self.get("K=$HOME/x\n"), "$HOME/x")
        self.assertEqual(self.get("K=`id`\n"), "`id`")

    def test_a_line_that_is_shell_code_is_never_executed(self):
        marker = self.d / "pwned"
        self.assertEqual(self.get(f"touch {marker}\nK=ok\n"), "ok")
        self.assertFalse(marker.exists())

    def test_quotes_comments_and_spaces(self):
        self.assertEqual(self.get('K="two words # kept"  # trailing\n'), "two words # kept")
        self.assertEqual(self.get("K='a b'\n"), "a b")
        self.assertEqual(self.get("K=plain   # comment\n"), "plain")
        self.assertEqual(self.get("export K=1\n"), "1")

    def test_last_assignment_wins_and_missing_or_blank_is_empty(self):
        self.assertEqual(self.get("K=1\nK=2\n"), "2")
        self.assertEqual(self.get("OTHER=1\n"), "")
        self.assertEqual(self.get("K=\n"), "")
        self.assertEqual(self.get("# K=commented\n"), "")

    def test_a_longer_key_with_the_same_prefix_is_not_matched(self):
        self.assertEqual(self.get("KEY2=x\n"), "")

    def test_shell_environment_wins_over_dotenv_as_in_compose(self):
        (self.d / ".env").write_text("CAPVSAR_STATE_DIR=/from/file\n")
        self.assertEqual(sh("state_dir", self.d).stdout, "/from/file")
        self.assertEqual(sh("state_dir", self.d, {"CAPVSAR_STATE_DIR": "/from/env"}).stdout, "/from/env")
        (self.d / ".env").unlink()
        self.assertEqual(sh("state_dir", self.d).stdout, ".")


class HostPaths(Scratch):
    def test_default_layout_is_the_original_in_checkout_paths(self):
        r = sh("prepare_host_paths", self.d)
        self.assertEqual(r.returncode, 0, r.stderr)
        for p in ("mumble/data", "services/exercise/data", "services/exercise/radio-public",
                  "services/flightplanner/data/charts", "services/board/repo",
                  "services/board/secrets"):
            self.assertTrue((self.d / p).is_dir(), p)
        self.assertTrue((self.d / "services/flightplanner/data/aviation_data.db").is_file())

    def test_the_board_key_and_known_hosts_are_never_created_as_anything(self):
        """Docker would have made them directories; the README's ssh-keygen then fails."""
        sh("prepare_host_paths", self.d)
        self.assertFalse((self.d / "services/board/secrets/id_ed25519").exists())
        self.assertFalse((self.d / "services/board/secrets/known_hosts").exists())
        self.assertEqual(oct((self.d / "services/board/secrets").stat().st_mode & 0o777), "0o700")

    def test_ssh_keygen_and_git_clone_from_the_readme_work_on_what_it_made(self):
        sh("prepare_host_paths", self.d)
        keygen = shutil.which("ssh-keygen")
        if keygen:
            r = subprocess.run([keygen, "-t", "ed25519", "-N", "", "-q", "-f",
                                str(self.d / "services/board/secrets/id_ed25519")],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
        src = self.d / "src"
        subprocess.run(["git", "init", "-q", str(src)], check=True)
        r = subprocess.run(["git", "clone", "-q", str(src), "services/board/repo"], cwd=self.d,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_state_dir_moves_every_state_path_and_creates_nothing_in_the_checkout(self):
        state = self.d / "state"
        r = sh("prepare_host_paths", self.d, {"CAPVSAR_STATE_DIR": str(state)})
        self.assertEqual(r.returncode, 0, r.stderr)
        for p in ("mumble/data", "services/exercise/data", "services/exercise/radio-public",
                  "services/flightplanner/data/charts", "services/board/repo"):
            self.assertTrue((state / p).is_dir(), p)
        self.assertFalse((self.d / "mumble").exists())
        self.assertFalse((self.d / "services/exercise").exists())

    def test_existing_data_is_left_alone(self):
        (self.d / "services/exercise/data").mkdir(parents=True)
        (self.d / "services/exercise/data/exercise.db").write_text("precious")
        (self.d / "services/flightplanner/data").mkdir(parents=True)
        (self.d / "services/flightplanner/data/aviation_data.db").write_text("also precious")
        sh("prepare_host_paths", self.d)
        self.assertEqual((self.d / "services/exercise/data/exercise.db").read_text(), "precious")
        self.assertEqual((self.d / "services/flightplanner/data/aviation_data.db").read_text(), "also precious")


class BoardOptIn(Scratch):
    def configure(self, key=True, known=True, repo=True):
        sec = self.d / "services/board/secrets"
        sec.mkdir(parents=True, exist_ok=True)
        if key:
            (sec / "id_ed25519").write_text("KEY")
        if known:
            (sec / "known_hosts").write_text("host ssh-ed25519 AAAA")
        if repo:
            (self.d / "services/board/repo/.git").mkdir(parents=True)

    def test_a_fresh_host_skips_the_board_and_says_why(self):
        sh("prepare_host_paths", self.d)
        r = sh("board_configured", self.d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("board not configured", r.stdout)
        self.assertIn("git clone", r.stdout)

    def test_a_complete_setup_enables_the_board(self):
        self.configure()
        self.assertEqual(sh("board_configured", self.d).returncode, 0)

    def test_each_missing_piece_keeps_the_board_out(self):
        for missing in ("key", "known", "repo"):
            with self.subTest(missing=missing):
                shutil.rmtree(self.d / "services", ignore_errors=True)
                self.configure(**{missing: False})
                self.assertEqual(sh("board_configured", self.d).returncode, 1)

    def test_a_directory_where_a_key_file_belongs_is_reported_clearly(self):
        self.configure(key=False)
        (self.d / "services/board/secrets/id_ed25519").mkdir()
        r = sh("board_configured", self.d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("is a DIRECTORY", r.stdout)

    def test_custom_paths_from_dotenv_are_honoured(self):
        keys = self.d / "elsewhere"
        keys.mkdir()
        (keys / "k").write_text("KEY")
        (keys / "h").write_text("HOSTS")
        (self.d / "clone/.git").mkdir(parents=True)
        (self.d / ".env").write_text(
            f"CAPVSAR_BOARD_REPO={self.d}/clone\nCAPVSAR_BOARD_SSH_KEY={keys}/k\n"
            f"CAPVSAR_BOARD_KNOWN_HOSTS={keys}/h\n")
        self.assertEqual(sh("board_configured", self.d).returncode, 0)


class DeployScriptWiring(unittest.TestCase):
    def setUp(self):
        self.deploy = (ROOT / "scripts" / "deploy.sh").read_text()

    def test_syntax(self):
        for f in ("deploy.sh", "deploy_lib.sh"):
            r = subprocess.run(["bash", "-n", str(ROOT / "scripts" / f)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_env_is_not_sourced_as_shell(self):
        import re
        self.assertIsNone(re.search(r"(?m)^\s*(\.|source)\s+\.?/?\.env\b", self.deploy))
        self.assertNotIn("set -a", self.deploy)

    def test_the_board_is_built_and_started_only_through_the_configured_gate(self):
        self.assertIn("board_configured", self.deploy)
        self.assertIn("--profile board", self.deploy)
        self.assertNotIn("build exercise flightplanner board", self.deploy)

    def test_deploy_uses_the_state_dir_not_hardcoded_checkout_paths(self):
        for hard in ("mkdir -p mumble/data", "mkdir -p services/exercise",
                     "chown -R 1000:1000 services/exercise/data",
                     "CA_DST=services/exercise"):
            self.assertNotIn(hard, self.deploy)
        self.assertIn("$STATE/mumble/data/mumble-server.sqlite", self.deploy)


if __name__ == "__main__":
    unittest.main()
