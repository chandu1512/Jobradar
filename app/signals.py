"""Conservative posting evidence; mentions are not immigration eligibility predictions."""
import html
import re

from app.requirements import screen


def enrich(raw, url):
    parts = [raw.get(k, '') for k in ('content', 'descriptionPlain', 'descriptionBodyPlain',
             'description', 'additionalPlain', 'basic_qualifications', 'preferred_qualifications')]
    parts += [item.get('content', '') for item in raw.get('lists', [])]
    detail = raw.get('_detail') or raw
    sections = (detail.get('jobAd') or {}).get('sections') or {}
    parts += [s.get('text', '') for s in sections.values() if isinstance(s, dict)]
    text = html.unescape(html.unescape(' '.join(p for p in parts if isinstance(p, str))))
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    sentences = re.split(r'(?<=[.!?;])\s+', text)
    training = r'\b(?:OPT|CPT)\b|(?:optional|curricular) practical training'
    evidence = [s[:700] for s in sentences if re.search(r'sponsor|\bH-?1B\b|' + training, s, re.I)]
    denial = (r"\b(no|not|cannot|unable|without|won.t)\b.{0,65}sponsor"
              r"|sponsor.{0,45}\b(not available|not provided)\b")
    offer = (r"\b(offer|provide|available|will|can)\b.{0,35}(visa |immigration )?sponsorship"
             r"|sponsorship.{0,25}\b(available|provided)\b")
    negative = any(re.search(denial, s, re.I) for s in evidence)
    positive = any(re.search(offer, s, re.I) and not re.search(denial, s, re.I) for s in evidence)
    status = ('conflicting' if negative and positive else 'not_offered' if negative
              else 'offered' if positive else 'unknown')
    salaries = []
    comp = raw.get('compensation') or {}
    for item in comp.get('summaryComponents', []):
        if item.get('compensationType') == 'Salary':
            salaries.append({'min': item.get('minValue'), 'max': item.get('maxValue'),
                             'currency': item.get('currencyCode'), 'interval': item.get('interval'),
                             'source': 'structured'})
    salary_evidence = []
    pay_pattern = (r'\$\s*([\d,]+(?:\.\d+)?\s*[kK]?)\s*(?:-|–|—|to)\s*\$?\s*'
                   r'([\d,]+(?:\.\d+)?\s*[kK]?)(?:\s*(?:USD|per|/|a)?\s*'
                   r'(hour|hr|year|annum|annually|annual|month))?')
    range_spans = []
    for match in re.finditer(pay_pattern, text):
        range_spans.append(match.span())
        context = text[max(0, match.start()-100):match.end()+100]
        if not re.search(r'pay|salary|compensation|base|hour|annual|year', context, re.I):
            continue
        def amount(value):
            number = float(value.lower().replace(',', '').replace('k', '').strip())
            return number * (1000 if 'k' in value.lower() else 1)
        lo, hi = amount(match[1]), amount(match[2])
        if lo <= hi and hi > 0:
            currency = 'USD' if 'USD' in match[0] or 'United States' in text else None
            salaries.append({'min': lo, 'max': hi, 'currency': currency,
                             'interval': match[3], 'source': 'posting_text'})
            salary_evidence.append(text[max(0, match.start()-80):match.end()+80])
    fixed_pattern = r'\$\s*([\d,]+(?:\.\d+)?\s*[kK]?)(?![\d,])'
    for match in re.finditer(fixed_pattern, text):
        if any(start <= match.start() < end for start, end in range_spans):
            continue
        context = text[max(0, match.start()-90):match.end()+90]
        prefix = text[max(0, match.start()-65):match.start()]
        suffix = text[match.end():match.end()+60]
        # Require salary context; do not turn signing bonuses or benefits into base pay.
        if not re.search(r'salary|base pay|base compensation|hourly (?:rate|pay)|annual pay', prefix, re.I):
            continue
        if re.search(r'bonus|equity|stipend|allowance|reimbursement', prefix, re.I):
            continue
        value = float(match[1].lower().replace(',', '').replace('k', '').strip())
        value *= 1000 if 'k' in match[1].lower() else 1
        unit = re.search(r'\b(hour|hr|year|annum|annually|annual|month)\b', suffix, re.I)
        salaries.append({'min': value, 'max': value, 'kind': 'fixed',
                         'currency': 'USD' if 'USD' in context else None,
                         'interval': unit[1].lower() if unit else None, 'source': 'posting_text'})
        salary_evidence.append(context)
    return {'requirements': screen(text), 'salary': {'ranges': salaries, 'evidence': salary_evidence[:8]},
            'sponsorship': {'status': status, 'evidence': evidence[:8]},
            'opt': {'mentioned': bool(re.search(training, text, re.I)),
                    'status': 'unknown'}, 'source_url': url,
            'description_available': bool(text)}
