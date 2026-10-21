"""Explainable title rules for role families, shared by SQL filtering and API labels.

Roles can belong to multiple families. These describe work, not the employer's industry.
Keep expressions compatible with both Python and PostgreSQL regular expressions.
"""
import re

CATEGORIES = {
    'ai_ml': ('AI / Machine Learning', r'ai|ml|machine learning|artificial intelligence|deep learning|'
              r'nlp|natural language|computer vision|llm|generative ai|applied scientist|research scientist'),
    'software': ('Software Engineering', r'software|swe|developer|programmer|full[ -]?stack|front[ -]?end|'
                 r'back[ -]?end|mobile engineer|ios engineer|android engineer|web engineer'),
    'data_analysis': ('Data Analysis / BI', r'data analyst|analytics|business intelligence|bi analyst|'
                      r'bi engineer|reporting analyst|business analyst'),
    'data_science': ('Data Science', r'data scien(tist|ce)'),
    'data_engineering': ('Data Engineering', r'data engineer|data platform|database|etl|data architect'),
    'devops_cloud': ('DevOps / Cloud / Infrastructure', r'devops|sre|site reliability|cloud|infrastructure|'
                     r'platform engineer|systems engineer|system engineer|network engineer'),
    'security': ('Cybersecurity', r'security|cyber|soc analyst|penetration test'),
    'qa': ('QA / Testing', r'qa|quality assurance|test engineer|sdet|software test'),
    'product': ('Product / Project Management', r'product manager|product owner|program manager|'
                r'project manager|scrum master'),
    'design': ('Design / UX', r'designer|ux|ui|user experience|user research'),
    'hardware': ('Hardware / Electrical / Mechanical', r'hardware|electrical|electronics|mechanical|'
                 r'firmware|embedded|robotics|semiconductor'),
    'sales': ('Sales / Business Development', r'sales|account executive|business development|'
              r'account manager|solutions engineer|solution engineer'),
    'marketing': ('Marketing / Communications', r'marketing|communications|public relations|'
                  r'copywriter|content strategist|seo'),
    'finance': ('Finance / Accounting', r'finance|financial|accountant|accounting|audit|tax|bookkeep|controller'),
    'hr': ('HR / Recruiting', r'recruiter|recruiting|recruitment|human resources|people operations|hr|talent'),
    'operations': ('Operations / Supply Chain', r'operations|supply chain|logistics|warehouse|procurement|'
                   r'manufacturing|production operator'),
    'healthcare': ('Healthcare', r'nurse|nursing|rn|lpn|physician|clinical|therapist|pharmacist|'
                   r'medical|health aide|caregiver|social worker|case manager'),
    'support': ('Customer Support / Success', r'customer support|customer success|customer service|'
                r'technical support|help desk|service desk'),
    'education': ('Education', r'teacher|teaching|instructor|professor|educator|tutor'),
    'legal': ('Legal', r'attorney|lawyer|paralegal|legal|counsel'),
    'trades': ('Trades / Field Services', r'technician|electrician|plumber|mechanic|hvac|carpenter|'
               r'construction|field service|driver'),
}
PATTERNS = {key: rf'(^|[^a-z])({pattern})([^a-z]|$)' for key, (_, pattern) in CATEGORIES.items()}
COMPILED = {key: re.compile(pattern, re.I) for key, pattern in PATTERNS.items()}


def classify(title):
    return [key for key, pattern in COMPILED.items() if pattern.search(title or '')]


def annotate(rows):
    return [{**row, 'categories': classify(row['title'])} for row in rows]
