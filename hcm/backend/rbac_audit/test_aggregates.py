from django.test import SimpleTestCase

from .aggregates import percentage, suppress_count, suppress_related_counts


class AggregateSuppressionTests(SimpleTestCase):
    def test_complementary_suppression_prevents_subtraction_attack(self):
        displayed, suppressed = suppress_related_counts(
            {"small": 1, "large": 9, "empty": 0}, suppress=True
        )
        self.assertTrue(suppressed)
        self.assertEqual(displayed, {"small": "<5", "large": "Suppressed", "empty": 0})

    def test_authorised_result_is_unchanged(self):
        displayed, suppressed = suppress_related_counts({"small": 1, "large": 9}, suppress=False)
        self.assertFalse(suppressed)
        self.assertEqual(displayed, {"small": 1, "large": 9})

    def test_suppressed_numerator_never_returns_an_exact_percentage(self):
        self.assertIsNone(percentage(1, 10, numerator_suppressed=True))
        self.assertEqual(percentage(5, 10, numerator_suppressed=False), 50.0)
        self.assertEqual(suppress_count(1, suppress=True), "<5")
