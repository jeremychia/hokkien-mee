"""
Geocode extracted posts and plot them on an interactive map.

Extracts location information from post text and the `location` field,
geocodes via OneMap API (with Nominatim/OpenStreetMap fallback),
and renders an HTML map with Folium (Leaflet).

Usage:
    python extractor/map_posts.py

Requires:
    - OneMap API credentials in secrets/secrets.py
    - Register free at https://www.onemap.gov.sg/apidocs/register

Output:
    output/hokkien_mee_map.html   — interactive map
    output/geocode_cache.json     — cached geocoding results (reused across runs)
"""

import json
import os
import re
import sys
import time

import folium
import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
INPUT_FILE = "output/group_posts.json"
OUTPUT_MAP = "output/hokkien_mee_map.html"
GEOCODE_CACHE = "output/geocode_cache.json"

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
    "tiong bahru food market": "Tiong Bahru Market",
    "old airport market": "Old Airport Road Food Centre",
    "old airport road market": "Old Airport Road Food Centre",
    "berseh hawker centre": "Berseh Food Centre",
    "berseh hawker center": "Berseh Food Centre",
    "smith street market & hawker center": "Chinatown Complex",
    "smith street market and hawker center": "Chinatown Complex",
    "smith street market": "Chinatown Complex",
}

