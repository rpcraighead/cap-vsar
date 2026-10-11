"""Deployment configuration that must fail closed (O2-3, O2-4).

Static checks on docker-compose.yml and scripts/deploy.sh; they need neither
Docker nor a running stack.
"""
import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = (ROOT / "docker-compose.yml").read_text()


class FailClosed(unittest.TestCase):
    def test_mumble_passwords_are_required_by_compose(self):
        for var in ("MUMBLE_SUPERUSER_PASSWORD", "MUMBLE_SERVER_PASSWORD"):
            uses = re.findall(r"\$\{" + var + r"([^}]*)\}", COMPOSE)
            self.assertTrue(uses, var)
            for suffix in uses:
                self.assertTrue(suffix.startswith(":?"),
                                f"{var} may be blank: ${{{var}{suffix}}}")

    def test_deploy_script_refuses_blank_mumble_passwords(self):
        deploy = (ROOT / "scripts" / "deploy.sh").read_text()
        self.assertIn("MUMBLE_SERVER_PASSWORD", deploy)
        self.assertIn("is empty in .env", deploy)

    def test_the_exercise_service_is_marked_production(self):
        block = COMPOSE[COMPOSE.index("  exercise:"):COMPOSE.index("  radio-https:")]
        self.assertRegex(block, r"CAPVSAR_ENV:\s*production")

    def test_dev_open_is_never_forwarded_into_a_container(self):
        self.assertNotRegex(COMPOSE, r"(?m)^\s*CAPVSAR_DEV_OPEN\s*:",
                            "compose must not pass the dev-open flag through")


class NoStalePorts(unittest.TestCase):
    def test_consoles_do_not_rewrite_links_to_unpublished_ports(self):
        """F2-1: a.nav-planner was pointed at :8090, which Caddy no longer serves."""
        for f in (ROOT / "services/exercise/app/static").glob("*.js"):
            self.assertNotIn(":8090", f.read_text(), f.name)


class StateDirAndBoardProfile(unittest.TestCase):
    """O2-7 and O2-5, from the compose file alone."""

    def test_every_state_bind_mount_goes_through_capvsar_state_dir(self):
        for tail in ("/mumble/data:/data", "/services/exercise/data:/data",
                     "/services/exercise/radio-public:/radio-public:ro",
                     "/services/flightplanner/data:/app/data",
                     "/services/flightplanner/data/charts:/app/charts"):
            self.assertIn("${CAPVSAR_STATE_DIR:-.}" + tail, COMPOSE, tail)

    def test_no_state_mount_is_a_bare_relative_path(self):
        mounts = re.findall(r"(?m)^\s+- (\./\S+?):/", COMPOSE)
        self.assertEqual(mounts, ["./services/exercise/Caddyfile"], "only config may be a bare ./ mount")

    def test_board_repo_defaults_under_the_state_dir(self):
        self.assertIn("${CAPVSAR_BOARD_REPO:-${CAPVSAR_STATE_DIR:-.}/services/board/repo}", COMPOSE)

    def test_the_board_is_an_opt_in_profile_and_nothing_depends_on_it(self):
        block = COMPOSE[COMPOSE.index("\n  board:"):COMPOSE.index("\n# WireGuard")]
        self.assertRegex(block, r'profiles:\s*\["board"\]')
        caddy = COMPOSE[COMPOSE.index("  radio-https:"):COMPOSE.index("  flightplanner:")]
        self.assertNotRegex(caddy, r"(?m)^\s+- board\s*$")

    def test_env_example_documents_state_dir_and_has_no_dead_mumble_keys(self):
        env = (ROOT / ".env.example").read_text()
        self.assertIn("CAPVSAR_STATE_DIR", env)
        self.assertNotRegex(env, r"(?m)^\s*#?\s*CAPVSAR_MUMBLE_")

    def test_ci_scratch_output_is_ignored(self):
        self.assertIn(".ci-out/", (ROOT / ".gitignore").read_text().splitlines())


class PlannerPort(unittest.TestCase):
    """O2-10: the planner has listened on 8080 since L-12/O-8."""

    FILES = ("scripts/preflight.py", "scripts/deploy.sh", "infra/ROUTER.md",
             "docs/WEB_HOSTING_AND_IDENTITY_PLAN.md")

    def test_no_current_file_names_the_old_planner_port(self):
        for rel in self.FILES:
            self.assertNotIn("8090", (ROOT / rel).read_text(), rel)

    def test_preflight_probes_the_real_planner_port(self):
        self.assertIn('(8080, "planner")', (ROOT / "scripts/preflight.py").read_text())

    def test_router_doc_lists_the_listeners_caddy_actually_publishes(self):
        published = set(re.findall(r'"(\d+):\d+"', COMPOSE[COMPOSE.index("  radio-https:"):COMPOSE.index("  flightplanner:")]))
        doc = (ROOT / "infra/ROUTER.md").read_text()
        for port in published:
            self.assertRegex(doc, rf"\|\s*{port}\s*\|", f"ROUTER.md does not list Caddy's {port}")


class DeadWireGuardHelper(unittest.TestCase):
    """O2-12: the WireGuard container was removed; its helper must not linger."""

    def test_wg_peer_script_is_gone_and_unreferenced_by_live_docs(self):
        self.assertFalse((ROOT / "scripts" / "wg-peer.sh").exists())
        for rel in ("README.md", "docs/CONNECT.md", "infra/ROUTER.md", "docker-compose.yml"):
            p = ROOT / rel
            if p.exists():
                self.assertNotIn("wg-peer", p.read_text(), rel)


