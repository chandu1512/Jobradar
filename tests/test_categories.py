import unittest

from fastapi import HTTPException

from app.api import _filters, categories
from app.categories import annotate, classify

CASES = {
    'Senior Machine Learning Engineer': {'ai_ml'},
    'AI/ML Engineer': {'ai_ml'},
    'Software Engineer, AI Platform': {'software', 'ai_ml'},
    'Data Analyst': {'data_analysis'},
    'Business Intelligence Analyst': {'data_analysis'},
    'Data Scientist': {'data_science'},
    'Data Engineer': {'data_engineering'},
    'Frontend Developer': {'software'},
    'Site Reliability Engineer': {'devops_cloud'},
    'Security Engineer': {'security'},
    'QA Engineer': {'qa'},
    'Product Manager': {'product'},
    'UX Designer': {'design'},
    'Embedded Software Engineer': {'software', 'hardware'},
    'Account Executive': {'sales'},
    'Marketing Manager': {'marketing'},
    'Financial Analyst': {'finance'},
    'Technical Recruiter': {'hr'},
    'Supply Chain Analyst': {'operations'},
    'Registered Nurse, RN': {'healthcare'},
    'Customer Success Manager': {'support'},
    'Math Teacher': {'education'},
    'Legal Counsel': {'legal'},
    'HVAC Technician': {'trades'},
    'Retail Associate': set(),
    'Email Campaign Specialist': set(),
}


class CategoryTests(unittest.TestCase):
    def test_representative_titles_and_word_boundaries(self):
        for title, expected in CASES.items():
            with self.subTest(title=title):
                self.assertEqual(set(classify(title)), expected)

    def test_filter_combines_with_existing_filters(self):
        where, args = _filters('engineer', '', 'NY', True, True, 'newgrad', 24, 'ai_ml')
        self.assertIn('j.title ~* %(category_pattern)s', where)
        self.assertIn('j.is_us', where)
        self.assertIn('j.remote', where)
        self.assertEqual(args['states'], ['NY'])
        self.assertIn('lvl', args)
        self.assertEqual(args['q'], '%engineer%')

    def test_company_filter_combines_with_category(self):
        where, args = _filters("engineer", "", "", True, False, "", 24, "software", "Stripe")
        self.assertIn("c.name ILIKE %(company)s", where)
        self.assertEqual(args["company"], "%Stripe%")
        self.assertIn("category_pattern", args)

    def test_unknown_category_rejected(self):
        with self.assertRaises(HTTPException) as error:
            _filters('', '', '', True, False, '', 24, 'unknown')
        self.assertEqual(error.exception.status_code, 422)

    def test_all_categories_default(self):
        _, args = _filters('', '', '', True, False, '', 24)
        self.assertNotIn('category_pattern', args)

    def test_labels_and_stream_annotations_share_category_ids(self):
        ids = {row['id'] for row in categories()}
        row = annotate([{'id': 1, 'title': 'AI Software Engineer'}])[0]
        self.assertEqual(row['categories'], ['ai_ml', 'software'])
        self.assertTrue(set(row['categories']) <= ids)
        self.assertEqual(row['id'], 1)
