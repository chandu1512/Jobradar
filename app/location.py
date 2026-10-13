"""Normalize free text ATS locations into (is_us, states, remote).

is_us is True for a US location, False for a clearly foreign one, None when unknown
(e.g. "Hybrid", "Remote" with no country). states holds two letter USPS codes.
"""
import re

STATES = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas", "CA": "california",
    "CO": "colorado", "CT": "connecticut", "DE": "delaware", "FL": "florida", "GA": "georgia",
    "HI": "hawaii", "ID": "idaho", "IL": "illinois", "IN": "indiana", "IA": "iowa", "KS": "kansas",
    "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland", "MA": "massachusetts",
    "MI": "michigan", "MN": "minnesota", "MS": "mississippi", "MO": "missouri", "MT": "montana",
    "NE": "nebraska", "NV": "nevada", "NH": "new hampshire", "NJ": "new jersey", "NM": "new mexico",
    "NY": "new york", "NC": "north carolina", "ND": "north dakota", "OH": "ohio", "OK": "oklahoma",
    "OR": "oregon", "PA": "pennsylvania", "RI": "rhode island", "SC": "south carolina",
    "SD": "south dakota", "TN": "tennessee", "TX": "texas", "UT": "utah", "VT": "vermont",
    "VA": "virginia", "WA": "washington", "WV": "west virginia", "WI": "wisconsin", "WY": "wyoming",
    "DC": "district of columbia", "PR": "puerto rico",
}
NAME_TO_CODE = {v: k for k, v in STATES.items()}

# Bare city names that ATSes commonly emit without a state.
CITIES = {
    "san francisco": "CA", "sf": "CA", "bay area": "CA", "san jose": "CA", "palo alto": "CA",
    "mountain view": "CA", "menlo park": "CA", "sunnyvale": "CA", "santa clara": "CA",
    "redwood city": "CA", "san mateo": "CA", "oakland": "CA", "berkeley": "CA", "los angeles": "CA",
    "san diego": "CA", "irvine": "CA", "santa monica": "CA", "el segundo": "CA", "torrance": "CA",
    "cupertino": "CA", "south san francisco": "CA", "pasadena": "CA", "new york city": "NY",
    "nyc": "NY", "manhattan": "NY", "brooklyn": "NY", "seattle": "WA", "bellevue": "WA",
    "redmond": "WA", "kirkland": "WA", "austin": "TX", "dallas": "TX", "houston": "TX",
    "san antonio": "TX", "chicago": "IL", "boston": "MA", "cambridge, ma": "MA", "somerville": "MA",
    "denver": "CO", "boulder": "CO", "atlanta": "GA", "miami": "FL", "tampa": "FL", "orlando": "FL",
    "phoenix": "AZ", "scottsdale": "AZ", "tempe": "AZ", "salt lake city": "UT", "lehi": "UT",
    "portland, or": "OR", "philadelphia": "PA", "pittsburgh": "PA", "detroit": "MI",
    "ann arbor": "MI", "minneapolis": "MN", "nashville": "TN", "raleigh": "NC", "durham": "NC",
    "charlotte": "NC", "cary": "NC", "arlington, va": "VA", "reston": "VA", "mclean": "VA",
    "chantilly": "VA", "herndon": "VA", "baltimore": "MD", "columbus": "OH", "cleveland": "OH",
    "st. louis": "MO", "kansas city": "MO", "las vegas": "NV", "honolulu": "HI", "madison": "WI",
    "new orleans": "LA", "indianapolis": "IN", "jersey city": "NJ", "hoboken": "NJ",
    "princeton": "NJ", "stamford": "CT", "new haven": "CT", "providence": "RI",
    "washington, dc": "DC", "washington dc": "DC", "washington d.c.": "DC", "beverly hills": "CA",
}
US_TOKENS = re.compile(r"(?<![a-z])(united states|usa|u\.s\.(?:a\.)?|us)(?![a-z])", re.I)
FOREIGN = re.compile(r"\b(" + "|".join([
    "canada", "toronto", "vancouver", "montreal", "ottawa", "calgary", "mexico", "brazil", "são paulo",
    "sao paulo", "rio de janeiro", "argentina", "buenos aires", "chile", "colombia", "bogota", "peru",
    "united kingdom", "uk", "england", "scotland", "london", "manchester", "edinburgh", "ireland",
    "dublin", "france", "paris", "germany", "berlin", "munich", "hamburg", "frankfurt", "netherlands",
    "amsterdam", "belgium", "brussels", "spain", "madrid", "barcelona", "portugal", "lisbon", "italy",
    "milan", "rome", "switzerland", "zurich", "geneva", "austria", "vienna", "poland", "warsaw",
    "krakow", "czech", "prague", "romania", "bucharest", "sweden", "stockholm", "denmark",
    "copenhagen", "norway", "oslo", "finland", "helsinki", "estonia", "tallinn", "israel", "tel aviv",
    "uae", "dubai", "abu dhabi", "saudi", "riyadh", "turkey", "istanbul", "egypt", "cairo", "nigeria",
    "lagos", "kenya", "nairobi", "south africa", "cape town", "johannesburg", "india", "bengaluru",
    "bangalore", "hyderabad", "mumbai", "pune", "chennai", "delhi", "gurgaon", "gurugram", "noida",
    "pakistan", "singapore", "malaysia", "kuala lumpur", "indonesia", "jakarta", "philippines",
    "manila", "vietnam", "thailand", "bangkok", "china", "beijing", "shanghai", "shenzhen",
    "hong kong", "taiwan", "taipei", "japan", "tokyo", "osaka", "korea", "seoul", "australia",
    "sydney", "melbourne", "brisbane", "new zealand", "auckland", "emea", "apac", "latam", "europe",
    "hungary", "budapest", "bulgaria", "sofia", "serbia", "belgrade", "slovakia", "bratislava",
    "czechia", "latvia", "riga", "lithuania", "vilnius", "ukraine", "kyiv", "kiev", "greece", "athens",
    "croatia", "zagreb", "slovenia", "luxembourg", "iceland", "herzliya", "haifa", "jerusalem",
    "rwanda", "ghana", "morocco", "lyon", "nantes", "bogotá", "lima", "costa rica", "uruguay",
    "montevideo", "guadalajara", "monterrey", "cyprus", "malta", "qatar", "doha", "sri lanka",
    "worldwide", "global",
]) + r")\b", re.I)
REMOTE = re.compile(r"\b(remote|anywhere|distributed|home based|work from home|wfh)\b", re.I)
SPLIT = re.compile(r"\s*(?:\||•|;|/| or | and |\n)\s*")
CODE_RE = re.compile(r"(?:^|[,\s(-])([A-Z]{2})(?=$|[\s,)])")


