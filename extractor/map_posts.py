"""Geocode extracted posts and generate an interactive map.

Extracts location information from post text and the `location` field,
geocodes via OneMap API (with Nominatim/OpenStreetMap fallback),
and renders an interactive Leaflet map from a custom HTML template.

Usage:
    python extractor/map_posts.py

Requires:
    - OneMap API credentials in secrets/secrets.py
    - Register free at https://www.onemap.gov.sg/apidocs/register

Output:
    docs/index.html               - interactive map (GitHub Pages)
    output/geocode_cache.json     - cached geocoding results (reused across runs)
"""

import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
INPUT_FILE = "output/group_posts.json"
OUTPUT_MAP = "docs/index.html"
GEOCODE_CACHE = "output/geocode_cache.json"
TEMPLATE_FILE = os.path.join(os.path.dirname(__file__), "map_template.html")

GROUP_URL = "https://www.facebook.com/groups/227074250721100/"

# Maximum number of images to include per post in the output (saves bandwidth)
MAX_IMAGES_PER_POST = 3

# Logged-in user name that may have leaked into scraped text.
# The scraper's "comment as <user>" UI element sometimes gets captured.
_SCRAPER_USER = "Jeremy"

ONEMAP_AUTH_URL = "https://www.onemap.gov.sg/api/auth/post/getToken"
ONEMAP_SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"

# Singapore bounding box — reject results outside this
SG_LAT_MIN, SG_LAT_MAX = 1.15, 1.47
SG_LNG_MIN, SG_LNG_MAX = 103.60, 104.05

# Centre of Singapore for default map view
SG_CENTRE = [1.3521, 103.8198]

# Known location aliases — map colloquial/variant names to canonical geocodable names
LOCATION_ALIASES = {
    # Hawker centres / markets — colloquial → canonical
    "tiong bahru food market": "Tiong Bahru Market",
    "old airport market": "Old Airport Road Food Centre",
    "old airport road market": "Old Airport Road Food Centre",
    "berseh hawker centre": "Berseh Food Centre",
    "berseh hawker center": "Berseh Food Centre",
    "smith street market & hawker center": "Chinatown Complex",
    "smith street market and hawker center": "Chinatown Complex",
    "smith street market": "Chinatown Complex",
    "mayflower hawker centre": "Mayflower food Center",
    "mayflower hawker center": "Mayflower food Center",
    "mayflower food center": "Mayflower food Center",
    "mayflower food centre": "Mayflower food Center",
    "mayflower hawker ctr": "Mayflower food Center",
    # Known stall → address mappings (stalls not indexed on geocoders)
    "kim keat hokkien mee": "511 Bishan Street 13",
    "kim keat hokkien mee - official": "511 Bishan Street 13",
    "ahjie hokkien mee": "7 Lorong 8 Toa Payoh",
    "ah ong hokkien mee": "4 Lorong 7 Toa Payoh",
    "chuan fried hokkien prawn mee": "84 Marine Parade Central",
    "shiok hokkien mee": "Beauty World Centre",
    "ho ji fried hokkien prawn noodles": "Mayflower food Center",
    "big fat boy fried hokkien mee": "352 Clementi Avenue 2",
    "bedok 69 hokkien mee": "69 Bedok South Avenue 3",
    "uncle peter hokkien mee": "216 Bedok North Street 1",
    "ah huat hokkien prawn mee": "216 Bedok North Street 1",
    "old airport hawker ctr": "Old Airport Road Food Centre",
    "old airport hawker centre": "Old Airport Road Food Centre",
    "old airport hawker center": "Old Airport Road Food Centre",
    "ah hak fish soup": "69 Bedok South Avenue 3",
    "sheng cheng char kway teow": "665 Buffalo Road",
    "yong heng hokkien mee": "155 Bukit Batok Street 11",
    # Stalls added from backfill geocoding failures
    "tian tian lai fried hokkien mee": "127 Lorong 1 Toa Payoh",
    "hong heng fried sotong prawn mee": "Tiong Bahru Market",
    "tian seng fried hokkien mee": "79A Circuit Road",
    "chuan hokkien mee": "84 Marine Parade Central",
    "hup seng hokkien mee": "505 Jurong West Street 52",
    "com hokkien mee": "44 Owen Road",
    "enjoy eating house and bar": "462 Crawford Lane",
    "enjoy eating house": "462 Crawford Lane",
    # Venue aliases
    "tampines st 82 blk 844 kopitiam": "844 Tampines Street 82",
    "clementi mall food court": "3155 Commonwealth Avenue West",
    "mayflower market and hawker centre": "Mayflower food Center",
    "mayflower market & hawker centre": "Mayflower food Center",
    "mayflower market and food centre": "Mayflower food Center",
    "mayflower market & food centre": "Mayflower food Center",
}