class PymumblePin(unittest.TestCase):
    """O2-9: the component that holds the Mumble password is pinned by content."""

    PIN = re.compile(r"pymumble @ (https://github\.com/azlux/pymumble/archive/([0-9a-f]{40})\.tar\.gz)")

    def read(self, rel):
        return (ROOT / rel).read_text()

    def test_the_pinned_url_names_a_full_40_char_commit(self):
        for rel in ("services/exercise/requirements-pymumble.txt", "requirements-dev.txt"):
            self.assertRegex(self.read(rel), self.PIN, rel)

    def test_the_image_requirement_carries_a_sha256_and_the_pin_is_not_in_the_main_file(self):
        self.assertRegex(self.read("services/exercise/requirements-pymumble.txt"),
                         r"--hash=sha256:[0-9a-f]{64}")
        self.assertNotIn("pymumble @", self.read("services/exercise/requirements.txt"),
                         "a hash in requirements.txt would force --require-hashes on every package")

    def test_dev_and_image_install_the_same_commit(self):
        image = self.PIN.search(self.read("services/exercise/requirements-pymumble.txt")).group(2)
        dev = self.PIN.search(self.read("requirements-dev.txt")).group(2)
        self.assertEqual(image, dev)

    def test_dev_requirements_have_no_hash_which_would_force_require_hashes_mode(self):
        self.assertNotIn("--hash", self.read("requirements-dev.txt"))

    def test_dockerfile_installs_it_hash_checked_and_without_resolving_dependencies(self):
        dockerfile = self.read("services/exercise/Dockerfile")
        self.assertRegex(dockerfile, r"pip install[^\n]*--no-deps[^\n]*--require-hashes[^\n]*requirements-pymumble\.txt")
        self.assertIn("requirements-pymumble.txt", re.search(r"COPY requirements[^\n]*", dockerfile).group(0))

    def test_pymumbles_own_dependencies_stay_pinned_in_the_main_file(self):
        main = self.read("services/exercise/requirements.txt")
        self.assertIn("opuslib==3.0.1", main)
        self.assertIn("protobuf==3.20.3", main)


def ignore_patterns(rel):
    return [l.strip() for l in (ROOT / rel).read_text().splitlines()
            if l.strip() and not l.lstrip().startswith("#")]


class DockerContextHygiene(unittest.TestCase):
    def test_exercise_and_board_keep_state_and_secrets_out_of_the_build_context(self):
        ex = ignore_patterns("services/exercise/.dockerignore")
        self.assertIn("data/", ex)
        self.assertIn("radio-public/", ex)
        board = ignore_patterns("services/board/.dockerignore")
        self.assertIn("repo/", board)
        self.assertIn("secrets/", board)

    def test_dockerfiles_still_copy_what_the_dockerignore_does_not_exclude(self):
        """Excluding something the Dockerfile COPYs would break the build."""
        for svc, copies in (("exercise", ("requirements.txt", "requirements-pymumble.txt", "app")),
                            ("board", ("requirements.txt", "app"))):
            ignored = ignore_patterns(f"services/{svc}/.dockerignore")
            for name in copies:
                self.assertNotIn(name, ignored)
                self.assertNotIn(name + "/", ignored)


class OneTestCommand(unittest.TestCase):
    """O2-2: one command runs every suite; CI runs the same one on 3.12."""

    CI = (ROOT / "scripts" / "ci_local.sh").read_text()

    def test_each_pytest_suite_runs_in_its_own_process(self):
        runs = re.findall(r"(?m)^run (pytest_\w+)\s+\$PY -m pytest (\S+)", self.CI)
        self.assertEqual({name for name, _ in runs},
                         {"pytest_root", "pytest_ai", "pytest_fp", "pytest_board"})
        self.assertEqual(len({target for _, target in runs}), 4)
        targets = {name: target for name, target in runs}
        self.assertEqual(targets["pytest_fp"], "services/flightplanner/tests")
        self.assertEqual(targets["pytest_board"], "services/board/tests")

    def test_run_tests_is_the_entry_point_and_is_executable(self):
        script = ROOT / "scripts" / "run_tests.sh"
        self.assertTrue(os.access(script, os.X_OK))
        self.assertIn("ci_local.sh", script.read_text())
        self.assertTrue(os.access(ROOT / "scripts" / "ci_local.sh", os.X_OK))

    def test_ci_workflow_runs_the_local_script_on_python_3_12(self):
        wf = (ROOT / ".gitea" / "workflows" / "ci.yml").read_text()
        self.assertIn('python-version: "3.12"', wf)
        self.assertIn("scripts/ci_local.sh --no-shim", wf)
        self.assertIn("pip install -r requirements-dev.txt", wf)

    def test_ci_workflow_is_valid_yaml_when_pyyaml_is_available(self):
        yaml = __import__("pytest").importorskip("yaml")
        doc = yaml.safe_load((ROOT / ".gitea" / "workflows" / "ci.yml").read_text())
        self.assertIn("tests", doc["jobs"])

    def test_pytest_ini_explains_why_two_suites_are_not_collected(self):
        ini = (ROOT / "pytest.ini").read_text()
        self.assertIn("scripts/run_tests.sh", ini)
        self.assertNotIn("services/board", ini.split("testpaths", 1)[1])

    def test_readmes_name_the_command(self):
        for rel in ("README.md", "docs/mission-base-radio/README.md"):
            self.assertIn("scripts/run_tests.sh", (ROOT / rel).read_text(), rel)


if __name__ == "__main__":
    unittest.main()