def _states(part):
    p = part.lower()
    found = {code for name, code in NAME_TO_CODE.items() if re.search(rf"\b{name}\b", p)}
    # "Washington" alone is usually the state, but "Washington, DC" is not.
    if "DC" in found or re.search(r"washington,?\s*d\.?c", p):
        found.discard("WA")
        found.add("DC")
    for city, code in CITIES.items():
        if not found and re.search(rf"\b{re.escape(city)}\b", p):
            found.add(code)
    # Bare codes ("Toronto, ON, CA") are weak evidence; a foreign word in the same part wins.
    codes = {c for c in CODE_RE.findall(part) if c in STATES}
    if codes and not found and FOREIGN.search(part):
        return set()
    return found | codes


def parse(location, country=None):
    """country is a structured hint from the ATS payload (ISO code or name), if any."""
    text = location or ""
    remote = bool(REMOTE.search(text))
    states, us_hit, foreign_hit = set(), False, False
    for part in filter(None, SPLIT.split(text)):
        s = _states(part)
        if s:
            states |= s
            us_hit = True
        elif US_TOKENS.search(part):
            us_hit = True
        elif FOREIGN.search(part):
            foreign_hit = True
    if country:
        c = country.strip().lower()
        if c in ("us", "usa", "united states", "united states of america"):
            us_hit = True
        elif not us_hit:
            foreign_hit = True
    if us_hit:
        is_us = True
    elif foreign_hit:
        is_us = False
    else:
        is_us = None
    return {"is_us": is_us, "states": sorted(states), "remote": remote}


def from_raw(ats, location, raw):
    """Pull a country hint out of the ATS payload, then parse."""
    raw = raw or {}
    country = None
    if ats == "lever":
        country = raw.get("country")
        if (raw.get("workplaceType") or "") == "remote" and location and "remote" not in location.lower():
            location = f"{location} (Remote)"
    elif ats == "ashby":
        addr = (raw.get("address") or {}).get("postalAddress") or {}
        country = addr.get("addressCountry")
        region = addr.get("addressRegion")
        if region and location:
            location = f"{location}, {region}"
        if raw.get("isRemote") and location and "remote" not in location.lower():
            location = f"{location} (Remote)"
    return parse(location, country)
