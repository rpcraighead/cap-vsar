"""Deployment configuration that must fail closed (O2-3, O2-4).

Static checks on docker-compose.yml and scripts/deploy.sh; they need neither
Docker nor a running stack.
"""
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


if __name__ == "__main__":
    unittest.main()
