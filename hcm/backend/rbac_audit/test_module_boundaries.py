"""Enforces hcm/README.md "Module rules" #1 mechanically (H2):

    Apps may import `core_hr` and `rbac_audit`; apps may NOT import each
    other — peer data goes through a read-only `<app>/queries.py` seam.

Until now this was "enforced in review" only. This walks every app's
production modules with `ast` (no execution) and fails on any import of a
peer app that isn't that peer's `queries` module. Carve-outs, all documented
in the README: test modules, migrations (Django writes cross-app deps
there itself), and `core_hr/management/commands/seed_demo_data.py`, the one
intentional exception (it seeds demo data across every module).
"""
import ast
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

BACKEND = Path(settings.BASE_DIR)
DOMAIN_APPS = [
    "core_hr", "rbac_audit", "recruitment", "performance", "learning", "compensation",
    "assessments", "identity_verification", "ee_reporting", "policies",
    "integrations",  # outbound adapters (ADR-011); may import core_hr/rbac_audit only, like any app
]
SHARED_KERNEL = {"core_hr", "rbac_audit"}
EXEMPT_FILES = {BACKEND / "core_hr" / "management" / "commands" / "seed_demo_data.py"}


def _production_modules(app: str):
    for path in (BACKEND / app).rglob("*.py"):
        rel = path.relative_to(BACKEND / app).parts
        if "migrations" in rel or "__pycache__" in rel:
            continue
        if path.name.startswith("test") or path.name == "tests.py":
            continue
        if path in EXEMPT_FILES:
            continue
        yield path


def _imported_roots(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module, node.module.split(".")[0]


class ModuleBoundaryTests(SimpleTestCase):
    def test_no_peer_app_imports_outside_queries_seams(self):
        violations = []
        for app in DOMAIN_APPS:
            for path in _production_modules(app):
                for dotted, root in _imported_roots(path):
                    if root == app or root in SHARED_KERNEL or root not in DOMAIN_APPS:
                        continue
                    if dotted == f"{root}.queries" or dotted.startswith(f"{root}.queries."):
                        continue  # the sanctioned read-only seam
                    violations.append(f"{path.relative_to(BACKEND)} imports {dotted}")
        self.assertEqual(violations, [], "Peer-app imports outside a queries.py seam:\n" + "\n".join(violations))

    def test_shared_kernel_does_not_import_domain_apps(self):
        """core_hr and rbac_audit are imported by everyone; they must not import back
        (the seed command is the documented exception). ConsentRecord's FK to
        recruitment.Applicant is a string reference in a migration, not an import —
        flagged as a design tension in NEXT_AGENT_BRIEF §3.6, not a rule breach here."""
        violations = []
        for app in SHARED_KERNEL:
            for path in _production_modules(app):
                for dotted, root in _imported_roots(path):
                    if root in DOMAIN_APPS and root not in SHARED_KERNEL:
                        violations.append(f"{path.relative_to(BACKEND)} imports {dotted}")
        self.assertEqual(violations, [], "Shared kernel imports a domain app:\n" + "\n".join(violations))

    def test_every_queries_seam_is_read_only(self):
        """A `<app>/queries.py` exists to be imported by peers; it must not write."""
        for app in DOMAIN_APPS:
            seam = BACKEND / app / "queries.py"
            if not seam.exists():
                continue
            source = seam.read_text(encoding="utf-8")
            for forbidden in (".create(", ".update(", ".delete(", ".save(", "bulk_create", "update_or_create"):
                self.assertNotIn(forbidden, source, f"{app}/queries.py must be read-only (found {forbidden})")