# Common Singapore abbreviations used in posts
SG_ABBREVIATIONS = {
    "amk": "Ang Mo Kio",
    "tpy": "Toa Payoh",
    "cck": "Choa Chu Kang",
    "jw": "Jurong West",
    "je": "Jurong East",
    "bb": "Bukit Batok",
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

    # Iteratively strip leading junk words (handles chained artifacts like
    # "ny times I reached Old Airport market" → "Old Airport market")
    _JUNK = (
        r'the|a|an|my|this|that|one|of|ny|at|in|I|to|very|towards|'
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
    if re.search(r'\b(?:goal|say in|stay in|known place|have a say)\b', q, re.I):
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
def extract_location_candidates(post):
    """Extract potential location search strings from a post.

    Returns a list of candidates ordered from most to least specific:
      1. Singapore 6-digit postal code
      2. Block/Blk + street address
      3. Hawker centre / food court name
      4. Facebook check-in location field
      5. Stall name from text
    """
    text = post.get("text", "")
    location = post.get("location", "")
    candidates = []

    # 1. Singapore postal codes (6 digits, typically starting with 0-8)
    #    Match "Singapore 540338" or standalone 6-digit codes, but not inside URLs
    # Remove URLs first to avoid false matches
    text_no_urls = re.sub(r'https?://\S+', '', text)
    postal_codes = re.findall(
        r'(?:singapore\s*)?(\d{6})\b', text_no_urls, re.I
    )
    for pc in postal_codes:
        # Basic validation: Singapore postal codes are 01xxxx to 83xxxx
        if pc[0] in '012345678' and not pc.startswith('000'):
            candidates.append(pc)

    # 2. Block + street address
    #    "Blk 308C Punggol Walk" or "Block 304, Woodlands Street 31"
    #    Also "828 Tampines Ave 3" (number-first without Blk prefix)
    block_patterns = [
        r'(?:blk|block)\s*(\d+[A-Za-z]?[\s,]+[A-Za-z\s]+(?:street|st|ave|avenue|road|rd|drive|dr|cres|crescent|walk|way|lane|lor|lorong|close|terrace|link|central|north|south|east|west)(?:\s+\d+)?)',
        r'(\d+[A-Za-z]?\s+(?:ang mo kio|tampines|bedok|toa payoh|geylang|hougang|jurong|bukit|serangoon|yishun|woodlands|clementi|pasir|circuit|owen|adam|beach|smith)\s*(?:street|st|ave|avenue|road|rd|drive|dr|cres|crescent|walk|way|lane|lor|lorong|close|terrace|link|central|north|south|east|west)?(?:\s+\d+)?)',
    ]
    for pat in block_patterns:
        for m in re.findall(pat, text, re.I):
            addr = re.sub(r'\s+', ' ', m).strip()
            addr = re.split(r'[.!?\n]', addr)[0].strip().rstrip(',')
            if len(addr) > 5:
                candidates.append(addr)

    # 3. Named hawker centres / food courts / markets
    hawker_patterns = [
        r'([A-Z][\w\s\'\-]{2,30}(?:hawker\s*cent(?:re|er)|food\s*cent(?:re|er)|food\s*court|food\s*house|market(?:\s*(?:&|and)\s*(?:food\s*cent(?:re|er)|hawker))?|coffee\s*shop|coffeeshop))',
        r'((?:hawker\s*cent(?:re|er)|food\s*cent(?:re|er)|food\s*court)\s+[A-Z][\w\s\'\-]+)',
    ]
    for pat in hawker_patterns:
        matches = re.findall(pat, text, re.I)
        for m in matches:
            name = re.sub(r'\s+', ' ', m).strip()
            # Strip leading junk words that slipped into the regex
            name = re.sub(r'^(?:at|in|the|a|an|of|or|my|this|from)\s+', '', name, flags=re.I).strip()
            if len(name) > 5 and len(name) < 80:
                candidates.append(name)

    # 4. Facebook check-in location field
    if location:
        candidates.append(location)

    # 5. Named stalls — look for proper-noun-like names before "Hokkien Mee" etc.
    #    e.g. "Ah Ong Hokkien Mee", "618 Hokkien Mee", "Nam Sing hokkien fried mee"
    stall_patterns = re.findall(
        r'((?:[A-Z][\w\'-]*\s+){1,4}(?:Fried\s+)?(?:Hokkien|Prawn)[\w\s\']*(?:Mee|Noodle|Mie)s?)',
        text,
    )
    for m in stall_patterns:
        name = re.sub(r'\s+', ' ', m).strip()
        # Skip generic phrases that aren't stall names
        generic = {
            'hokkien mee', 'fried hokkien mee', 'hkm', 'hokkien mie',
            'the hokkien mee', 'a hokkien mee', 'my hokkien mee',
            'this hokkien mee', 'good hokkien mee', 'nice hokkien mee',
        }
        if name.lower() in generic:
            continue
        if len(name) > 5 and len(name) < 60:
            candidates.append(name)

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
# Map generation
# ---------------------------------------------------------------------------
def build_map(geocoded_posts):
    """Build a Folium map with markers for geocoded posts."""
    m = folium.Map(
        location=SG_CENTRE,
        zoom_start=12,
        tiles=None,
    )

    # Add OneMap tile layer
    folium.TileLayer(
        tiles="https://www.onemap.gov.sg/maps/tiles/Default/{z}/{x}/{y}.png",
        attr='<img src="https://www.onemap.gov.sg/web-assets/images/logo/om_logo.png" '
             'style="height:20px;width:20px;"/> OneMap | '
             'Map data &copy; contributors, '
             '<a href="https://www.sla.gov.sg/">Singapore Land Authority</a>',
        name="OneMap Default",
        max_zoom=19,
    ).add_to(m)

    # Group markers by location to handle multiple posts at same spot
    location_groups = {}
    for item in geocoded_posts:
        key = f"{item['lat']:.6f},{item['lng']:.6f}"
        if key not in location_groups:
            location_groups[key] = []
        location_groups[key].append(item)

    for key, items in location_groups.items():
        lat = items[0]["lat"]
        lng = items[0]["lng"]

        # Build popup HTML
        popup_parts = []
        for item in items:
            post = item["post"]
            text_preview = post.get("text", "")[:150].replace("\n", "<br>")
            author = post.get("author", "Unknown")
            post_link = post.get("post_link", "")

            # Show images if available
            img_html = ""
            images = post.get("images", [])
            if images:
                img_html = (
                    f'<img src="{images[0]}" '
                    f'style="max-width:200px;max-height:150px;margin-top:5px;" '
                    f'onerror="this.style.display=\'none\'">'
                )

            popup_parts.append(
                f'<div style="margin-bottom:10px;border-bottom:1px solid #ccc;padding-bottom:8px;">'
                f'<b>{author}</b><br>'
                f'<small>{text_preview}</small><br>'
                f'{img_html}'
                f'<br><a href="{post_link}" target="_blank">View post →</a>'
                f'</div>'
            )

        popup_html = (
            f'<div style="max-width:300px;max-height:400px;overflow-y:auto;">'
            f'<b style="font-size:14px;">📍 {items[0]["address"]}</b><br>'
            f'<small style="color:gray;">{len(items)} post(s) at this location</small>'
            f'<hr style="margin:5px 0;">'
            f'{"".join(popup_parts)}'
            f'</div>'
        )

        folium.Marker(
            location=[lat, lng],
            popup=folium.Popup(popup_html, max_width=350),
            tooltip=f'{items[0]["address"]} ({len(items)} post{"s" if len(items) > 1 else ""})',
            icon=folium.Icon(color="red", icon="cutlery", prefix="fa"),
        ).add_to(m)

    return m


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

    # Build and save map
    print(f"\nBuilding map...")
    m = build_map(geocoded)
    m.save(OUTPUT_MAP)
    print(f"Map saved to {OUTPUT_MAP}")
    print(f"Open in browser: file://{os.path.abspath(OUTPUT_MAP)}")


if __name__ == "__main__":
    main()
