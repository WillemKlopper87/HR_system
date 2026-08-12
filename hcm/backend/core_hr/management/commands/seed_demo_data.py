from __future__ import annotations

import random
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from core_hr.data_quality import run_data_quality_checks
from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from rbac_audit.models import Role, RoleAssignment

User = get_user_model()

# Sprint-0-Decision-Log.md #3: synthetic dataset, ~600 employees, SA
# demographic distribution. Defaults smaller here for fast local iteration
# — pass --count 600 to match the ratified full rehearsal dataset.
DEFAULT_COUNT = 150

DEPARTMENTS = [
    ("Executive Office", "EXEC"),
    ("Engineering", "ENG"),
    ("Finance", "FIN"),
    ("Human Resources", "HR"),
    ("Sales & Marketing", "SLM"),
    ("Operations", "OPS"),
    ("Legal & Compliance", "LEG"),
]

LOCATIONS = [
    ("Head Office — Johannesburg", "JHB", "GP"),
    ("Cape Town Office", "CPT", "WC"),
    ("Durban Office", "DBN", "KZN"),
    ("Pretoria Office", "PTA", "GP"),
]

FIRST_NAMES = [
    "Thandiwe", "Sipho", "Naledi", "Kagiso", "Lerato", "Tebogo", "Ayanda", "Bongani",
    "Zanele", "Mandla", "Nomvula", "Sizwe", "Precious", "Themba", "Nokuthula", "Vusi",
    "Priya", "Arjun", "Kavitha", "Rajesh", "Fatima", "Ahmed", "Chantal", "Riaan",
    "Elmarie", "Pieter", "Susan", "James", "Michael", "Sarah", "Emma", "David",
    "Grace", "Peter", "Lindiwe", "Jabulani", "Palesa", "Kabelo", "Nosipho", "Mbali",
]
LAST_NAMES = [
    "Nkosi", "Dlamini", "Mokoena", "Khumalo", "Ndlovu", "Zulu", "Mahlangu", "Sithole",
    "Naidoo", "Pillay", "Govender", "Reddy", "van der Merwe", "Botha", "Pretorius",
    "de Villiers", "Smith", "Jones", "Williams", "Brown", "Mabuza", "Tshabalala",
    "Mnguni", "Radebe", "Cele", "Molefe", "Sithebe", "Abrahams", "Adams", "Isaacs",
]

RACE_WEIGHTS = [("african", 0.72), ("coloured", 0.10), ("indian", 0.03), ("white", 0.13), ("not_disclosed", 0.02)]
GENDER_WEIGHTS = [("male", 0.51), ("female", 0.47), ("not_disclosed", 0.02)]
DISABILITY_WEIGHTS = [("no", 0.95), ("yes", 0.03), ("not_disclosed", 0.02)]


def _weighted_choice(weights, rng):
    return rng.choices([v for v, _ in weights], weights=[w for _, w in weights], k=1)[0]


