import unittest
from pathlib import Path

from app.signals import enrich


class SignalsTests(unittest.TestCase):
    def test_unknown_is_not_denial(self):
        result = enrich({'descriptionPlain': 'Great engineering role'}, 'https://example.com')
        self.assertEqual(result['sponsorship']['status'], 'unknown')
        self.assertFalse(result['opt']['mentioned'])

    def test_negative_and_opt(self):
        result = enrich({'content': 'We cannot offer visa sponsorship. OPT candidates welcome.'}, 'url')
        self.assertEqual(result['sponsorship']['status'], 'not_offered')
        self.assertTrue(result['opt']['mentioned'])
        self.assertEqual(result['opt']['status'], 'unknown')

    def test_structured_salary(self):
        result = enrich({'compensation': {'summaryComponents': [
            {'compensationType': 'Salary', 'minValue': 100000, 'maxValue': 130000,
             'currencyCode': 'USD', 'interval': '1 YEAR'}]}}, 'url')
        self.assertEqual(result['salary']['ranges'][0]['min'], 100000)

    def test_text_salary_preserves_unknown_units(self):
        result = enrich({'content': 'Pay $100,000 - $130,000.'}, 'url')
        self.assertIsNone(result['salary']['ranges'][0]['interval'])
        self.assertIsNone(result['salary']['ranges'][0]['currency'])

    def test_fixed_salary(self):
        result = enrich({'content': 'The annual salary is $85,000 per year.'}, 'url')
        salary = result['salary']['ranges'][0]
        self.assertEqual((salary['min'], salary['max'], salary['kind']), (85000, 85000, 'fixed'))
        self.assertEqual(salary['interval'], 'year')

    def test_bonus_not_base_salary(self):
        result = enrich({'content': 'Salary includes a signing bonus of $10,000.'}, 'url')
        self.assertEqual(result['salary']['ranges'], [])

    def test_range_not_duplicated_as_fixed(self):
        result = enrich({'content': 'Annual salary $85,000 - $100,000 per year.'}, 'url')
        self.assertEqual(len(result['salary']['ranges']), 1)

    def test_nested_description(self):
        result = enrich({'_detail': {'jobAd': {'sections': {
            'qualifications': {'text': 'We cannot provide visa sponsorship.'}}}}}, 'url')
        self.assertTrue(result['description_available'])
        self.assertEqual(result['sponsorship']['status'], 'not_offered')

    def test_spelled_out_practical_training(self):
        result = enrich({'content': 'Optional practical training candidates may apply.'}, 'url')
        self.assertTrue(result['opt']['mentioned'])
        self.assertEqual(result['opt']['status'], 'unknown')

    def test_recidiviz_entry_level_actual_compensation_markup(self):
        content = (Path(__file__).parent / 'fixtures' / 'recidiviz_compensation.html').read_text()
        result = enrich({'content': content}, 'https://job-boards.greenhouse.io/recidiviz/jobs/4717510006')
        self.assertEqual(len(result['salary']['ranges']), 1)
        salary = result['salary']['ranges'][0]
        self.assertEqual((salary['min'], salary['max'], salary['kind']), (85000, 85000, 'fixed'))
        self.assertIsNone(salary['interval'])
        self.assertEqual(result['sponsorship']['status'], 'not_offered')

    def test_compensation_bonus_is_not_base_salary(self):
        result = enrich({'content': 'Compensation: signing bonus $85,000.'}, 'url')
        self.assertEqual(result['salary']['ranges'], [])

    def test_repeated_fixed_compensation_is_deduplicated(self):
        result = enrich({'content': 'Compensation: $85,000. Compensation: $85,000.'}, 'url')
        self.assertEqual(len(result['salary']['ranges']), 1)
        self.assertEqual(result['salary']['ranges'][0]['min'], 85000)
