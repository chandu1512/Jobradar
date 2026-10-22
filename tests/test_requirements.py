import unittest

from app.requirements import screen


class RequirementTests(unittest.TestCase):
    def test_plain_title_does_not_establish_eligibility(self):
        self.assertEqual(screen('')['status'], 'unknown')
        self.assertEqual(screen('We build machine learning systems.')['status'], 'unknown')

    def test_experience(self):
        result = screen('Requires 3–5 years of professional experience.')
        self.assertEqual(result['findings'][0]['type'], 'experience')

    def test_degree_alternatives_not_phd_only(self):
        result = screen('Bachelor degree or PhD in computer science.')
        self.assertEqual(result['findings'][0]['qualification'], 'alternative')

    def test_preference_not_requirement(self):
        result = screen('PhD preferred.')
        self.assertEqual(result['findings'][0]['qualification'], 'preferred')

    def test_enrollment_and_graduation(self):
        result = screen('Must be currently enrolled and returning to school. '
                        'Graduation between Spring 2027 and Fall 2027.')
        self.assertEqual({f['type'] for f in result['findings']}, {'enrollment', 'graduation_window'})

    def test_itar_is_review_flag_not_citizenship_verdict(self):
        result = screen('This position is subject to ITAR export control requirements.')
        self.assertEqual(result['findings'][0]['type'], 'work_authorization')
        self.assertNotIn('eligible', result)

    def test_experience_written_range(self):
        result = screen('Minimum 3 to 5 years of industry experience required.')
        self.assertEqual(result['findings'][0]['type'], 'experience')
