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


if __name__ == "__main__":
    unittest.main()