# Common Singapore abbreviations used in posts
SG_ABBREVIATIONS = {
    "amk": "Ang Mo Kio",
    "tpy": "Toa Payoh",
    "cck": "Choa Chu Kang",
    "jw": "Jurong West",
    "je": "Jurong East",
    "bb": "Bukit Batok",
    "bt": "Bukit",
    "bm": "Bukit Merah",
    "bp": "Bukit Panjang",
}


# ---------------------------------------------------------------------------
# OneMap helpers
# ---------------------------------------------------------------------------
def get_onemap_token():
    """Authenticate with OneMap using credentials from secrets/secrets.py."""
    # Import credentials from secrets/secrets.py
    secrets_path = os.path.join(os.path.dirname(__file__), '..', 'secrets', 'secrets.py')
    secrets_path = os.path.abspath(secrets_path)
    if not os.path.exists(secrets_path):
        print(f"Error: {secrets_path} not found.")
        print("Create secrets/secrets.py with:")
        print('  onemap = {')
        print('      "email": "your_email@example.com","')
        print('      "password": "your_password"')
        print('  }')
        print()
        print("Register free at https://www.onemap.gov.sg/apidocs/register")
        sys.exit(1)

    import importlib.util
    spec = importlib.util.spec_from_file_location("secrets", secrets_path)
    secrets_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(secrets_mod)

    creds = getattr(secrets_mod, 'onemap', None)
    if not creds or not creds.get('email') or not creds.get('password'):
        print("Error: secrets/secrets.py must contain an 'onemap' dict with 'email' and 'password'.")
        sys.exit(1)

    resp = requests.post(
        ONEMAP_AUTH_URL,
        json={"email": creds['email'], "password": creds['password']},
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"Error: OneMap auth failed (HTTP {resp.status_code}): {resp.text}")
        sys.exit(1)

    data = resp.json()
    token = data.get("access_token", "")
    if not token:
        print(f"Error: No access_token in response: {data}")
        sys.exit(1)

    return token


