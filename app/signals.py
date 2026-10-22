"""Conservative posting evidence; mentions are not immigration eligibility predictions."""
import html
import re


def enrich(raw, url):
    parts = [raw.get(k, '') for k in ('content', 'descriptionPlain', 'descriptionBodyPlain',
             'description', 'additionalPlain', 'basic_qualifications', 'preferred_qualifications')]
    parts += [item.get('content', '') for item in raw.get('lists', [])]
    text = html.unescape(html.unescape(' '.join(p for p in parts if isinstance(p, str))))
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    sentences = re.split(r'(?<=[.!?;])\s+', text)
    evidence = [s[:700] for s in sentences if re.search(r'sponsor|\bH-?1B\b|\bOPT\b|\bCPT\b', s, re.I)]
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
    for match in re.finditer(pay_pattern, text):
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
    return {'salary': {'ranges': salaries, 'evidence': salary_evidence[:8]},
            'sponsorship': {'status': status, 'evidence': evidence[:8]},
            'opt': {'mentioned': bool(re.search(r'\b(?:OPT|CPT)\b', text)),
                    'status': 'unknown'}, 'source_url': url,
            'description_available': bool(text)}
