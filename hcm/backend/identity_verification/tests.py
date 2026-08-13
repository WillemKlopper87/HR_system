from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.test import TestCase
from rbac_audit.consent import record_consent
from rbac_audit.models import ConsentRecord

from .geo import OFFICE_GEOFENCE_RADIUS_M, haversine_distance_m
from .matching import DescriptorError, MATCH_THRESHOLD, euclidean_distance
from .models import BiometricEnrollment, LivenessCheck
from .services import (
    ConsentRequiredError,
    EnrollmentRequiredError,
    ReviewError,
    enroll_employee,
    resolve_review,
    run_liveness_check,
    weekly_office_attendance,
)


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(
        name="Head Office", code="HO", province=Location.Province.GAUTENG, latitude=-26.2041, longitude=28.0473
    )
    return dept, level, grade, location


def _hire(number, *, dept, level, grade, location):
    return Employee.objects.hire(
        employee_number=number, first_name="Alex", last_name="Employee", date_of_birth=date(1990, 1, 1),
        work_email=f"{number.lower()}@example.com", hire_date=date(2020, 1, 1),
        department=dept, occupational_level=level, job_grade=grade, location=location,
    )


def _consent(employee):
    record_consent(
        employee=employee, purpose=ConsentRecord.Purpose.BIOMETRIC,
        lawful_basis=ConsentRecord.LawfulBasis.CONSENT, text_version="v1",
    )


class MatchingTests(TestCase):
    def test_identical_vectors_have_zero_distance(self):
        self.assertEqual(euclidean_distance([0.0] * 128, [0.0] * 128), 0.0)

    def test_single_dimension_perturbation_within_threshold_matches(self):
        a = [0.1] * 128
        b = [0.1] * 127 + [0.1 + MATCH_THRESHOLD - 0.1]
        self.assertLess(euclidean_distance(a, b), MATCH_THRESHOLD)

    def test_wrong_length_descriptor_raises(self):
        with self.assertRaises(DescriptorError):
            euclidean_distance([0.0] * 127, [0.0] * 128)


class GeoTests(TestCase):
    def test_same_point_has_zero_distance(self):
        self.assertEqual(haversine_distance_m(-26.2041, 28.0473, -26.2041, 28.0473), 0.0)

    def test_johannesburg_to_cape_town_is_far_beyond_geofence(self):
        distance = haversine_distance_m(-26.2041, 28.0473, -33.9249, 18.4241)
        self.assertGreater(distance, OFFICE_GEOFENCE_RADIUS_M)
        # sanity: the real-world distance is roughly 1200-1300km
        self.assertGreater(distance, 1_000_000)


class EnrollAndCheckServiceTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()
        self.employee = _hire("E001", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        self.descriptor = [0.1] * 128

    def test_enroll_requires_consent(self):
        with self.assertRaises(ConsentRequiredError):
            enroll_employee(employee=self.employee, descriptor=self.descriptor)

    def test_enroll_succeeds_with_consent(self):
        _consent(self.employee)
        enrollment = enroll_employee(employee=self.employee, descriptor=self.descriptor)
        self.assertEqual(enrollment.employee, self.employee)

    def test_re_enrollment_overwrites_the_same_row(self):
        _consent(self.employee)
        enroll_employee(employee=self.employee, descriptor=self.descriptor)
        enroll_employee(employee=self.employee, descriptor=[0.2] * 128)
        self.assertEqual(BiometricEnrollment.objects.filter(employee=self.employee).count(), 1)
        self.assertEqual(BiometricEnrollment.objects.get(employee=self.employee).descriptor, [0.2] * 128)

    def test_check_requires_consent(self):
        with self.assertRaises(ConsentRequiredError):
            run_liveness_check(employee=self.employee, descriptor=self.descriptor)

    def test_check_requires_prior_enrollment(self):
        _consent(self.employee)
        with self.assertRaises(EnrollmentRequiredError):
            run_liveness_check(employee=self.employee, descriptor=self.descriptor)

    def test_matching_descriptor_produces_match_and_no_review_needed(self):
        _consent(self.employee)
        enroll_employee(employee=self.employee, descriptor=self.descriptor)
        close = self.descriptor[:127] + [self.descriptor[-1] + 0.3]
        check = run_liveness_check(employee=self.employee, descriptor=close)
        self.assertEqual(check.outcome, LivenessCheck.Outcome.MATCH)
        self.assertEqual(check.review_status, LivenessCheck.ReviewStatus.NOT_REQUIRED)

    def test_mismatching_descriptor_is_flagged_for_review(self):
        _consent(self.employee)
        enroll_employee(employee=self.employee, descriptor=self.descriptor)
        far = [0.9] * 128
        check = run_liveness_check(employee=self.employee, descriptor=far)
        self.assertEqual(check.outcome, LivenessCheck.Outcome.NO_MATCH)
        self.assertEqual(check.review_status, LivenessCheck.ReviewStatus.PENDING)

    def test_missing_descriptor_is_no_face_detected_and_flagged(self):
        _consent(self.employee)
        enroll_employee(employee=self.employee, descriptor=self.descriptor)
        check = run_liveness_check(employee=self.employee, descriptor=None)
        self.assertEqual(check.outcome, LivenessCheck.Outcome.NO_FACE_DETECTED)
        self.assertEqual(check.review_status, LivenessCheck.ReviewStatus.PENDING)

    def test_location_within_geofence_is_at_office(self):
        _consent(self.employee)
        enroll_employee(employee=self.employee, descriptor=self.descriptor)
        check = run_liveness_check(employee=self.employee, descriptor=self.descriptor, latitude=-26.2041, longitude=28.0473)
        self.assertTrue(check.at_office)
        self.assertEqual(check.distance_from_office_m, 0.0)

    def test_location_outside_geofence_is_not_at_office(self):
        _consent(self.employee)
        enroll_employee(employee=self.employee, descriptor=self.descriptor)
        check = run_liveness_check(employee=self.employee, descriptor=self.descriptor, latitude=-33.9249, longitude=18.4241)
        self.assertFalse(check.at_office)
        self.assertGreater(check.distance_from_office_m, OFFICE_GEOFENCE_RADIUS_M)

    def test_no_location_captured_leaves_at_office_unknown(self):
        _consent(self.employee)
        enroll_employee(employee=self.employee, descriptor=self.descriptor)
        check = run_liveness_check(employee=self.employee, descriptor=self.descriptor)
        self.assertIsNone(check.at_office)
        self.assertIsNone(check.distance_from_office_m)

    def test_office_location_without_geofence_configured_leaves_at_office_unknown(self):
        ungeofenced = Location.objects.create(name="Remote Site", code="RS", province=Location.Province.WESTERN_CAPE)
        other = _hire("E002", dept=self.dept, level=self.level, grade=self.grade, location=ungeofenced)
        _consent(other)
        enroll_employee(employee=other, descriptor=self.descriptor)
        check = run_liveness_check(employee=other, descriptor=self.descriptor, latitude=-26.2041, longitude=28.0473)
        self.assertIsNone(check.at_office)


class ReviewServiceTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()
        self.employee = _hire("E001", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        self.reviewer = _hire("HR1", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        _consent(self.employee)
        enroll_employee(employee=self.employee, descriptor=[0.1] * 128)
        self.flagged = run_liveness_check(employee=self.employee, descriptor=[0.9] * 128)

    def test_confirmed_mismatch_updates_review_fields(self):
        resolve_review(self.flagged, reviewer=self.reviewer, decision=LivenessCheck.ReviewStatus.CONFIRMED_MISMATCH, notes="Escalated")
        self.flagged.refresh_from_db()
        self.assertEqual(self.flagged.review_status, LivenessCheck.ReviewStatus.CONFIRMED_MISMATCH)
        self.assertEqual(self.flagged.reviewed_by, self.reviewer)
        self.assertIsNotNone(self.flagged.reviewed_at)
        self.assertEqual(self.flagged.review_notes, "Escalated")

    def test_cannot_review_a_non_pending_check(self):
        resolve_review(self.flagged, reviewer=self.reviewer, decision=LivenessCheck.ReviewStatus.CONFIRMED_MISMATCH)
        with self.assertRaises(ReviewError):
            resolve_review(self.flagged, reviewer=self.reviewer, decision=LivenessCheck.ReviewStatus.CONFIRMED_MATCH)

    def test_invalid_decision_value_is_rejected(self):
        with self.assertRaises(ReviewError):
            resolve_review(self.flagged, reviewer=self.reviewer, decision="not_a_real_decision")


class WeeklyAttendanceTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()
        self.employee = _hire("E001", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        _consent(self.employee)
        enroll_employee(employee=self.employee, descriptor=[0.1] * 128)

    def test_no_checks_means_not_compliant(self):
        summary = weekly_office_attendance(self.employee)
        self.assertEqual(summary["days_in_office"], 0)
        self.assertFalse(summary["compliant"])

    def test_one_in_office_day_still_short_of_two_required(self):
        run_liveness_check(employee=self.employee, descriptor=[0.1] * 128, latitude=-26.2041, longitude=28.0473)
        summary = weekly_office_attendance(self.employee)
        self.assertEqual(summary["days_in_office"], 1)
        self.assertFalse(summary["compliant"])

    def test_repeated_checks_same_day_count_once(self):
        run_liveness_check(employee=self.employee, descriptor=[0.1] * 128, latitude=-26.2041, longitude=28.0473)
        run_liveness_check(employee=self.employee, descriptor=[0.1] * 128, latitude=-26.2041, longitude=28.0473)
        summary = weekly_office_attendance(self.employee)
        self.assertEqual(summary["days_in_office"], 1)