def onemap_search(query, token):
    """Search OneMap for a location string. Returns (lat, lng, address) or None."""
    try:
        resp = requests.get(
            ONEMAP_SEARCH_URL,
            params={
                "searchVal": query,
                "returnGeom": "Y",
                "getAddrDetails": "Y",
                "pageNum": 1,
            },
            headers={"Authorization": token},
            timeout=10,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        results = data.get("results", [])
        if not results:
            return None

        top = results[0]
        lat = float(top.get("LATITUDE", 0))
        lng = float(top.get("LONGITUDE") or top.get("LONGTITUDE", 0))
        address = top.get("ADDRESS", "")

        # Reject results outside Singapore
        if not (SG_LAT_MIN <= lat <= SG_LAT_MAX and SG_LNG_MIN <= lng <= SG_LNG_MAX):
            return None

        return (lat, lng, address)

    except Exception as e:
        print(f"    OneMap error for '{query}': {e}")
        return None


def nominatim_search(query):
    """Search Nominatim (OpenStreetMap) for a location. Returns (lat, lng, address) or None.

    Nominatim knows POIs, restaurants, hawker centres etc. that OneMap may not.
    Free with 1 request/second rate limit.
    """
    try:
        resp = requests.get(
            NOMINATIM_SEARCH_URL,
            params={
                "q": query,
                "format": "json",
                "countrycodes": "sg",
                "limit": 1,
                "addressdetails": 1,
            },
            headers={"User-Agent": "hokkien-mee-mapper/1.0"},
            timeout=10,
        )
        if resp.status_code != 200:
            return None

        results = resp.json()
        if not results:
            return None

        top = results[0]
        lat = float(top.get("lat", 0))
        lng = float(top.get("lon", 0))
        address = top.get("display_name", "")

        # Reject results outside Singapore
        if not (SG_LAT_MIN <= lat <= SG_LAT_MAX and SG_LNG_MIN <= lng <= SG_LNG_MAX):
            return None

        # Shorten display_name: take first 2-3 parts before "Singapore"
        parts = [p.strip() for p in address.split(",")]
        short_parts = []
        for p in parts:
            if p.lower().startswith("singapore"):
                break
            short_parts.append(p)
        address = ", ".join(short_parts[:3]) if short_parts else address

        return (lat, lng, address)

    except Exception as e:
        print(f"    Nominatim error for '{query}': {e}")
        return None


# ---------------------------------------------------------------------------
# Query cleaning
# ---------------------------------------------------------------------------
def clean_query(query):
    """Generate cleaned variations of a query for better geocoding."""
    variations = []
    q = query.strip()

    # Check alias first (exact match on raw input)
    alias = LOCATION_ALIASES.get(q.lower())
    if alias:
        variations.append(alias)

    # Also check alias on ASCII-stripped version (for "Chuan Fried Hokkien Prawn Mee 川炒…")
    q_ascii = re.sub(r'[^\x00-\x7F]+', ' ', q).strip()
    q_ascii = re.sub(r'[.\-]+$', '', q_ascii).strip()  # strip trailing dots/dashes
    q_ascii = re.sub(r'\s+', ' ', q_ascii).strip()
    if q_ascii and q_ascii.lower() != q.lower():
        alias_ascii = LOCATION_ALIASES.get(q_ascii.lower())
        if alias_ascii and alias_ascii not in variations:
            variations.append(alias_ascii)

    # Iteratively strip leading junk words (handles chained artifacts like
    # "ny times I reached Old Airport market" → "Old Airport market")
    _JUNK = (
        r'the|a|an|my|this|that|one|of|ny|at|in|I|to|very|towards|from|'
        r'no one|only|just|every|many|some|few|have|had|has|went|'
        r'go|going|was|been|am|is|are|tried|known|times|reached|'
        r'like|love|stall|place|spot'
    )
    prev = None
    while prev != q:
        prev = q
        q = re.sub(rf'^(?:{_JUNK})\s+', '', q, flags=re.I).strip()

    # Filter false positives — generic phrases that aren't locations
    if not q or len(q) < 4:
        return variations
    if re.search(r'\b(?:goal|say in|stay in|known place|have a say|better$|worse$|not very clean$)\b', q, re.I):
        return variations
    # Reject standalone generic terms
    if q.lower() in {
        'coffeeshop', 'coffee shop', 'market', 'food court',
        'food centre', 'food center', 'hawker', 'stall',
    }:
        return variations

    variations.append(q)

    # Check alias after cleaning too
    alias2 = LOCATION_ALIASES.get(q.lower())
    if alias2 and alias2 not in variations:
        variations.append(alias2)

    # Strip Chinese characters
    ascii_only = re.sub(r'[^\x00-\x7F]+', ' ', q).strip()
    ascii_only = re.sub(r'\s+', ' ', ascii_only).strip().rstrip('.')
    if ascii_only and ascii_only != q and len(ascii_only) > 3:
        variations.append(ascii_only)

    # Strip trailing " - Official" or similar
    no_suffix = re.sub(r'\s*[-–]\s*Official\s*$', '', q, flags=re.I).strip()
    if no_suffix != q and no_suffix:
        variations.append(no_suffix)

    # S-11 prefix removal
    s11_match = re.match(r'S-?11\s+(.+)', q, re.I)
    if s11_match:
        variations.append(s11_match.group(1))

    # Split on " at " — try the location part after the preposition
    if ' at ' in q.lower():
        idx = q.lower().index(' at ')
        after = q[idx + 4:].strip()
        if after and len(after) > 5:
            variations.append(after)
            a_alias = LOCATION_ALIASES.get(after.lower())
            if a_alias:
                variations.append(a_alias)
            # Expand abbreviations in the 'after' part too
            after_words = after.split()
            exp_after = []
            changed_a = False
            for w in after_words:
                exp = SG_ABBREVIATIONS.get(w.lower())
                if exp:
                    exp_after.append(exp)
                    changed_a = True
                else:
                    exp_after.append(w)
            if changed_a:
                variations.append(' '.join(exp_after))

    # Strip "Coffee Shop"/"Coffeeshop" suffix (confuses address geocoding)
    no_cs = re.sub(r'\s*(?:coffee\s*shop|coffeeshop)\s*$', '', q, flags=re.I).strip()
    if no_cs != q and no_cs and len(no_cs) > 5:
        variations.append(no_cs)

    # Strip trailing stall numbers ("80 Circuit Road 27" → "80 Circuit Road")
    no_stall = re.sub(r'\s+#?\d{1,2}\s*$', '', q).strip()
    if no_stall != q and no_stall and len(no_stall) > 5:
        variations.append(no_stall)

    # Try without "Blk"/"Block" prefix
    no_blk = re.sub(r'^(?:Blk|Block)\s+', '', q, flags=re.I).strip()
    if no_blk != q and no_blk:
        variations.append(no_blk)

    # Expand common Singapore abbreviations (AMK → Ang Mo Kio, etc.)
    words = q.split()
    expanded_words = []
    changed = False
    for w in words:
        exp = SG_ABBREVIATIONS.get(w.lower())
        if exp:
            expanded_words.append(exp)
            changed = True
        else:
            expanded_words.append(w)
    if changed:
        variations.append(' '.join(expanded_words))

    # Add "Singapore" suffix if not present
    if 'singapore' not in q.lower():
        variations.append(q + ' Singapore')

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for v in variations:
        key = v.lower()
        if key not in seen:
            seen.add(key)
            unique.append(v)

    return unique


# ---------------------------------------------------------------------------
# Location extraction from post text
# ---------------------------------------------------------------------------
def _extract_from_text(text, candidates):
    """Extract location candidates from a block of text (post or comment)."""
    # 1. Singapore postal codes (6 digits, typically starting with 0-8)
    text_no_urls = re.sub(r'https?://\S+', '', text)
    postal_codes = re.findall(
        r'(?:singapore\s*)?(\d{6})\b', text_no_urls, re.I
    )
    for pc in postal_codes:
        if pc[0] in '012345678' and not pc.startswith('000'):
            candidates.append(pc)

    # 2. Block + street address patterns
    _ROAD_SUFFIX = (
        r'(?:street|st|ave|avenue|road|rd|drive|dr|cres|crescent|walk|way|'
        r'lane|lor|lorong|close|terrace|link|central|north|south|east|west)'
    )
    _AREA_NAMES = (
        r'(?:ang mo kio|tampines|bedok|toa payoh|geylang|hougang|jurong|'
        r'bukit|serangoon|yishun|woodlands|clementi|pasir|circuit|owen|'
        r'adam|beach|smith|marine|kelantan|jalan|anchorvale|sengkang|'
        r'punggol|bishan|commonwealth|queenstown|bendemeer|kallang|'
        r'whampoa|balestier|novena|telok|changi|simei|kembangan|'
        r'aljunied|mountbatten|macpherson|paya|upper|lower)'
    )
    block_patterns = [
        # "Blk 308C Punggol Walk" or "Block 304, Woodlands Street 31"
        rf'(?:blk|block)\s*(\d+[A-Za-z]?[\s,]+[A-Za-z\s]+{_ROAD_SUFFIX}(?:\s+\d+)?)',
        # "828 Tampines Ave 3" — number-first with known area name
        rf'(\d+[A-Za-z]?\s+{_AREA_NAMES}\s*{_ROAD_SUFFIX}?(?:\s+\d+)?)',
        # Standalone street address: "31 Kelantan Lane", "68 Geylang Bahru"
        rf'(\d+[A-Za-z]?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s+{_ROAD_SUFFIX})',
    ]
    for pat in block_patterns:
        for m in re.findall(pat, text, re.I):
            addr = re.sub(r'\s+', ' ', m).strip()
            addr = re.split(r'[.!?\n]', addr)[0].strip().rstrip(',')
            if len(addr) > 5:
                candidates.append(addr)

    # 3. Named hawker centres / food courts / markets / coffeeshops
    hawker_patterns = [
        r'([A-Z][\w\s\'\-]{2,30}(?:hawker\s*cent(?:re|er)|food\s*cent(?:re|er)|food\s*court|food\s*house|eating\s*house|market(?:\s*(?:&|and)\s*(?:food\s*cent(?:re|er)|hawker(?:\s*cent(?:re|er))?))?|coffee\s*shop|coffeeshop|kopitiam))',
        r'((?:hawker\s*cent(?:re|er)|food\s*cent(?:re|er)|food\s*court)\s+[A-Z][\w\s\'\-]+)',
        # "hawker Ctr" abbreviation
        r'([A-Z][\w\s\'\-]{2,30}(?:hawker\s*ctr))',
    ]
    for pat in hawker_patterns:
        matches = re.findall(pat, text, re.I)
        for m in matches:
            name = re.sub(r'\s+', ' ', m).strip()
            name = re.sub(r'^(?:at|in|the|a|an|of|or|my|this|from)\s+', '', name, flags=re.I).strip()
            if len(name) > 5 and len(name) < 80:
                candidates.append(name)

    # 4. Known area / neighbourhood names — "Beauty World", "Bukit Batok", etc.
    area_pattern = re.findall(
        r'\b(Beauty\s+World|Holland\s+Village|Tiong\s+Bahru|'
        r'Golden\s+Mile|Tanjong\s+Pagar|Telok\s+Ayer|'
        r'Chinatown|Geylang\s+Serai|Little\s+India|'
        r'Bugis|Lavender|Bencoolen|Novena|Newton)\b',
        text, re.I
    )
    for area in area_pattern:
        candidates.append(area.strip())

    # 5. Named stalls — proper-noun-like names before "Hokkien Mee" etc.
    stall_patterns = re.findall(
        r'((?:[A-Z][\w\'-]*\s+){1,4}(?:Fried\s+)?(?:Hokkien|Prawn)[\w\s\']*(?:Mee|Noodle|Mie)s?)',
        text,
    )
    for m in stall_patterns:
        name = re.sub(r'\s+', ' ', m).strip()
        generic = {
            'hokkien mee', 'fried hokkien mee', 'hkm', 'hokkien mie',
            'the hokkien mee', 'a hokkien mee', 'my hokkien mee',
            'this hokkien mee', 'good hokkien mee', 'nice hokkien mee',
            'best hokkien mee', 'great hokkien mee', 'their hokkien mee',
            'your hokkien mee', 'our hokkien mee', 'any hokkien mee',
            'some hokkien mee', 'one hokkien mee', 'every hokkien mee',
        }
        if name.lower() in generic:
            continue
        if len(name) > 5 and len(name) < 60:
            candidates.append(name)

    # 6. "Address:" prefix — explicit address mention
    addr_match = re.search(
        r'[Aa]ddress\s*:?\s*(.+?)(?:\n|$)', text
    )
    if addr_match:
        addr_text = addr_match.group(1).strip().rstrip('.')
        if len(addr_text) > 5 and len(addr_text) < 100:
            candidates.append(addr_text)


def extract_location_candidates(post):
    """Extract potential location search strings from a post.

    Returns a list of candidates ordered from most to least specific:
      1. Singapore 6-digit postal code
      2. Block/Blk + street address
      3. Hawker centre / food court name
      4. Named area / neighbourhood
      5. Facebook check-in location field
      6. Stall name from text
      7. Location clues from comments (lower priority)
    """
    text = post.get("text", "")
    location = post.get("location", "")
    candidates = []

    # Extract from post text (highest priority)
    _extract_from_text(text, candidates)

    # Facebook check-in location field
    if location:
        candidates.append(location)

    # Extract from comments (lower priority — appended after post candidates)
    comments = post.get("comments", [])
    comment_candidates = []
    for comment in comments:
        comment_text = comment.get("text", "")
        if comment_text:
            _extract_from_text(comment_text, comment_candidates)
    candidates.extend(comment_candidates)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for c in candidates:
        key = c.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique


# ---------------------------------------------------------------------------
# Geocoding with cache
# ---------------------------------------------------------------------------
def load_cache():
    """Load geocode cache from disk."""
    if os.path.exists(GEOCODE_CACHE):
        try:
            with open(GEOCODE_CACHE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_cache(cache):
    """Save geocode cache to disk."""
    with open(GEOCODE_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def geocode_post(post, token, cache):
    """Try to geocode a post. Returns (lat, lng, matched_query, address) or None.

    Strategy:
      1. For each candidate, generate cleaned variations
      2. Try OneMap first (best for addresses, postal codes, building names)
      3. Fall back to Nominatim (best for POIs, stall names, businesses)
    """
    candidates = extract_location_candidates(post)
    if not candidates:
        return None

    # Collect all query variations across candidates
    all_queries = []  # (original_candidate, query_variation)
    for candidate in candidates:
        for variation in clean_query(candidate):
            all_queries.append((candidate, variation))

    # Phase 1: Try OneMap with all variations
    for original, query in all_queries:
        cache_key = f"onemap:{query.strip().lower()}"

        if cache_key in cache:
            cached = cache[cache_key]
            if cached is None:
                continue
            return (cached["lat"], cached["lng"], original, cached["address"])

        result = onemap_search(query, token)
        time.sleep(0.3)

        if result:
            lat, lng, address = result
            cache[cache_key] = {"lat": lat, "lng": lng, "address": address}
            return (lat, lng, original, address)
        else:
            cache[cache_key] = None

    # Phase 2: Try Nominatim with all variations
    for original, query in all_queries:
        cache_key = f"nominatim:{query.strip().lower()}"

        if cache_key in cache:
            cached = cache[cache_key]
            if cached is None:
                continue
            return (cached["lat"], cached["lng"], original, cached["address"])

        result = nominatim_search(query)
        time.sleep(1.1)  # Nominatim requires 1 req/sec

        if result:
            lat, lng, address = result
            cache[cache_key] = {"lat": lat, "lng": lng, "address": address}
            return (lat, lng, original, address)
        else:
            cache[cache_key] = None

    return None


# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

def _clean_post_text(text):
    """Remove artifacts left by the scraper.

    The logged-in user's name (e.g. "Jeremy") sometimes appears as a
    standalone line sandwiched between the collapsed and expanded versions
    of the post text.  This strips it, as well as trailing numeric
    reaction counts that leaked in.
    """
    if not text:
        return text
    name = _SCRAPER_USER
    # Remove standalone line matching the user's name (case-insensitive)
    # Pattern: "\nJeremy\n" or trailing "\nJeremy"
    text = re.sub(
        rf'\n{re.escape(name)}\s*$', '', text, flags=re.I
    )
    text = re.sub(
        rf'\n{re.escape(name)}\n', '\n', text, flags=re.I
    )
    # Remove trailing bare numbers (leaked reaction counts like "\n32")
    text = re.sub(r'\n\d{1,4}\s*$', '', text)
    # Remove trailing "View more answers" UI leak
    text = re.sub(r'\nView more answers\s*$', '', text, flags=re.I)
    return text.strip()


# ---------------------------------------------------------------------------
# Sentiment analysis
# ---------------------------------------------------------------------------

# Positive keywords / phrases — food-context and Singlish aware
_POSITIVE = [
    # Strong positive
    r'\bbest\b', r'\bamazing\b', r'\bexcellent\b', r'\bfantastic\b',
    r'\boutstanding\b', r'\bperfect\b', r'\bincredible\b', r'\blegit\b',
    r'\bmust.?try\b', r'\bworth\b', r'\btop.?notch\b', r'\b10/10\b',
    # Moderate positive
    r'\bgood\b', r'\bgreat\b', r'\bnice\b', r'\bdelicious\b', r'\btasty\b',
    r'\byummy\b', r'\brecommend\b', r'\bfavou?rite\b', r'\bawesome\b',
    r'\blove(?:d|s)?\b', r'\bwonderful\b', r'\bsuperb\b',
    # Singlish / local positive
    r'\bshiok\b', r'\bsedap\b', r'\bpower\b', r'\bnot bad\b',
    r'\bquite good\b', r'\bdamn good\b', r'\bsolid\b',
    # Hokkien mee specific positive signals
    r'\bwok.?hei\b', r'\bfragran[ct]\b', r'\blard\b', r'\bcharcoal\b',
    r'\bqueue\b', r'\blong queue\b', r'\bsell.?out\b', r'\bsold.?out\b',
    r'\bbig.?prawn\b', r'\bfresh prawn\b', r'\bgood stuff\b',
    # Reaction signals
    r'\b(?:5|4\.5|4)\s*/\s*5\b',
    '\U0001F44D', '\u2764', '\U0001F60B', '\U0001F929',
]

# Negative keywords / phrases
_NEGATIVE = [
    # Strong negative
    r'\bterrible\b', r'\bhorrible\b', r'\bworst\b', r'\bawful\b',
    r'\bnever going back\b', r"\bdon'?t bother\b", r'\bavoid\b',
    r'\bdisgusting\b', r'\binedible\b',
    # Moderate negative
    r'\bbad\b', r'\bdisappoint\w*\b', r'\boverrated\b', r'\bmeh\b',
    r'\bmediocre\b', r'\bskip\b', r'\bnot.{0,5}good\b', r'\bnot.{0,5}nice\b',
    r'\bnot.{0,5}worth\b', r'\btoo wet\b', r'\btoo dry\b', r'\btoo salty\b',
    r'\bno taste\b', r'\btasteless\b', r'\bbland\b',
    # Singlish / local negative
    r'\bcmi\b', r'\bcannot make it\b', r'\bsoso\b', r'\bso.?so\b',
    r'\blor(?:\b|$)', r'\bok(?:ay)? only\b', r'\bnothing special\b',
    # Hokkien mee specific negative
    r'\bno pork\b', r'\bno lard\b', r'\bdecline\b', r'\bwen?t down\w*\b',
    r'\bnot.{0,10}same\b', r'\bused to be\b',
    # Reaction signals
    '\U0001F44E', '\U0001F922',
    r'\b[01]\s*/\s*5\b',
]

_POS_PATTERNS = [re.compile(p, re.I) for p in _POSITIVE]
_NEG_PATTERNS = [re.compile(p, re.I) for p in _NEGATIVE]


def _score_text(text):
    """Score a single text. Returns (positive_hits, negative_hits)."""
    if not text:
        return (0, 0)
    pos = sum(1 for p in _POS_PATTERNS if p.search(text))
    neg = sum(1 for p in _NEG_PATTERNS if p.search(text))
    return (pos, neg)


def compute_location_sentiment(posts_at_location):
    """Compute a sentiment score for a location from all its posts and comments.

    Returns a dict with:
      - score: float 0.0-5.0 (star rating), or None if insufficient data
      - positive: int total positive signals
      - negative: int total negative signals
      - total_signals: int total signals found
      - rated_comments: int number of comments that had sentiment signals
    """
    total_pos = 0
    total_neg = 0
    rated_comments = 0

    for post in posts_at_location:
        # Score the post text itself (often neutral/descriptive, lower weight)
        post_pos, post_neg = _score_text(post.get("text", ""))
        total_pos += post_pos
        total_neg += post_neg
        if post_pos or post_neg:
            rated_comments += 1

        # Score each comment (these are the real opinions)
        for comment in post.get("comments", []):
            c_pos, c_neg = _score_text(comment.get("text", ""))
            total_pos += c_pos
            total_neg += c_neg
            if c_pos or c_neg:
                rated_comments += 1

    total_signals = total_pos + total_neg

    # Need at least 2 signal-bearing texts to produce a rating
    if rated_comments < 2 or total_signals < 2:
        return {
            "score": None,
            "positive": total_pos,
            "negative": total_neg,
            "total_signals": total_signals,
            "rated_comments": rated_comments,
        }

    # Positive ratio → map to 1.0–5.0 star scale
    # 100% positive = 5.0, 50/50 = 3.0, 100% negative = 1.0
    ratio = total_pos / total_signals
    score = 1.0 + ratio * 4.0
    # Round to nearest 0.5
    score = round(score * 2) / 2

    return {
        "score": score,
        "positive": total_pos,
        "negative": total_neg,
        "total_signals": total_signals,
        "rated_comments": rated_comments,
    }


# ---------------------------------------------------------------------------
# Map generation
# ---------------------------------------------------------------------------
def build_site(geocoded_posts, total_posts):
    """Generate an interactive HTML map from the template and geocoded data."""
    # Group posts by location
    location_groups = {}
    for item in geocoded_posts:
        key = f"{item['lat']:.6f},{item['lng']:.6f}"
        if key not in location_groups:
            location_groups[key] = {
                "lat": item["lat"],
                "lng": item["lng"],
                "address": item["address"],
                "posts": [],
                "_raw_posts": [],  # keep originals for sentiment analysis
            }
        post = item["post"]
        location_groups[key]["_raw_posts"].append(post)

        # Extract a clean reaction count
        reactions_raw = post.get("reactions", "")
        reactions = ""
        if reactions_raw:
            m = re.match(r'(\d+)', reactions_raw)
            if m:
                reactions = m.group(1)

        post_id = post.get("post_id", "unknown")
        images = []
        for j, url in enumerate(post.get("images", [])[:MAX_IMAGES_PER_POST]):
            if not url:
                continue
            images.append({
                "url": url,
                "local": f"images/{post_id}_{j}.jpg",
            })

        location_groups[key]["posts"].append({
            "author": post.get("author", "Unknown"),
            "text": _clean_post_text(post.get("text", "")),
            "images": images,
            "post_link": post.get("post_link", ""),
            "timestamp": post.get("timestamp", ""),
            "comment_count": len(post.get("comments", [])),
            "reactions": reactions,
        })

    # Compute sentiment for each location
    for loc in location_groups.values():
        sentiment = compute_location_sentiment(loc["_raw_posts"])
        loc["sentiment"] = {
            "score": sentiment["score"],
            "positive": sentiment["positive"],
            "negative": sentiment["negative"],
            "rated_comments": sentiment["rated_comments"],
        }
        del loc["_raw_posts"]  # don't include raw posts in output

    # Assign a stable ID to each location (short hash of address)
    for loc in location_groups.values():
        loc["id"] = hashlib.sha256(
            loc["address"].lower().encode("utf-8")
        ).hexdigest()[:8]

    # Sort locations: most posts first, then alphabetically
    locations = sorted(
        location_groups.values(),
        key=lambda loc: (-len(loc["posts"]), loc["address"].lower()),
    )

    # Log sentiment stats
    rated = [l for l in locations if l["sentiment"]["score"] is not None]
    print(f"  Sentiment: {len(rated)}/{len(locations)} locations have ratings")
    if rated:
        avg = sum(l["sentiment"]["score"] for l in rated) / len(rated)
        print(f"  Average rating: {avg:.1f}/5.0")

    # Build the data payload for the template
    map_data = {
        "meta": {
            "total_posts": total_posts,
            "geocoded_count": len(geocoded_posts),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "locations": locations,
    }

    # Read template
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    # Inject data
    html = html.replace("__MAP_DATA__", json.dumps(map_data, ensure_ascii=False))
    html = html.replace("__GROUP_URL__", GROUP_URL)

    return html


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    # Load posts
    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found. Run extract_group.py first.")
        sys.exit(1)

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    posts = data.get("posts", data) if isinstance(data, dict) else data
    print(f"Loaded {len(posts)} posts from {INPUT_FILE}")

    # Authenticate with OneMap
    print("Authenticating with OneMap...")
    token = get_onemap_token()
    print("  ✓ Token obtained\n")

    # Load geocode cache
    cache = load_cache()
    print(f"Geocode cache: {len(cache)} entries\n")

    # Geocode each post
    geocoded = []
    skipped = 0
    for i, post in enumerate(posts):
        post_id = post.get("post_id", "?")
        candidates = extract_location_candidates(post)

        if not candidates:
            skipped += 1
            continue

        result = geocode_post(post, token, cache)
        if result:
            lat, lng, query, address = result
            geocoded.append({
                "post": post,
                "lat": lat,
                "lng": lng,
                "query": query,
                "address": address,
            })
            print(f"  ✓ [{i+1}/{len(posts)}] {post_id}: {query} → {address}")
        else:
            print(f"  ✗ [{i+1}/{len(posts)}] {post_id}: no match for {candidates[:2]}")

    # Save cache
    save_cache(cache)

    print(f"\nGeocoded: {len(geocoded)}/{len(posts)} posts ({skipped} had no location info)")

    if not geocoded:
        print("No posts could be geocoded. Nothing to map.")
        sys.exit(0)

    # Build and save site
    print("\nBuilding map...")
    html = build_site(geocoded, len(posts))

    os.makedirs(os.path.dirname(OUTPUT_MAP), exist_ok=True)
    with open(OUTPUT_MAP, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Map saved to {OUTPUT_MAP}")
    print(f"Open in browser: file://{os.path.abspath(OUTPUT_MAP)}")


if __name__ == "__main__":
    main()
