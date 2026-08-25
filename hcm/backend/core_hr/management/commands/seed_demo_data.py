from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core_hr.data_quality import run_data_quality_checks
from core_hr.exits import confirm_employment_change, propose_employment_change
from core_hr.models import (
    Department,
    Employee,
    EmployeeVersion,
    EmploymentChange,
    JobGrade,
    Location,
    OccupationalLevel,
)
from rbac_audit.consent import record_consent
from rbac_audit.models import ConsentRecord, Role, RoleAssignment

# Cross-module import exception: this command's whole job is seeding demo
# data across every module for local dev/UI review, not core_hr business
# logic — "apps may not import each other" (hcm/README.md) governs feature
# code, not a dev-tooling script that necessarily spans all of them.
from assessments.models import ProviderConfig
from assessments.services import assign_assessment, simulate_provider_completion
from compensation.models import Benefit, BenefitsElection, PayBand
from compensation.services import approve_proposal, propose_compensation_change, reject_proposal
from ee_reporting.constants import BARRIER_CATEGORIES
from ee_reporting.constants import OCCUPATIONAL_LEVEL_CODES as EE_LEVEL_CODES
from ee_reporting.models import EEPlan, EEQuestionnaire, EmployerConfig, RemunerationRecord
from ee_reporting.services import ee_manager_approve, generate_report, sign_off, submit_for_review
from establishment.models import PositionApprovalStep
from establishment.services import (
    backfill_positions_for_current_employees,
    decide_step,
    propose_position,
    submit_for_approval,
)
from performance.models import (
    AgreementTemplate,
    PerformanceAgreement,
    PerformancePeriod,
    PeriodPhase,
    TemplateElement,
    TemplateSection,
)
from performance.services import (
    approve_agreement,
    approve_feedback_360_rater,
    create_agreement,
    generate_agreements_for_period,
    nominate_feedback_360_rater,
    open_calibration_session,
    open_feedback_360_request,
    open_phase,
    publish_template,
    record_calibration_outcome,
    sign_agreement,
    submit_agreement,
    submit_feedback_360_response,
)
# Aliased: performance.services already owns `publish_template` for
# AgreementTemplate above -- this is onboarding.ChecklistTemplate's own
# publish action (C1 part 3 slice 3), an unrelated model.
from onboarding.models import ChecklistTemplate
from onboarding.services import complete_item as complete_checklist_item
from onboarding.services import create_template as create_checklist_template
from onboarding.services import publish_template as publish_checklist_template
from identity_verification.models import LivenessCheck
from identity_verification.services import enroll_employee, run_liveness_check
from learning.models import Certification, Course, CourseRequirement, EmployeeSkill, Skill, TrainingRecord
from performance.models import Feedback, Goal, Review, ReviewCycle
from performance.services import launch_review_cycle
from policies.models import Policy
from policies.services import acknowledge_policy, create_policy, publish_policy
from django.core.files.uploadedfile import SimpleUploadedFile
from recruitment.models import Applicant, BackgroundCheck, InterviewScorecard, InterviewSession, Offer, Requisition
from recruitment.services import submit_portal_application, transition_applicant
from succession.models import CriticalPost, SuccessionCandidate

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
    # name, code, province, latitude, longitude — coordinates are each
    # office's approximate real-world CBD location, used by
    # identity_verification's office-attendance geofence check.
    ("Head Office — Johannesburg", "JHB", "GP", -26.2041, 28.0473),
    ("Cape Town Office", "CPT", "WC", -33.9249, 18.4241),
    ("Durban Office", "DBN", "KZN", -29.8587, 31.0218),
    ("Pretoria Office", "PTA", "GP", -25.7479, 28.2293),
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
            locations = [
                Location.objects.create(name=n, code=c, province=p, latitude=lat, longitude=lng)
                for n, c, p, lat, lng in LOCATIONS
            ]
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

            # --- Onboarding/offboarding checklist templates (C1 part 3
            # slice 3) -- seeded and published BEFORE any employee below is
            # hired, so hire()'s automatic hook (core_hr/lifecycle_hooks.py)
            # actually creates an onboarding checklist for every one of
            # them, the same way a real HR team would have the process live
            # before day one rather than retrofitting it. created_by is
            # None here (no hr_admin employee exists yet at this point in
            # the script) -- perfectly valid, that field is nullable.
            onboarding_template = create_checklist_template(
                name="Standard onboarding", direction=ChecklistTemplate.Direction.ONBOARDING,
                items=[
                    {"label": "Issue laptop and access card", "owner_role": "it",
                     "description": "Provision a laptop, building access card and VPN account."},
                    {"label": "Set up payroll and banking details", "owner_role": "hr",
                     "description": "Confirm banking details and enrol on the payroll run."},
                    {"label": "Introduce to line manager and team", "owner_role": "line_manager",
                     "description": "First-week introductions and a walkthrough of team norms."},
                    {"label": "Book induction / orientation session", "owner_role": "hr"},
                    {"label": "Confirm workstation and required software", "owner_role": "it"},
                ],
            )
            publish_checklist_template(onboarding_template, actor=None)

            offboarding_template = create_checklist_template(
                name="Standard offboarding", direction=ChecklistTemplate.Direction.OFFBOARDING,
                items=[
                    {"label": "Collect laptop, access card and other assets", "owner_role": "it",
                     "description": "Confirm all issued equipment is returned and in working order."},
                    {"label": "Revoke building and system access", "owner_role": "it"},
                    {"label": "Conduct exit interview", "owner_role": "hr"},
                    {"label": "Confirm final pay and outstanding leave", "owner_role": "hr"},
                    {"label": "Handover notes to line manager", "owner_role": "line_manager"},
                ],
            )
            publish_checklist_template(offboarding_template, actor=None)

            def hire(*, department, level, location, manager, hire_date, employment_status=None, contract_end_date=None):
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
                    employment_status=employment_status,
                    contract_end_date=contract_end_date,
                    race=_weighted_choice(RACE_WEIGHTS, rng),
                    gender=_weighted_choice(GENDER_WEIGHTS, rng),
                    disability_status=_weighted_choice(DISABILITY_WEIGHTS, rng),
                    race_source="hr_captured",
                    disability_source="hr_captured",
                )
                RoleAssignment.objects.create(employee=employee, role=base_role)
                return employee

            ceo = hire(department=exec_dept, level=top_level, location=locations[0], manager=None, hire_date=date(2015, 1, 1))
            # Independent oversight function, reports to nobody in the org
            # chart on purpose (same as the CEO) -- an auditor's read access
            # spans every department, so it isn't scoped under one.
            auditor_employee = hire(
                department=exec_dept, level=senior_level, location=locations[0], manager=None, hire_date=date(2019, 1, 1)
            )

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

            # A SECOND hr_admin, so the four-eyes control on suspensions and
            # dismissals (C1 part 3, spec §4.2 -- confirmed_by must differ from
            # proposed_by) is actually demonstrable. With one hr_admin seeded,
            # every tiered change is proposable but unconfirmable, so the
            # control could only ever be seen failing.
            hr_second = next(
                (v.employee for v in hr_head.direct_reports.filter(valid_to__isnull=True).select_related("employee")),
                None,
            )
            if hr_second is not None:
                RoleAssignment.objects.create(employee=hr_second, role=hr_admin_role)
                hr_second.user = User.objects.create_user(username="hradmin2", password="hradmin123")
                hr_second.save(update_fields=["user"])

            eng_head = dept_heads[dept_codes.index("ENG")]
            RoleAssignment.objects.create(employee=eng_head, role=line_manager_role)
            eng_head.user = User.objects.create_user(username="manager", password="manager123")
            eng_head.save(update_fields=["user"])

            report_version = eng_head.direct_reports.filter(valid_to__isnull=True).select_related("employee").first()
            staff = None
            if report_version is not None:
                staff = report_version.employee
                staff.user = User.objects.create_user(username="employee", password="employee123")
                staff.save(update_fields=["user"])

            recruiter_role = Role.objects.get(name="recruiter")
            slm_head = dept_heads[dept_codes.index("SLM")]
            RoleAssignment.objects.create(employee=slm_head, role=recruiter_role)
            slm_head.user = User.objects.create_user(username="recruiter", password="recruiter123")
            slm_head.save(update_fields=["user"])

            comp_manager_role = Role.objects.get(name="comp_manager")
            fin_head = dept_heads[dept_codes.index("FIN")]
            RoleAssignment.objects.create(employee=fin_head, role=comp_manager_role)
            fin_head.user = User.objects.create_user(username="compmanager", password="compmanager123")
            fin_head.save(update_fields=["user"])

            ee_manager_role = Role.objects.get(name="ee_manager")
            ops_head = dept_heads[dept_codes.index("OPS")]
            RoleAssignment.objects.create(employee=ops_head, role=ee_manager_role)
            ops_head.user = User.objects.create_user(username="eemanager", password="eemanager123")
            ops_head.save(update_fields=["user"])

            # CEO doubles as the PFMA Accounting Officer for sign-off
            # purposes (EEA-Form-Spec-Notes.md) — the same person, not a
            # separate seeded employee, matching how the form itself
            # names the role "Chief Executive Officer/Accounting Officer".
            accounting_officer_role = Role.objects.get(name="accounting_officer")
            RoleAssignment.objects.create(employee=ceo, role=accounting_officer_role)
            ceo.user = User.objects.create_user(username="accountingofficer", password="accountingofficer123")
            ceo.save(update_fields=["user"])

            auditor_role = Role.objects.get(name="auditor")
            RoleAssignment.objects.create(employee=auditor_employee, role=auditor_role)
            auditor_employee.user = User.objects.create_user(username="auditor", password="auditor123")
            auditor_employee.save(update_fields=["user"])

            # --- Contract end-date tracking & renewal decisions (C1 part 2) --
            # Two of eng_head's direct reports, fixed-term with a
            # contract_end_date set -- nothing in the random hire() loop
            # above ever sets employment_status/contract_end_date, so
            # without these /contract-renewals (and its e2e coverage,
            # Task 6) would have no rows to exercise the recommend/decide
            # flow against. Distinct first names keep e2e row locators
            # unambiguous even though both share a last name.
            eng_dept = other_depts[dept_codes.index("ENG")]
            contract_renewal_employee = hire(
                department=eng_dept, level=mid_level, location=locations[0], manager=eng_head,
                hire_date=date(2023, 6, 1),
                employment_status=EmployeeVersion.EmploymentStatus.FIXED_TERM,
                contract_end_date=timezone.localdate() + timedelta(days=45),
            )
            contract_renewal_employee.first_name = "Renewal"
            contract_renewal_employee.last_name = "Contractor"
            contract_renewal_employee.save(update_fields=["first_name", "last_name"])

            contract_lapse_employee = hire(
                department=eng_dept, level=mid_level, location=locations[0], manager=eng_head,
                hire_date=date(2023, 6, 1),
                employment_status=EmployeeVersion.EmploymentStatus.FIXED_TERM,
                contract_end_date=timezone.localdate() + timedelta(days=20),
            )
            contract_lapse_employee.first_name = "Lapse"
            contract_lapse_employee.last_name = "Contractor"
            contract_lapse_employee.save(update_fields=["first_name", "last_name"])

            demo_requisitions = self._seed_recruitment_demo_data(
                departments=departments, levels=levels, grades_by_level=grades_by_level,
                locations=locations, recruiter=slm_head, interviewers=[eng_head, ops_head], rng=rng,
            )

            self._seed_performance_demo_data(manager=eng_head, direct_report=staff)
            self._seed_learning_demo_data(manager=eng_head, direct_report=staff, rng=rng)
            self._seed_compensation_demo_data(
                levels=levels, grades_by_level=grades_by_level, comp_manager=fin_head,
                hr_admin=hr_head, direct_report=staff, rng=rng,
            )
            self._seed_assessments_demo_data(
                ee_manager=ops_head, hr_admin=hr_head, recruiter=slm_head, direct_report=staff, second_employee=eng_head,
            )
            self._seed_identity_verification_demo_data(direct_report=staff, rng=rng)
            self._seed_ee_reporting_demo_data(
                hr_admin=hr_head, ee_manager=ops_head, accounting_officer=ceo, levels=levels, rng=rng,
            )
            self._seed_ess_demo_data(direct_report=staff)
            self._seed_policies_demo_data(hr_admin=hr_head, direct_report=staff, rng=rng)
            self._seed_performance_agreements_demo_data(hr_admin=hr_head, head=eng_head, staff=staff, rng=rng)
            self._seed_calibration_and_feedback360_demo_data(
                hr_admin=hr_head, employee=fin_head, head=ceo, peer=ops_head,
            )
            # LAST, once every employee exists: establishment.migrations.
            # 0002 ran its backfill against an empty database (correctly
            # creating nothing), so without this every fresh demo/e2e
            # environment has zero Positions and both seeded requisitions
            # sit unlinked -- the exact pre-C1 state this feature replaces.
            self._seed_establishment_demo_data(requisitions=demo_requisitions, hr_admin=hr_head)
            self._seed_onboarding_demo_data(
                hr_admin=hr_head, manager=eng_head, staff=staff,
                department=eng_dept, level=mid_level, grade=grades_by_level[mid_level.code][0],
                location=locations[0],
            )
            self._seed_succession_demo_data(hr_admin=hr_head, eng_head=eng_head, staff=staff, fin_head=fin_head)

        run_data_quality_checks()

        self.stdout.write(self.style.SUCCESS(f"Seeded {employee_counter} employees across {len(departments)} departments."))
        self.stdout.write(
            "Demo logins — hradmin/hradmin123 (HR Admin), hradmin2/hradmin123 (second HR Admin, "
            "for two-person confirmation), manager/manager123 (Line Manager), "
            "recruiter/recruiter123 (Recruiter), compmanager/compmanager123 (Comp Manager), "
            "eemanager/eemanager123 (EE Manager), accountingofficer/accountingofficer123 (Accounting Officer), "
            "auditor/auditor123 (Auditor), employee/employee123 (Employee). Local development only."
        )

    def _seed_recruitment_demo_data(self, *, departments, levels, grades_by_level, locations, recruiter, interviewers, rng):
        """A handful of requisitions/applicants spanning the pipeline —
        including one carried all the way through transition_applicant to
        HIRED, so the demo shows the Sprint 4 acceptance criterion (hire
        creates an employees row) with real seeded data, not just tests.

        C6: also seeds a scheduled interview session with two scorecards
        (one already submitted, so /my-interviews has a real blind-review
        example on first login), two background checks, `eng_req` flagged
        externally postable, and one portal-sourced applicant so
        submit_portal_application's whole path is demoable, not just tested.

        Returns the two requisitions so _seed_establishment_demo_data can
        link real approved posts to them once every employee exists (C1)."""
        eng_dept = next(d for d in departments if d.code == "ENG")
        fin_dept = next(d for d in departments if d.code == "FIN")
        junior_level = levels[-1]
        mid_level = levels[len(levels) // 2]
        grade = grades_by_level[junior_level.code][0]

        eng_req = Requisition.objects.create(
            title="Backend Engineer", department=eng_dept, occupational_level=junior_level, job_grade=grade,
            location=locations[0], headcount=2, status=Requisition.Status.OPEN,
            opened_at=date(2026, 6, 1), created_by=recruiter, external_posting=True,
            description=(
                "We're growing the platform team and looking for a backend engineer comfortable across the stack. "
                "You'll work closely with product and design to ship features end to end, in a small, senior team."
            ),
        )
        fin_req = Requisition.objects.create(
            title="Financial Analyst", department=fin_dept, occupational_level=mid_level,
            job_grade=grades_by_level[mid_level.code][0], location=locations[0],
            headcount=1, status=Requisition.Status.OPEN, opened_at=date(2026, 7, 1), created_by=recruiter,
        )

        Applicant.objects.create(
            requisition=eng_req, first_name="Nomsa", last_name="Khumalo",
            email="nomsa.khumalo@applicant-demo.example", date_of_birth=date(1996, 4, 12),
        )
        interviewing = Applicant.objects.create(
            requisition=eng_req, first_name="Werner", last_name="Botha",
            email="werner.botha@applicant-demo.example", date_of_birth=date(1993, 9, 2),
        )
        for stage in (Applicant.Stage.SCREENED, Applicant.Stage.INTERVIEW):
            transition_applicant(interviewing, to_stage=stage, actor=recruiter)

        session = InterviewSession.objects.create(
            applicant=interviewing, round_number=1,
            scheduled_at=timezone.make_aware(datetime(2026, 8, 20, 10, 0)),
            duration_minutes=45, location="Boardroom 2", status=InterviewSession.Status.COMPLETED,
            notes="Technical + culture-fit round.", created_by=recruiter,
        )
        session.interviewers.set(interviewers)
        # Only the first interviewer has scored so far -- a real,
        # demoable example of blind-review masking (design spec §2.2): log
        # in as the second interviewer's account and their peer's score is
        # still hidden until they submit their own.
        InterviewScorecard.objects.create(
            session=session, interviewer=interviewers[0], skill_rating=4, communication_rating=5,
            culture_fit_rating=4, recommendation=InterviewScorecard.Recommendation.HIRE,
            comments="Strong technical fundamentals, communicates clearly.",
        )
        BackgroundCheck.objects.create(
            applicant=interviewing, check_type=BackgroundCheck.CheckType.REFERENCE,
            status=BackgroundCheck.Status.IN_PROGRESS, requested_by=recruiter,
            requested_at=timezone.now(), notes="Awaiting response from second listed referee.",
        )

        with_offer = Applicant.objects.create(
            requisition=fin_req, first_name="Aisha", last_name="Cassim",
            email="aisha.cassim@applicant-demo.example", date_of_birth=date(1991, 11, 20),
        )
        for stage in (Applicant.Stage.SCREENED, Applicant.Stage.INTERVIEW, Applicant.Stage.OFFER):
            transition_applicant(with_offer, to_stage=stage, actor=recruiter)
        Offer.objects.create(
            applicant=with_offer, proposed_job_grade=grades_by_level[mid_level.code][0],
            proposed_annual_salary="420000.00", proposed_by=recruiter,
        )
        BackgroundCheck.objects.create(
            applicant=with_offer, check_type=BackgroundCheck.CheckType.CRIMINAL_RECORD,
            status=BackgroundCheck.Status.CLEARED, requested_by=recruiter,
            requested_at=timezone.now() - timedelta(days=5), completed_at=timezone.now(),
            notes="No record found. Cleared for offer.",
        )

        to_hire = Applicant.objects.create(
            requisition=eng_req, first_name="Sibusiso", last_name="Mahlangu",
            email="sibusiso.mahlangu@applicant-demo.example", date_of_birth=date(1994, 2, 8),
        )
        record_consent(
            applicant=to_hire, purpose=ConsentRecord.Purpose.DEMOGRAPHIC_SELF_ID,
            lawful_basis=ConsentRecord.LawfulBasis.CONSENT, text_version="v1", actor=recruiter,
        )
        to_hire.race = _weighted_choice(RACE_WEIGHTS, rng)
        to_hire.gender = _weighted_choice(GENDER_WEIGHTS, rng)
        to_hire.disability_status = _weighted_choice(DISABILITY_WEIGHTS, rng)
        to_hire.save(update_fields=["race", "gender", "disability_status"])
        for stage in (Applicant.Stage.SCREENED, Applicant.Stage.INTERVIEW, Applicant.Stage.OFFER, Applicant.Stage.HIRED):
            transition_applicant(to_hire, to_stage=stage, actor=recruiter, hire_date=date(2026, 8, 1))

        rejected = Applicant.objects.create(
            requisition=fin_req, first_name="Johan", last_name="van Wyk",
            email="johan.vanwyk@applicant-demo.example", date_of_birth=date(1989, 6, 15),
        )
        transition_applicant(
            rejected, to_stage=Applicant.Stage.REJECTED, actor=recruiter, rejected_reason="Not enough relevant experience"
        )

        # Careers portal (C6): a real self-application through the same
        # public path a genuine anonymous visitor would use, against the
        # requisition flagged external_posting=True above.
        submit_portal_application(
            requisition=eng_req, first_name="Naledi", last_name="Dlamini",
            email="naledi.dlamini@portal-demo.example", phone="0821234567", date_of_birth=date(1997, 3, 14),
            resume=SimpleUploadedFile(
                "naledi-dlamini-cv.pdf", b"%PDF-1.7\nDemo CV content for Naledi Dlamini.",
                content_type="application/pdf",
            ),
            race=_weighted_choice(RACE_WEIGHTS, rng), gender=_weighted_choice(GENDER_WEIGHTS, rng),
            disability_status=_weighted_choice(DISABILITY_WEIGHTS, rng), demographic_consent=True,
        )

        return [eng_req, fin_req]

    # --- Position / establishment control (C1) ------------------------------

    def _seed_establishment_demo_data(self, *, requisitions, hr_admin):
        """One approved Position per currently-employed person — the same
        idempotent backfill establishment/migrations/0002 wraps, run here
        because that migration executed against an empty database — and
        then real approved posts behind the seeded requisitions, so the
        Positions page, the vacancy-rate stats, and the recruiter's
        position picker all have live data in a fresh environment."""
        backfilled = backfill_positions_for_current_employees()

        linked = 0
        for requisition in requisitions:
            positions = self._positions_for_requisition(requisition, hr_admin=hr_admin)
            requisition.positions.set(positions)
            linked += len(positions)

        self.stdout.write(
            f"Seeded establishment control: {backfilled} positions backfilled from current employees, "
            f"{linked} linked across {len(requisitions)} demo requisitions."
        )

    def _seed_onboarding_demo_data(self, *, hr_admin, manager, staff, department, level, grade, location):
        """C1 part 3 slice 3: the onboarding template published earlier
        (before any employee was hired) already gave every seeded employee,
        `staff` included, an active onboarding checklist via hire()'s
        automatic hook -- nothing to create there. This method:

        1. Ticks off a couple of `staff`'s onboarding tasks, so
           /checklists shows a mix of done/not-done rather than either
           extreme.
        2. Hires one throwaway employee and immediately resigns them
           (propose -> confirm, which executes at once since resignation
           is a routine, proposer-confirms type effective today) so the
           offboarding hook actually fires and /checklists has a real
           offboarding example to show, not just onboarding ones."""
        if staff is not None:
            onboarding = staff.checklists.filter(direction=ChecklistTemplate.Direction.ONBOARDING).first()
            if onboarding is not None:
                for item in onboarding.items.all()[:2]:
                    complete_checklist_item(item, actor=manager, notes="Done in first week.")

        leaver = Employee.objects.hire(
            employee_number="E90001", first_name="Departing", last_name="Demo",
            date_of_birth=date(1988, 3, 12), work_email="departing.demo@sentech-demo.example",
            hire_date=date(2021, 1, 1), department=department, occupational_level=level,
            job_grade=grade, location=location, manager=manager,
        )
        change = propose_employment_change(
            leaver, actor=hr_admin, change_type=EmploymentChange.ChangeType.RESIGNATION,
            effective_date=timezone.localdate(), reason="Accepted a role elsewhere; resignation on notice.",
        )
        confirm_employment_change(change, actor=hr_admin)

        self.stdout.write(
            "Seeded onboarding/offboarding checklists: 'Standard onboarding' and 'Standard offboarding' "
            "published; a demo resignation shows the offboarding checklist created automatically."
        )

    def _seed_succession_demo_data(self, *, hr_admin, eng_head, staff, fin_head):
        """C6: two critical posts, one with a successor in the pipeline and
        one without -- so /talent-pools has a real example of each shape,
        and the CRITICAL_POST_NO_SUCCESSOR data-quality check (run at the
        end of handle()) has something genuine to flag rather than an empty
        list. Runs after _seed_establishment_demo_data, which is what gives
        every seeded employee (eng_head, fin_head included) an approved
        Position to flag."""
        eng_position = eng_head.current_version.position
        if eng_position is not None:
            eng_critical = CriticalPost.objects.create(
                position=eng_position, reason="Sole technical authority for platform architecture; no documented backup.",
                flagged_by=hr_admin,
            )
            if staff is not None:
                SuccessionCandidate.objects.create(
                    critical_post=eng_critical, employee=staff,
                    readiness=SuccessionCandidate.Readiness.READY_1_2_YEARS,
                    notes="Strong technical growth this year; needs stakeholder-management exposure before ready.",
                    nominated_by=hr_admin,
                )

        fin_position = fin_head.current_version.position
        if fin_position is not None:
            CriticalPost.objects.create(
                position=fin_position,
                reason="Signs off every compensation proposal; single point of failure on payroll compliance.",
                flagged_by=hr_admin,
            )

        self.stdout.write(
            "Seeded succession planning: 2 critical posts flagged (one with a ready-in-1-2-years successor, "
            "one with none yet, on purpose -- demonstrates the data-quality check)."
        )

    def _positions_for_requisition(self, requisition, *, hr_admin):
        """Exactly `headcount` posts: the ones this requisition's completed
        hires already occupy, topped up with freshly approved vacant ones.

        Linking a hire's own backfilled post (the same rule
        recruitment.services.backfill_requisition_positions applies to
        historical closed requisitions) is what keeps the design spec's
        §4.3 invariant true in the demo data: "all linked positions
        occupied" stays the same fact as "hired_count >= headcount". Every
        backfilled position is occupied by definition — it was backfilled
        FROM its occupant — so the still-open seats need brand-new posts,
        which also gives the recruiter's picker something genuinely vacant
        to offer."""
        positions = []
        hired = requisition.applicants.filter(
            current_stage=Applicant.Stage.HIRED, resulting_employee__isnull=False
        ).select_related("resulting_employee")
        for applicant in hired:
            version = applicant.resulting_employee.current_version
            if version is not None and version.position is not None:
                positions.append(version.position)

        while len(positions) < requisition.headcount:
            positions.append(self._approve_new_position(requisition=requisition, hr_admin=hr_admin))
        return positions[: requisition.headcount]

    def _approve_new_position(self, *, requisition, hr_admin):
        """Walked through the real configured approval chain rather than
        created pre-approved, so the demo's Positions page shows a genuine
        PositionApprovalStep audit trail instead of posts that appeared
        from nowhere."""
        position = propose_position(
            title=requisition.title, department=requisition.department,
            occupational_level=requisition.occupational_level, job_grade=requisition.job_grade,
            location=requisition.location, actor=hr_admin,
        )
        submit_for_approval(position, actor=hr_admin)
        for role_name in settings.POSITION_APPROVAL_CHAIN:
            decide_step(
                position, actor=self._employee_with_role(role_name),
                decision=PositionApprovalStep.Decision.APPROVED,
                comment=f"Approved on the establishment for '{requisition.title}'.",
            )
        return position

    @staticmethod
    def _employee_with_role(role_name):
        """Whoever actually holds the role in this seeded org — looked up,
        not hardcoded, so a deployment running a different
        POSITION_APPROVAL_CHAIN still records a real actor. None if nobody
        holds it; establishment/services.py doesn't require an actor."""
        assignment = (
            RoleAssignment.objects.filter(role__name=role_name, revoked_at__isnull=True)
            .select_related("employee")
            .first()
        )
        return assignment.employee if assignment else None

    def _seed_performance_demo_data(self, *, manager, direct_report):
        """Launches one review cycle against the full seeded workforce (so
        the completion dashboard has a realistic denominator), then
        completes just a couple of reviews — showing the dashboard as HR
        would actually see it mid-cycle, not 0% or 100%."""
        cycle = ReviewCycle.objects.create(
            name="2026 Annual Review", cycle_type=ReviewCycle.CycleType.ANNUAL,
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
        )
        launch_review_cycle(cycle)

        manager_review = Review.objects.get(review_cycle=cycle, employee=manager)
        manager_review.self_rating = 4
        manager_review.self_comments = "Strong delivery quarter over quarter."
        manager_review.self_submitted_at = timezone.now()
        manager_review.save()

        if direct_report is not None:
            report_review = Review.objects.get(review_cycle=cycle, employee=direct_report)
            report_review.self_rating = 4
            report_review.self_comments = "Met all sprint commitments."
            report_review.self_submitted_at = timezone.now()
            report_review.manager_rating = 4
            report_review.manager_comments = "Consistently reliable, ready for more scope."
            report_review.manager_submitted_at = timezone.now()
            report_review.save()

            Goal.objects.create(
                employee=direct_report, manager=manager, title="Lead the Q3 migration project",
                description="Own planning and delivery end to end.", target_date=date(2026, 9, 30),
                status=Goal.Status.ACTIVE, created_by=manager,
            )
            Goal.objects.create(
                employee=direct_report, manager=manager, title="Complete AWS certification",
                target_date=date(2026, 6, 30), status=Goal.Status.ACTIVE, created_by=direct_report,
            )
            Feedback.objects.create(
                employee=direct_report, author=manager, feedback_type=Feedback.FeedbackType.MANAGER,
                text="Great job unblocking the team during the outage last sprint.",
            )

    def _seed_learning_demo_data(self, *, manager, direct_report, rng):
        """A skill catalog + assignments spread across a slice of the
        workforce, not just the two named demo employees — so the skills
        inventory (gap analysis by department/level) and WSP/ATR export
        (Documentation-Review-and-Gap-Analysis.md gap C2) have something
        realistic to show."""
        skills = [
            Skill.objects.create(name="Python", category=Skill.Category.TECHNICAL),
            Skill.objects.create(name="Project Management", category=Skill.Category.LEADERSHIP),
            Skill.objects.create(name="Public Speaking", category=Skill.Category.SOFT),
            Skill.objects.create(name="AWS", category=Skill.Category.TECHNICAL),
            Skill.objects.create(name="Data Analysis", category=Skill.Category.TECHNICAL),
            Skill.objects.create(name="POPIA Compliance", category=Skill.Category.COMPLIANCE),
        ]

        all_employees = list(Employee.objects.all())
        sampled = rng.sample(all_employees, min(25, len(all_employees)))
        for employee in sampled:
            for skill in rng.sample(skills, rng.randint(1, 3)):
                EmployeeSkill.objects.get_or_create(
                    employee=employee, skill=skill,
                    defaults={"proficiency": rng.choice(EmployeeSkill.Proficiency.values)},
                )

        if direct_report is not None:
            Certification.objects.create(
                employee=direct_report, name="AWS Certified Solutions Architect",
                issuing_body="Amazon Web Services", issue_date=date(2025, 6, 1), expiry_date=date(2028, 6, 1),
            )
            TrainingRecord.objects.create(
                employee=direct_report, title="AWS Solutions Architect Bootcamp", provider="A Cloud Guru",
                status=TrainingRecord.Status.COMPLETED, start_date=date(2026, 2, 1),
                completion_date=date(2026, 3, 1), hours="40.0", cost="8500.00",
            )
            TrainingRecord.objects.create(
                employee=direct_report, title="Advanced Python for Data Engineers", provider="Internal L&D",
                status=TrainingRecord.Status.IN_PROGRESS, start_date=date(2026, 7, 1), hours="16.0",
            )

        # --- C6: mandatory-training compliance -- course catalogue +
        # requirement rules, with a deliberate mix of compliant/overdue
        # people so the dashboard, the row-scoped overdue list, and the
        # data-quality sweep all have something real to show.
        today = timezone.localdate()
        popia_course = Course.objects.create(
            name="POPIA Awareness Refresher", provider="Internal L&D", hours="2.0", mandatory=True,
            validity_days=365,
        )
        safety_course = Course.objects.create(
            name="Workplace Safety Induction", provider="Internal L&D", hours="4.0", mandatory=True,
        )
        Course.objects.create(name="Advanced Excel", provider="Internal L&D", hours="8.0", mandatory=False)

        # Org-wide: everyone must have a current POPIA refresher.
        CourseRequirement.objects.create(
            course=popia_course, effective_from=today - timedelta(days=400), due_within_days=90,
        )
        # Department-scoped: only manager's own department (Engineering)
        # must complete the safety induction -- exercises the by-department
        # breakdown and the row-scoped overdue list's department-narrower
        # population, distinct from the org-wide rule above.
        eng_dept = manager.current_version.department
        CourseRequirement.objects.create(
            course=safety_course, department=eng_dept, effective_from=today - timedelta(days=200),
            due_within_days=60,
        )

        if direct_report is not None:
            # Compliant on the org-wide course, overdue on the department
            # one -- both states visible for the one demo employee whose
            # login (employee/employee123) e2e coverage drives directly.
            TrainingRecord.objects.create(
                employee=direct_report, course=popia_course, title=popia_course.name, provider=popia_course.provider,
                status=TrainingRecord.Status.COMPLETED, completion_date=today - timedelta(days=30), hours="2.0",
            )

        # A realistic completion rate on the org-wide course: roughly a
        # third of the sampled workforce slice is compliant, the rest sit
        # overdue (the rule's effective_from is far enough in the past
        # that due_within_days has already elapsed for everyone).
        for employee in sampled:
            if employee is direct_report:
                continue
            if rng.random() < 0.35:
                TrainingRecord.objects.create(
                    employee=employee, course=popia_course, title=popia_course.name,
                    provider=popia_course.provider, status=TrainingRecord.Status.COMPLETED,
                    completion_date=today - timedelta(days=rng.randint(10, 300)), hours="2.0",
                )

    def _seed_compensation_demo_data(self, *, levels, grades_by_level, comp_manager, hr_admin, direct_report, rng):
        """Pay bands scaled by seniority (order 1 = top management = highest
        pay), plus a spread of comp proposals across every workflow state
        (pending, approved in-band, approved out-of-band with an override
        reason, rejected) so the Sprint 10-11 propose/approve UI has
        something real to show rather than an empty state. One grade gets
        two bands (an expired one and the current one) to demonstrate the
        effective-dated pattern (PayBand.objects.current())."""
        for level in levels:
            base = max(180000, 1400000 - (level.order - 1) * 220000)
            for i, grade in enumerate(grades_by_level[level.code]):
                mid = base + i * 60000
                PayBand.objects.create(
                    job_grade=grade, min_salary=round(mid * 0.75, -3), mid_salary=mid, max_salary=round(mid * 1.25, -3),
                    valid_from=date(2024, 1, 1), created_by=comp_manager,
                )

        first_grade = grades_by_level[levels[0].code][0]
        PayBand.objects.filter(job_grade=first_grade, valid_from=date(2024, 1, 1)).update(valid_to=date(2025, 12, 31))
        current_mid = max(180000, 1400000 - (levels[0].order - 1) * 220000) * 1.15
        PayBand.objects.create(
            job_grade=first_grade, min_salary=round(current_mid * 0.75, -3), mid_salary=round(current_mid, -3),
            max_salary=round(current_mid * 1.25, -3), valid_from=date(2026, 1, 1), created_by=comp_manager,
        )

        benefits = [
            Benefit.objects.create(name="Discovery Health Medical Aid", category=Benefit.Category.MEDICAL),
            Benefit.objects.create(name="Bonitas Medical Aid", category=Benefit.Category.MEDICAL),
            Benefit.objects.create(name="Sentech Provident Fund", category=Benefit.Category.RETIREMENT),
            Benefit.objects.create(name="Group Life & Disability Cover", category=Benefit.Category.RISK_COVER),
        ]
        all_employees = list(Employee.objects.all())
        sampled = rng.sample(all_employees, min(30, len(all_employees)))
        for employee in sampled:
            for benefit in rng.sample(benefits, rng.randint(1, 2)):
                BenefitsElection.objects.get_or_create(
                    employee=employee, benefit=benefit,
                    defaults={
                        "status": _weighted_choice(
                            [(BenefitsElection.Status.ENROLLED, 0.8), (BenefitsElection.Status.WAIVED, 0.2)], rng
                        ),
                        "effective_date": date(2024, 1, 1),
                    },
                )

        proposal_candidates = [e for e in sampled if e.current_version and e.current_version.job_grade_id][:4]
        if direct_report is not None and direct_report not in proposal_candidates:
            proposal_candidates = [direct_report] + proposal_candidates
        proposal_candidates = proposal_candidates[:4]

        def _band_for(employee):
            return PayBand.objects.filter(job_grade=employee.current_version.job_grade).current().first()

        if len(proposal_candidates) >= 1:
            band = _band_for(proposal_candidates[0])
            out_of_band_salary = (band.max_salary * 2) if band else Decimal("1500000")
            propose_compensation_change(
                employee=proposal_candidates[0], proposed_annual_salary=out_of_band_salary,
                justification="Market benchmarking shows this role is under-banded relative to peers.",
                proposed_by=comp_manager,
            )
        if len(proposal_candidates) >= 2:
            band = _band_for(proposal_candidates[1])
            in_band_salary = band.mid_salary if band else Decimal("400000")
            approved_in_band = propose_compensation_change(
                employee=proposal_candidates[1], proposed_annual_salary=in_band_salary,
                justification="Annual merit increase.", proposed_by=comp_manager,
            )
            approve_proposal(approved_in_band, approver=hr_admin)
        if len(proposal_candidates) >= 3:
            band = _band_for(proposal_candidates[2])
            out_of_band_salary = (band.max_salary * Decimal("1.5")) if band else Decimal("2000000")
            approved_override = propose_compensation_change(
                employee=proposal_candidates[2], proposed_annual_salary=out_of_band_salary,
                justification="Retention counter-offer.", proposed_by=comp_manager,
            )
            approve_proposal(approved_override, approver=hr_admin, override_reason="Approved by Exco — retention risk.")
        if len(proposal_candidates) >= 4:
            band = _band_for(proposal_candidates[3])
            in_band_salary = band.min_salary if band else Decimal("220000")
            rejected = propose_compensation_change(
                employee=proposal_candidates[3], proposed_annual_salary=in_band_salary,
                justification="Requested adjustment.", proposed_by=comp_manager,
            )
            reject_proposal(rejected, approver=hr_admin)

    def _seed_assessments_demo_data(self, *, ee_manager, hr_admin, recruiter, direct_report, second_employee):
        """One pending employee-subject assignment (so the demo login can
        see an in-flight assessment and, as ee_manager/hr_admin, trigger
        simulate_completion live), one already-completed employee-subject
        assignment (so there's a real result to look at immediately), and
        one completed applicant-subject assignment against the recruitment
        pipeline's mid-stage candidate — exercising the exact same
        consent -> assign -> webhook pipeline the tests do, just seeded
        instead of scripted."""
        ProviderConfig.objects.get_or_create(
            provider_key="sandbox", defaults={"display_name": "Sandbox (local dev)", "active": True}
        )

        if direct_report is not None:
            record_consent(
                employee=direct_report, purpose=ConsentRecord.Purpose.ASSESSMENT,
                lawful_basis=ConsentRecord.LawfulBasis.CONSENT, text_version="v1", actor=ee_manager,
            )
            assign_assessment(
                employee=direct_report, assessment_type="cognitive", assigned_by=ee_manager,
            )

        record_consent(
            employee=second_employee, purpose=ConsentRecord.Purpose.ASSESSMENT,
            lawful_basis=ConsentRecord.LawfulBasis.CONSENT, text_version="v1", actor=hr_admin,
        )
        completed = assign_assessment(employee=second_employee, assessment_type="personality", assigned_by=hr_admin)
        simulate_provider_completion(completed)

        applicant = Applicant.objects.filter(email="werner.botha@applicant-demo.example").first()
        if applicant is not None:
            record_consent(
                applicant=applicant, purpose=ConsentRecord.Purpose.ASSESSMENT,
                lawful_basis=ConsentRecord.LawfulBasis.CONSENT, text_version="v1", actor=recruiter,
            )
            applicant_assignment = assign_assessment(
                applicant_id=applicant.id, assessment_type="technical", assigned_by=recruiter,
            )
            simulate_provider_completion(applicant_assignment)

    def _seed_identity_verification_demo_data(self, *, direct_report, rng):
        """Enrolls a sample of employees (fake random descriptors — not
        tied to any real face) with a spread of this-week check-in history,
        so MyIdentityVerificationPage has real data for the 'employee'
        demo login and WorkforceIntegrityPage's attendance table shows a
        realistic mix of compliant/non-compliant employees. One check for
        the direct_report is deliberately built from a mismatched
        descriptor and left pending, so the hr_admin review queue isn't
        empty in a fresh demo."""
        all_employees = list(Employee.objects.all())
        sampled = rng.sample(all_employees, min(15, len(all_employees)))
        if direct_report is not None and direct_report not in sampled:
            sampled = [direct_report] + sampled[:14]

        today = timezone.localdate()
        week_start = today - timedelta(days=today.weekday())

        for employee in sampled:
            record_consent(
                employee=employee, purpose=ConsentRecord.Purpose.BIOMETRIC,
                lawful_basis=ConsentRecord.LawfulBasis.CONSENT, text_version="v1",
            )
            descriptor = [rng.uniform(-1.0, 1.0) for _ in range(128)]
            enroll_employee(employee=employee, descriptor=descriptor)

            version = employee.current_version
            office = version.location if version is not None else None
            has_geofence = office is not None and office.latitude is not None and office.longitude is not None

            available_weekdays = min(today.weekday() + 1, 5)
            num_checkins = rng.choice([0, 1, 1, 2, 3])
            checkin_days = rng.sample(range(available_weekdays), min(num_checkins, available_weekdays))
            for day_offset in checkin_days:
                close_descriptor = [v + rng.uniform(-0.05, 0.05) for v in descriptor]
                lat = float(office.latitude) if has_geofence else None
                lng = float(office.longitude) if has_geofence else None
                check = run_liveness_check(employee=employee, descriptor=close_descriptor, latitude=lat, longitude=lng)
                checkin_at = timezone.make_aware(datetime.combine(week_start + timedelta(days=day_offset), time(9, 0)))
                LivenessCheck.objects.filter(pk=check.pk).update(created_at=checkin_at)

        if direct_report is not None:
            flagged_descriptor = [rng.uniform(-1.0, 1.0) for _ in range(128)]
            run_liveness_check(employee=direct_report, descriptor=flagged_descriptor)

    def _seed_ee_reporting_demo_data(self, *, hr_admin, ee_manager, accounting_officer, levels, rng):
        """Employer config (Section A) + a current-year questionnaire + a
        2025-2030 EE plan, then remuneration for every current employee
        scaled off their real pay band (not flat, so the median/gap
        stats and highest/lowest-paid figures look real) — enough for
        EEA2 AND EEA4 to both pass validate_report_readiness(). One EEA2
        is walked all the way to signed_off (a realistic "what does a
        finished report look like" demo); its EEA4 sibling is left in
        draft so the submit/review/sign-off UI has something actionable
        to demo live."""
        report_year = 2026
        period_start, period_end = date(2026, 1, 1), date(2026, 12, 31)

        EmployerConfig.objects.create(
            trade_name="Sentech SOC Ltd",
            dti_registration_name="Sentech SOC Limited",
            dti_registration_number="1996/025054/30",
            paye_sars_number="7530196842",
            uif_reference_number="U123456789",
            ee_reference_number="E123456",
            national_or_provincial_eap="National",
            industry_sector="Telecommunications",
            seta_classification="MICT SETA",
            telephone_number="0113141000",
            postal_address="PO Box 21, Honeydew", postal_code="2040", postal_city="Johannesburg",
            postal_province=Location.Province.GAUTENG,
            physical_address="Octave Building, 320 Sentech Road, Honeydew", physical_code="2040",
            physical_city="Johannesburg", physical_province=Location.Province.GAUTENG,
            ceo_name=f"{accounting_officer.first_name} {accounting_officer.last_name}",
            ceo_telephone="0113141001", ceo_email=accounting_officer.work_email,
            ee_senior_manager_name=f"{hr_admin.first_name} {hr_admin.last_name}",
            ee_senior_manager_telephone="0113141002", ee_senior_manager_email=hr_admin.work_email,
            business_type="state_owned_enterprise", is_organ_of_state=True,
            employee_count_band="150_or_more",
        )

        barriers = {
            key: {
                "barriers": i < 6,
                "aa_measures": i < 6,
                "start_date": "2026-01-01" if i < 6 else None,
                "end_date": "2026-12-31" if i < 6 else None,
            }
            for i, (key, _label) in enumerate(BARRIER_CATEGORIES)
        }
        EEQuestionnaire.objects.create(
            report_year=report_year,
            achieved_all_targets=False,
            justifiable_reasons={
                "TOP": ["insufficient_target_individuals"],
                "SENIOR": ["insufficient_promotion_opportunities"],
                "disability": ["insufficient_recruitment_opportunities"],
            },
            consultation={
                "consultative_body_or_ee_forum": True, "representative_trade_unions": True, "employees": True,
            },
            barriers=barriers,
            monitoring_frequency="quarterly",
            achieved_annual_objectives=True,
            achieved_annual_objectives_explanation=(
                "Met 4 of 5 annual numerical targets; disability representation remains the outstanding gap."
            ),
            has_remuneration_policy=True,
            remuneration_gap_aligned_to_policy=True,
            has_measures_in_ee_plan=True,
            differential_reason="seniority_length_of_service",
            updated_by=hr_admin,
        )

        EEPlan.objects.create(
            plan_period_start=date(2025, 1, 1), plan_period_end=date(2030, 12, 31),
            sector_targets={
                "TOP": {"african_male": 8, "african_female": 6, "white_male": 3, "white_female": 2},
                "SENIOR": {"african_male": 10, "african_female": 8, "white_male": 4, "white_female": 3},
                "PQ": {"african_male": 14, "african_female": 12, "white_male": 3, "white_female": 3},
                "SKILLED": {"african_male": 20, "african_female": 18, "white_male": 3, "white_female": 3},
            },
            numerical_goals={
                "SEMI": {"african_male": 30, "african_female": 28},
                "UNSKILLED": {"african_male": 32, "african_female": 30},
            },
            disability_5yr_target_pct=Decimal("3.0"),
            annual_targets={
                level: {
                    "african_male": 22, "african_female": 20, "coloured_male": 5, "coloured_female": 4,
                    "indian_male": 2, "indian_female": 1, "white_male": 6, "white_female": 5,
                    "foreign_national_male": 1, "foreign_national_female": 1,
                }
                for level in EE_LEVEL_CODES
            },
            annual_target_disability_value=15, annual_target_disability_pct=Decimal("2.5"),
            created_by=hr_admin,
        )

        for employee in Employee.objects.all():
            version = employee.current_version
            if version is None:
                continue
            band = PayBand.objects.filter(job_grade=version.job_grade).current().first() if version.job_grade else None
            base = float(band.mid_salary) if band else 250000.0
            fixed = int(round(base * rng.uniform(0.85, 1.15), -2))
            variable = int(round(fixed * rng.uniform(0.0, 0.15), -2))
            RemunerationRecord.objects.create(
                employee=employee, period_start=period_start, period_end=period_end,
                fixed_remuneration=fixed, variable_remuneration=variable, imported_by=hr_admin,
            )

        eea2 = generate_report(
            form_type="eea2", report_year=report_year, period_start=period_start, period_end=period_end, actor=hr_admin,
        )
        submit_for_review(eea2, actor=hr_admin)
        ee_manager_approve(eea2, actor=ee_manager)
        sign_off(eea2, actor=accounting_officer, place="Johannesburg")

        # Left in draft on purpose — the demo login can exercise
        # submit_for_review/ee_review/sign_off live instead of finding
        # every report already finished.
        generate_report(
            form_type="eea4", report_year=report_year, period_start=period_start, period_end=period_end, actor=hr_admin,
        )

    def _seed_ess_demo_data(self, *, direct_report):
        """Sprint 15 (ESS): deliberately light-touch — the 'employee' demo
        login's own profile contact details and self-ID are left untouched
        (empty/not-consented) so MyProfilePage has something real to fill
        in live, not just a page confirming already-seeded data renders.
        One REQUESTED training record and a guaranteed benefits election
        are the only pre-seeded rows, so My Learning/My Benefits aren't
        empty on first login either."""
        if direct_report is None:
            return

        TrainingRecord.objects.create(
            employee=direct_report, title="Certified Kubernetes Administrator", provider="Linux Foundation",
            status=TrainingRecord.Status.REQUESTED,
        )

        if not BenefitsElection.objects.filter(employee=direct_report).exists():
            benefit = Benefit.objects.filter(active=True).first()
            if benefit is not None:
                BenefitsElection.objects.create(
                    employee=direct_report, benefit=benefit, status=BenefitsElection.Status.ENROLLED,
                    effective_date=date(2024, 1, 1),
                )

    def _seed_policies_demo_data(self, *, hr_admin, direct_report, rng):
        """Three published policies with a realistic acknowledgment spread
        (not 0% or 100%, so the compliance dashboard looks real), one
        created from an uploaded text file to genuinely exercise the
        extraction/chunking path (not just typed body text), and one
        policy deliberately left in DRAFT so hr_admin has something
        actionable to publish live. The 'employee' demo login has
        acknowledged one policy and left another outstanding, so
        MyPoliciesPage shows both states on first login."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        conduct = create_policy(
            title="Code of Conduct",
            category=Policy.Category.CODE_OF_CONDUCT,
            body=(
                "All Sentech employees are expected to act with honesty, integrity, and respect toward "
                "colleagues, clients, and the public. Conflicts of interest must be disclosed to your manager "
                "or HR as soon as they arise. Company property and information must be used responsibly and "
                "never for personal gain. Violations may result in disciplinary action up to and including "
                "dismissal, in line with the Labour Relations Act."
            ),
            effective_date=date(2024, 1, 1), actor=hr_admin,
        )
        publish_policy(conduct, actor=hr_admin)

        leave_body = (
            "Employees accrue annual leave at 1.25 days per completed month of service (15 days per year), "
            "in line with the Basic Conditions of Employment Act minimum. Leave must be requested at least "
            "two weeks in advance where possible and approved by your line manager. Sick leave follows a "
            "36-month cycle entitlement; a medical certificate is required for absences longer than two "
            "consecutive days. Unused annual leave may be carried over by written agreement with HR, up to "
            "a maximum of 5 days."
        )
        leave_upload = SimpleUploadedFile("leave-policy.txt", leave_body.encode("utf-8"), content_type="text/plain")
        leave = create_policy(
            title="Leave Policy", category=Policy.Category.LEAVE, file=leave_upload,
            effective_date=date(2024, 1, 1), actor=hr_admin,
        )
        publish_policy(leave, actor=hr_admin)

        popia = create_policy(
            title="POPIA / Data Privacy Policy",
            category=Policy.Category.POPIA_PRIVACY,
            body=(
                "Sentech processes personal information strictly for legitimate HR, payroll, and Employment "
                "Equity reporting purposes, in line with the Protection of Personal Information Act (POPIA). "
                "Special personal information — race, gender, disability status, and biometric data — is only "
                "captured with explicit consent, recorded and auditable. Employees may request access to, "
                "correction of, or deletion of their own personal information at any time by contacting HR."
            ),
            effective_date=date(2024, 6, 1), actor=hr_admin,
        )
        publish_policy(popia, actor=hr_admin)

        create_policy(
            title="Remote Work Policy",
            category=Policy.Category.REMOTE_WORK,
            body=(
                "Employees may work remotely up to 3 days per week with manager approval, subject to the "
                "2-day minimum in-office requirement tracked via the Workforce Integrity module. Draft — "
                "pending final sign-off from Exco."
            ),
            actor=hr_admin,
        )  # left in DRAFT deliberately — hr_admin's live "publish" demo

        all_employees = list(Employee.objects.all())
        conduct_ackers = [e for e in rng.sample(all_employees, min(100, len(all_employees))) if e != direct_report]
        for employee in conduct_ackers:
            acknowledge_policy(conduct, employee=employee)

        popia_ackers = [direct_report] + [
            e for e in rng.sample(all_employees, min(60, len(all_employees))) if e != direct_report
        ]
        for employee in popia_ackers:
            if employee is not None:
                acknowledge_policy(popia, employee=employee)
        # `leave` is left with zero acknowledgments — freshly published,
        # nobody's gotten to it yet; a third realistic completion state.

    # --- Performance agreements / KPI contracting (PC-1, ADR-010) -----------

    def _seed_performance_agreements_demo_data(self, *, hr_admin, head, staff, rng):
        """A live FY 2026/27 contracting round, mid-flight on purpose:

        the period is OPEN (so the reminder job has something to do), one
        published template shaped like the real Sentech scorecard (three
        corporate objectives -> KPA -> weighted KPIs whose weights total
        100%, each with all five target descriptors), an agreement for every
        employee, and a deliberate spread of states — most still in draft
        (the realistic "nobody has done it yet" starting point the whole
        reminder feature exists for), a few submitted/approved awaiting
        signature, a few fully agreed — so every dashboard number and every
        button has a real case behind it. The `employee` demo login's own
        agreement is left in DRAFT so a demo can walk the whole flow.
        """
        period = PerformancePeriod.objects.create(
            name="2026/27", start_date=date(2026, 4, 1), end_date=date(2027, 3, 31), created_by=hr_admin,
        )
        # The FY windows the user described: contract in April, review at Q2,
        # assess after year end.
        PeriodPhase.objects.create(
            period=period, stage=PeriodPhase.Stage.CONTRACTING, opens_on=date(2026, 4, 1),
            due_on=date(2026, 4, 30), reminder_offsets_days=[28, 14, 7, 1], overdue_every_days=7,
        )
        PeriodPhase.objects.create(
            period=period, stage=PeriodPhase.Stage.MIDYEAR, opens_on=date(2026, 9, 1),
            due_on=date(2026, 9, 30), reminder_offsets_days=[14, 7, 1], overdue_every_days=7,
        )
        PeriodPhase.objects.create(
            period=period, stage=PeriodPhase.Stage.FINAL, opens_on=date(2027, 4, 1),
            due_on=date(2027, 4, 30), reminder_offsets_days=[14, 7, 1], overdue_every_days=7,
        )

        template = AgreementTemplate.objects.create(
            name="Sentech Individual Scorecard", version=1, period=period, created_by=hr_admin,
        )
        # Objectives are the corporate strategy of the year (they changed between
        # the two real workbooks — hence versioned templates).
        scorecard = [
            ("DRIVE SUSTAINABLE GROWTH", [
                ("Financial Sustainability", "Diversified (new) revenue growth", "ZAR", Decimal("0.20"), [
                    "No new revenue", "Less than R1m", "R1m", "R1.5m", "R2m",
                ]),
                ("Cost efficiency", "Operating cost variance against budget", "%", Decimal("0.10"), [
                    "Over budget by >10%", "Over budget by up to 10%", "On budget",
                    "Under budget by up to 5%", "Under budget by more than 5%",
                ]),
            ]),
            ("DELIVER RELIABLE CUSTOMER-CENTRIC SERVICES", [
                ("Enabling new offerings", "Handover of commercially ready services to the business unit",
                 "Deadline", Decimal("0.20"), [
                     "Not handed over", "Handover by March 2027", "Handover by December 2026",
                     "Handed over by November 2026", "Handed over by September 2026",
                 ]),
                ("Service availability", "Network availability against SLA", "%", Decimal("0.15"), [
                    "Below 99.0%", "99.0%", "99.5%", "99.8%", "99.9%+",
                ]),
            ]),
            ("BUILD FUTURE-READY AND TRUSTED ORGANISATION", [
                ("Innovation & AI delivery", "Hybrid broadband-broadcast platform and services",
                 "Feasibility studies / pilots", Decimal("0.20"), [
                     "Conceptualisation and planning started", "Device and platform partner onboarded",
                     "Demo deployment of platform and services", "Commercialisation model approved",
                     "100 customers onboarded",
                 ]),
                ("People development", "Training and development plan achieved", "Quantitative",
                 Decimal("0.15"), [
                     "No training done", "One training initiative completed", "Two completed",
                     "Three completed", "More than three completed",
                 ]),
            ]),
        ]
        for section_order, (title, elements) in enumerate(scorecard):
            section = TemplateSection.objects.create(template=template, title=title, order=section_order)
            for order, (kpa, kpi, metric, weight, descriptors) in enumerate(elements):
                TemplateElement.objects.create(
                    template=template, section=section, kpa_description=kpa, kpi_title=kpi, metric=metric,
                    default_weight=weight, order=order,
                    level_descriptors={str(i + 1): text for i, text in enumerate(descriptors)},
                )
        publish_template(template, actor=hr_admin)

        open_phase(period, PeriodPhase.Stage.CONTRACTING, actor=hr_admin)
        result = generate_agreements_for_period(period, actor=hr_admin)

        # Spread the states. Everything else stays in draft — which is exactly
        # the situation the reminder engine is built for.
        agreements = list(
            PerformanceAgreement.objects.filter(period=period)
            .exclude(employee=staff)
            .exclude(head__isnull=True)
            .select_related("employee", "head")[:24]
        )
        rng.shuffle(agreements)
        # Only demo *logins* can actually sign (signing re-authenticates a
        # password); bulk-generated employees have no user account, so put the
        # pairs that can complete the whole flow at the front.
        agreements.sort(key=lambda a: (a.employee.user_id is None or a.head.user_id is None))
        for agreement in agreements[:8]:
            try:
                submit_agreement(agreement, actor=agreement.employee)
            except Exception:  # noqa: BLE001 - demo data only; a missing head just stays draft
                continue
        for agreement in agreements[:5]:
            try:
                approve_agreement(agreement, actor=agreement.head)
            except Exception:  # noqa: BLE001
                continue
        # Fully agreed ones need real signatures, so the demo has genuine
        # signed PDFs (hash and all), not fabricated status rows.
        for agreement in agreements[:3]:
            try:
                sign_agreement(agreement, actor=agreement.employee, role="employee",
                               password=self._password_for(agreement.employee))
                sign_agreement(agreement, actor=agreement.head, role="head",
                               password=self._password_for(agreement.head))
            except Exception:  # noqa: BLE001
                continue

        self.stdout.write(
            f"Seeded performance period {period.name}: {result['created']} agreements "
            f"({PerformanceAgreement.objects.filter(period=period, status='agreed').count()} signed, "
            f"{PerformanceAgreement.objects.filter(period=period, status='draft').count()} still to do)."
        )

    def _seed_calibration_and_feedback360_demo_data(self, *, hr_admin, employee, head, peer):
        """C6: calibration/moderation + 360 feedback (design spec 2026-08-25-
        performance-calibration-360-design.md). A SECOND, already-elapsed FY
        (2025/26) exists purely so /calibration and /my-feedback-requests have
        something real to show, without touching the main 2026/27 period's
        carefully-curated draft/submitted/approved/agreed spread above --
        opening mid-year/final on that period would sweep every AGREED
        agreement there into the new stage as a side effect, which would
        contradict its own "a few fully agreed" narrative. `employee`/`head`
        are demo logins (fin_head/compmanager under ceo/accountingofficer),
        real accounts so the whole flow -- including the two password
        signatures -- is genuinely reproducible, not faked.

        Deliberately left mid-flow, not fully wrapped up: the 360 round has
        self + manager responses in (both automatic slots) but the one
        nominated peer hasn't responded yet -- exactly the state a demo login
        as that peer (`eemanager`) can walk forward, and it demonstrates the
        aggregate's >=3-response floor (design spec §2.10) genuinely not
        being met yet, the realistic starting point, not a finished example.
        """
        period = PerformancePeriod.objects.create(
            name="2025/26", start_date=date(2025, 4, 1), end_date=date(2026, 3, 31), created_by=hr_admin,
        )
        for stage, opens_on, due_on in [
            (PeriodPhase.Stage.CONTRACTING, date(2025, 4, 1), date(2025, 4, 30)),
            (PeriodPhase.Stage.MIDYEAR, date(2025, 9, 1), date(2025, 9, 30)),
            (PeriodPhase.Stage.FINAL, date(2026, 4, 1), date(2026, 4, 30)),
        ]:
            PeriodPhase.objects.create(period=period, stage=stage, opens_on=opens_on, due_on=due_on)

        template = AgreementTemplate.objects.create(
            name="Calibration Demo Scorecard", version=1, period=period, created_by=hr_admin,
        )
        section = TemplateSection.objects.create(template=template, title="ORGANISATIONAL PERFORMANCE", order=0)
        descriptors_a = {"1": "Over budget by >10%", "2": "Over budget", "3": "On budget", "4": "Under budget", "5": "Well under budget"}
        descriptors_b = {"1": "Missed", "2": "Partially met", "3": "Met", "4": "Exceeded", "5": "Significantly exceeded"}
        TemplateElement.objects.create(
            template=template, section=section, kpa_description="Financial management", kpi_title="Budget variance",
            metric="%", default_weight=Decimal("0.6"), order=0, level_descriptors=descriptors_a,
        )
        TemplateElement.objects.create(
            template=template, section=section, kpa_description="Delivery", kpi_title="Departmental plan delivery",
            metric="Milestones", default_weight=Decimal("0.4"), order=1, level_descriptors=descriptors_b,
        )
        publish_template(template, actor=hr_admin)

        open_phase(period, PeriodPhase.Stage.CONTRACTING, actor=hr_admin)
        agreement = create_agreement(period=period, employee=employee, template=template, actor=hr_admin)
        submit_agreement(agreement, actor=employee)
        approve_agreement(agreement, actor=head)
        sign_agreement(agreement, actor=employee, role="employee", password=self._password_for(employee))
        sign_agreement(agreement, actor=head, role="head", password=self._password_for(head))

        open_phase(period, PeriodPhase.Stage.MIDYEAR, actor=hr_admin)
        agreement.refresh_from_db()
        sign_agreement(agreement, actor=employee, role="employee", password=self._password_for(employee))
        sign_agreement(agreement, actor=head, role="head", password=self._password_for(head))

        open_phase(period, PeriodPhase.Stage.FINAL, actor=hr_admin)
        agreement.refresh_from_db()
        for element in agreement.elements.all():
            element.final_rating = 4
            element.save(update_fields=["final_rating"])
        sign_agreement(agreement, actor=employee, role="employee", password=self._password_for(employee))
        sign_agreement(agreement, actor=head, role="head", password=self._password_for(head))
        agreement.refresh_from_db()

        # Calibration: hr_admin reviews the (org-wide, single-agreement)
        # cohort and records the realistic common case -- "reviewed, no
        # change needed" -- not an adjustment. The audit trail (session +
        # reason) exists either way.
        session = open_calibration_session(
            period=period, department=None, actor=hr_admin, meeting_date=date(2026, 5, 15),
            participants_note="Department heads + HR Admin",
        )
        record_calibration_outcome(
            session, agreement, actor=hr_admin,
            reason="Consistent with the rest of the organisation's rating distribution this year.",
        )

        # 360: self + manager slots are automatic and both respond; one
        # nominated peer is approved but left un-responded on purpose (see
        # docstring).
        feedback_request = open_feedback_360_request(agreement, actor=hr_admin)
        self_slot = feedback_request.raters.get(relationship="self")
        manager_slot = feedback_request.raters.get(relationship="manager")
        submit_feedback_360_response(
            self_slot, actor=employee, collaboration_rating=4, communication_rating=4, reliability_rating=4,
            strengths="Delivers consistently and communicates blockers early.",
            development_areas="Could delegate more of the budget review to the team.",
        )
        submit_feedback_360_response(
            manager_slot, actor=head, collaboration_rating=4, communication_rating=5, reliability_rating=4,
            strengths="Excellent cross-functional partner, always prepared for exec meetings.",
        )
        peer_slot = nominate_feedback_360_rater(feedback_request, peer, actor=employee)
        approve_feedback_360_rater(peer_slot, actor=head)

        self.stdout.write(
            f"Seeded calibration/360 demo: {period.name} agreement final-signed for "
            f"{employee.employee_number}, one calibration outcome recorded (no change), 360 round open with "
            f"self+manager responded and one peer ({peer.employee_number}) approved awaiting response."
        )

    @staticmethod
    def _password_for(employee):
        """Demo logins are `username` + '123' (see the login banner); employees
        generated in bulk have no user account, so signing them is skipped."""
        if employee.user is None:
            return None
        return f"{employee.user.get_username()}123"
