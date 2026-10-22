import unittest

from app.entry_level import classify
from app.hunt import canonical_url, pay_filter


class IdentityTests(unittest.TestCase):
    def test_tracking_removed_but_job_id_kept(self):
        self.assertEqual(canonical_url('https://EXAMPLE.com/job/?utm_source=mail&gh_jid=123#apply'),
                         'https://example.com/job?gh_jid=123')
        self.assertNotEqual(canonical_url('https://example.com/job?id=123'),
                            canonical_url('https://example.com/job?id=124'))

    def test_non_web_url_rejected(self):
        with self.assertRaises(ValueError):
            canonical_url('javascript:alert(1)')

    def test_pay_periods_never_converted(self):
        query, args = pay_filter(70000, 'year', 'USD', True)
        self.assertIn('NOT EXISTS', query)
        self.assertIn('year', args['comp_units'])
        self.assertNotIn('hour', args['comp_units'])
        self.assertEqual(args['min_comp'], 70000)
        query, args = pay_filter(25, 'hour', 'USD', False)
        self.assertNotIn('NOT EXISTS', query)
        self.assertNotIn('year', args['comp_units'])


class EntryTests(unittest.TestCase):
    def test_plain_title_can_have_entry_evidence(self):
        entry, _ = classify('Requires 0 to 2 years of professional experience.')
        self.assertEqual(entry['status'], 'entry_evidence')

    def test_contradiction_needs_review(self):
        entry, _ = classify('Recent graduates welcome. Requires 5 years of professional experience.')
        self.assertEqual(entry['status'], 'review_required')

    def test_preferred_experience_does_not_override_entry(self):
        entry, _ = classify('Recent graduates welcome. Five years preferred.')
        self.assertEqual(entry['status'], 'entry_evidence')

    def test_unknown_not_entry(self):
        entry, _ = classify('Build our machine learning platform.')
        self.assertEqual(entry['status'], 'unknown')

    def test_start_is_not_graduation(self):
        _, starts = classify('Graduation March 2027. Start date: March 2027.')
        self.assertEqual(len(starts), 1)
        self.assertEqual(starts[0]['date'], '2027-03-01')
        self.assertEqual(starts[0]['precision'], 'month')

    def test_invalid_start_date_not_emitted(self):
        _, starts = classify('Start date: February 31, 2027.')
        self.assertEqual(starts, [])