class Command(BaseCommand):
    help = (
        "Seeds synthetic org structure, employees, and demo logins for local "
        "development and UI review (Sprint 0 decision log #3: synthetic dataset). "
        "Refuses to run against a database that already has employees."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--count", type=int, default=DEFAULT_COUNT,
            help=f"Employees to generate (default {DEFAULT_COUNT}; decision log's full dataset is 600).",
        )
        parser.add_argument("--seed", type=int, default=42, help="Random seed, for reproducible demo data.")

    def handle(self, *args, **options):
        if Employee.objects.exists():
            self.stdout.write(self.style.WARNING(
                "Employees already exist — refusing to seed. Run against an empty database."
            ))
            return

        count = options["count"]
        rng = random.Random(options["seed"])

        with transaction.atomic():
            departments = [Department.objects.create(name=name, code=code) for name, code in DEPARTMENTS]
            locations = [Location.objects.create(name=n, code=c, province=p) for n, c, p in LOCATIONS]
            levels = list(OccupationalLevel.objects.order_by("order"))
            grades_by_level = {
                level.code: [
                    JobGrade.objects.create(
                        name=f"{level.name} Grade {i}", code=f"{level.code}-G{i}", occupational_level=level
                    )
                    for i in (1, 2)
                ]
                for level in levels
            }

            exec_dept, *other_depts = departments
            top_level, *rest_levels = levels
            senior_level = rest_levels[0] if rest_levels else top_level
            mid_level = rest_levels[len(rest_levels) // 2] if rest_levels else top_level
            junior_level = rest_levels[-1] if rest_levels else top_level

            employee_counter = 0
            # hire() itself grants no roles — role provisioning is a
            # separate concern (RBAC-Roles.md notes it's destined for Entra
            # ID group sync, ADR-004). Every seeded employee still needs
            # the base 'employee' role (self row-scope) to see their own
            # record at all, so this seed data grants it explicitly, same
            # as every RBAC test's setUp does.
            base_role = Role.objects.get(name="employee")

            def hire(*, department, level, location, manager, hire_date):
                nonlocal employee_counter
                employee_counter += 1
                n = employee_counter
                first = rng.choice(FIRST_NAMES)
                last = rng.choice(LAST_NAMES)
                grade = rng.choice(grades_by_level[level.code])
                employee = Employee.objects.hire(
                    employee_number=f"E{n:05d}",
                    first_name=first,
                    last_name=last,
                    date_of_birth=date(1965, 1, 1) + timedelta(days=rng.randint(0, 365 * 40)),
                    work_email=f"{first.lower()}.{last.lower().replace(' ', '')}.{n}@sentech-demo.example",
                    hire_date=hire_date,
                    department=department,
                    occupational_level=level,
                    job_grade=grade,
                    location=location,
                    manager=manager,
                    race=_weighted_choice(RACE_WEIGHTS, rng),
                    gender=_weighted_choice(GENDER_WEIGHTS, rng),
                    disability_status=_weighted_choice(DISABILITY_WEIGHTS, rng),
                    race_source="hr_captured",
                    disability_source="hr_captured",
                )
                RoleAssignment.objects.create(employee=employee, role=base_role)
                return employee

            ceo = hire(department=exec_dept, level=top_level, location=locations[0], manager=None, hire_date=date(2015, 1, 1))

            dept_heads = []
            for dept in other_depts:
                head = hire(department=dept, level=senior_level, location=rng.choice(locations), manager=ceo, hire_date=date(2017, 1, 1))
                dept_heads.append(head)

            remaining = max(count - 1 - len(dept_heads), 0)
            for i in range(remaining):
                dept_index = i % len(other_depts)
                head = dept_heads[dept_index]
                level = mid_level if rng.random() < 0.35 else junior_level
                hire(
                    department=other_depts[dept_index], level=level, location=rng.choice(locations), manager=head,
                    hire_date=date(2018, 1, 1) + timedelta(days=rng.randint(0, 365 * 7)),
                )

            hr_admin_role = Role.objects.get(name="hr_admin")
            line_manager_role = Role.objects.get(name="line_manager")
            dept_codes = [dept.code for dept in other_depts]

            hr_head = dept_heads[dept_codes.index("HR")]
            RoleAssignment.objects.create(employee=hr_head, role=hr_admin_role)
            hr_head.user = User.objects.create_user(username="hradmin", password="hradmin123")
            hr_head.save(update_fields=["user"])

            eng_head = dept_heads[dept_codes.index("ENG")]
            RoleAssignment.objects.create(employee=eng_head, role=line_manager_role)
            eng_head.user = User.objects.create_user(username="manager", password="manager123")
            eng_head.save(update_fields=["user"])

            report_version = eng_head.direct_reports.filter(valid_to__isnull=True).select_related("employee").first()
            if report_version is not None:
                staff = report_version.employee
                staff.user = User.objects.create_user(username="employee", password="employee123")
                staff.save(update_fields=["user"])

        run_data_quality_checks()

        self.stdout.write(self.style.SUCCESS(f"Seeded {employee_counter} employees across {len(departments)} departments."))
        self.stdout.write(
            "Demo logins — hradmin/hradmin123 (HR Admin), manager/manager123 (Line Manager), "
            "employee/employee123 (Employee). Local development only."
        )
