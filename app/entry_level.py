"""Description evidence for early-career discovery, not an eligibility guarantee."""
import re
from datetime import date

MONTHS = {name.lower(): i for i, name in enumerate(
    ['January','February','March','April','May','June','July','August','September','October','November','December'], 1)}


def classify(text):
    evidence, conflicts, starts = [], [], []
    for sentence in re.split(r'(?<=[.!?;])\s+', text):
        snippet = sentence[:1000]
        if re.search(r'\b(recent graduates?|new[ -]grads?|early[ -]career|entry[ -]level|graduate program)\b'
                     r'|\bno (?:prior |professional |work )?experience (?:is )?required\b', sentence, re.I):
            evidence.append(snippet)
        for match in re.finditer(r'\b(\d{1,2})\s*(?:[-–]|to)\s*(\d{1,2})\s+years?\s+(?:of\s+)?'
                                 r'(?:experience|professional|relevant|industry|work)', sentence, re.I):
            if int(match[1]) <= 2 and int(match[2]) <= 2:
                evidence.append(snippet)
        if not re.search(r'\bpreferred\b|nice.to.have|a plus', sentence, re.I):
            for match in re.finditer(r'\b(\d{1,2})\s*(?:\+|[-–]\s*\d{1,2})?\s+years?\s+(?:of\s+)?'
                                     r'(?:experience|professional|relevant|industry|work)', sentence, re.I):
                if int(match[1]) >= 3:
                    conflicts.append(snippet)
        # Only dates explicitly tied to starting employment, not graduation windows.
        pattern = (r'\b(?:start(?:ing)?(?: date)?|begin(?:ning)?)\s*(?:is|:|in|on|by)?\s*'
                   r'(' + '|'.join(MONTHS) + r')\s+(?:(\d{1,2}),?\s+)?(20\d{2})\b')
        for match in re.finditer(pattern, sentence, re.I):
            try:
                value = date(int(match[3]), MONTHS[match[1].lower()], int(match[2] or 1))
            except ValueError:
                continue
            starts.append({'date': value.isoformat(), 'precision': 'day' if match[2] else 'month',
                           'evidence': snippet})
    return {'status': ('review_required' if evidence and conflicts else 'entry_evidence' if evidence else 'unknown'),
            'evidence': list(dict.fromkeys(evidence))[:8],
            'conflicting_experience': list(dict.fromkeys(conflicts))[:8]}, starts
