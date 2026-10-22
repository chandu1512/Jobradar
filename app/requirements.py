"""Posting requirements for review, never a personalized eligibility verdict."""
import re


def screen(text):
    sentences = re.split(r'(?<=[.!?;])\s+|[\r\n]+', text)
    checks = {
        'experience': (r'\b\d{1,2}\s*(?:\+|(?:[-–]|to)\s*\d{1,2})?\s+years?\s+(?:of\s+)?'
                       r'(?:professional|relevant|industry|work|related|software|engineering|experience)'),
        'doctoral_degree': r'\bPh\.?D\.?\b|\bdoctor(?:al|ate)\b',
        'work_authorization': r'\bITAR\b|\bU\.?S\.?\s+(?:citizen|person)|\bsecurity clearance\b|\bexport.control',
        'enrollment': (r'\b(?:currently|actively)\s+enrolled\b|\breturn(?:ing)?\s+to\s+'
                       r'(?:school|university|college)\b|\b(?:pursuing|enrolled in)\s+'
                       r'(?:a |an )?(?:degree|bachelor|master|Ph|doctor)'),
        'graduation_window': (r'\bgraduat(?:e|es|ed|ing|ion)\b.{0,100}\b20\d{2}\b'
                              r'|\b20\d{2}\b.{0,60}\bgraduat(?:e|ing|ion)\b'),
    }
    findings = []
    for sentence in sentences:
        for kind, pattern in checks.items():
            if not re.search(pattern, sentence, re.I):
                continue
            # Preserve alternatives and preferences instead of inferring a hard requirement.
            qualification = ('preferred' if re.search(r'\bprefer(?:red|ably)?\b|nice.to.have|a plus', sentence, re.I)
                             else 'alternative' if re.search(r'\bor\b|equivalent', sentence, re.I)
                             else 'stated')
            item = {'type': kind, 'qualification': qualification, 'evidence': sentence[:1000]}
            if item not in findings:
                findings.append(item)
    return {'status': 'review_required' if findings else 'unknown',
            'description_available': bool(text), 'findings': findings[:20],
            'note': ('Requirements are posting evidence, not a decision that you qualify. '
                     'Preferences and alternatives need review.')}
