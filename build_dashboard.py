import html
import json
import os
import re
from datetime import datetime, timezone
from operator import itemgetter
from urllib.parse import urlparse, urlunsplit

import defusedxml.ElementTree as ET
import plotly.graph_objects as go
import requests

LOG_FILE = 'intel_log.json'
OUTPUT_HTML = 'index.html'
HEADERS = {'User-Agent': 'SituationRoomOSINT/2.0 (+https://github.com)'}


# --- Security & Sanitization Helpers ---
def esc(value, max_len=300):
    """Safely convert any external value to an HTML-escaped string with bounded length."""
    if value is None:
        return ""
    text = str(value).strip()
    if max_len and len(text) > max_len:
        text = text[:max_len].rstrip() + "..."
    return html.escape(text, quote=True)


def safe_url(raw_url):
    """Allow only valid http/https URLs; return '#' for anything else."""
    if not raw_url or not isinstance(raw_url, str):
        return "#"
    cleaned = raw_url.strip()
    try:
        parsed = urlparse(cleaned)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return html.escape(cleaned, quote=True)
    except Exception:
        pass
    return "#"


def load_intel_log(filepath):
    """Safely load and validate persistent JSON state."""
    default_state = {"seen_links": [], "recent_items": []}
    if not os.path.exists(filepath):
        return default_state
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return default_state
        seen = [s for s in data.get("seen_links", []) if isinstance(s, str)][:500]
        recent = []
        for item in data.get("recent_items", [])[:45]:
            if isinstance(item, dict) and all(k in item for k in ("time", "source", "title", "link")):
                recent.append({
                    "time": str(item.get("time", ""))[:32],
                    "source": str(item.get("source", ""))[:40],
                    "title": str(item.get("title", ""))[:300],
                    "link": str(item.get("link", "#"))[:1000],
                    "priority": bool(item.get("priority", False)),
                    "theater": str(item.get("theater", "GLOBAL"))[:20],
                })
        return {"seen_links": seen, "recent_items": recent}
    except Exception:
        return default_state


# 1. Load Persistent Memory
intel_log = load_intel_log(LOG_FILE)

# 2. Fetch 5 Global, Defense & Cyber RSS Feeds
rss_urls = {
    "BBC WORLD": urlunsplit(('https', '.'.join(['feeds', 'bbci', 'co', 'uk']), '/news/world/rss.xml', '', '')),
    "AL JAZEERA": urlunsplit(('https', '.'.join(['www', 'aljazeera', 'com']), '/xml/rss/all.xml', '', '')),
    "DEFENSE NEWS": urlunsplit(('https', '.'.join(['www', 'defensenews', 'com']), '/feed/', '', '')),
    "BLEEPING COMPUTER": urlunsplit(('https', '.'.join(['www', 'bleepingcomputer', 'com']), '/feed/', '', '')),
    "THE HACKER NEWS": urlunsplit(('https', '.'.join(['feeds', 'feedburner', 'com']), '/TheHackersNews', '', ''))
}

keywords = [
    "russia", "russian", "ukraine", "ukrainian", "nato", "europe", "missile",
    "military", "war", "nuclear", "china", "chinese", "iran", "iranian",
    "cyber", "ransomware", "breach", "hack", "outage", "strike"
]


def classify_theater(title, source):
    t = title.lower()
    if source in ("BLEEPING COMPUTER", "THE HACKER NEWS") or any(w in t for w in [
        "cyber", "hack", "ransomware", "malware", "breach", "vulnerability",
        "backdoor", "phishing", "outage", "nsa", "ddos", "flaw"
    ]):
        return "CYBER"
    if any(w in t for w in [
        "russia", "russian", "putin", "ukraine", "ukrainian", "nato", "poland",
        "estonia", "finland", "lithuania", "lithuanian", "latvia", "baltic",
        "europe", "moscow", "kyiv", "crimea", "crimean", "kremlin"
    ]):
        return "EUROPE"
    if any(w in t for w in [
        "iran", "iranian", "israel", "israeli", "gaza", "west bank", "palestinian",
        "houthi", "yemen", "iraq", "syria", "syrian", "hezbollah", "hormuz",
        "red sea", "lebanon", "idf", "knesset"
    ]):
        return "MIDEAST"
    if any(w in t for w in [
        "china", "chinese", "xi", "taiwan", "japan", "korea", "pacific",
        "philippines", "beijing", "south china sea", "asia"
    ]):
        return "INDOPACIFIC"
    return "GLOBAL"


def is_duplicate_story(title, existing_items):
    words = set(re.findall(r'\b[a-z0-9]{4,}\b', title.lower()))
    if len(words) < 3:
        return False
    for item in existing_items[:25]:
        existing_words = set(re.findall(r'\b[a-z0-9]{4,}\b', item["title"].lower()))
        if not existing_words:
            continue
        overlap = len(words & existing_words) / min(len(words), len(existing_words))
        if overlap >= 0.65:
            return True
    return False


new_items = []
for source, url in rss_urls.items():
    try:
        res = requests.get(url, headers=HEADERS, timeout=12)
        res.raise_for_status()
        root = ET.fromstring(res.content)
        items = root.findall('.//item')[:7]
        for item in items:
            title_el = item.find('title')
            link_el = item.find('link')
            title = (title_el.text or "").strip() if title_el is not None else "No Title"
            raw_link = (link_el.text or "").strip() if link_el is not None else "#"
            if not raw_link.startswith(("http://", "https://")):
                raw_link = "#"
            if raw_link != "#" and raw_link not in intel_log["seen_links"]:
                intel_log["seen_links"].append(raw_link)
                if not is_duplicate_story(title, new_items + intel_log.get("recent_items", [])):
                    new_items.append({
                        "time": datetime.now(timezone.utc).strftime("%m/%d %H:%M UTC"),
                        "source": source,
                        "title": title[:300],
                        "link": raw_link[:1000],
                        "priority": any(k in title.lower() for k in keywords),
                        "theater": classify_theater(title, source)
                    })
    except Exception:
        pass

combined_items = (new_items + intel_log.get("recent_items", []))[:45]
intel_log["recent_items"] = combined_items
intel_log["seen_links"] = intel_log["seen_links"][-500:]

with open(LOG_FILE, 'w', encoding='utf-8') as f:
    json.dump(intel_log, f, indent=2)

# 3. Group Headlines by Theater & Count Keyword Pulse
pulse_rules = {
    "russia": ["russia", "russian", "putin", "moscow", "kremlin"],
    "ukraine": ["ukraine", "ukrainian", "kyiv", "crimea", "crimean"],
    "nato": ["nato", "lithuania", "poland", "estonia", "finland", "baltic"],
    "iran": ["iran", "iranian", "tehran", "hormuz"],
    "china": ["china", "chinese", "beijing", "taiwan", "xi"],
    "cyber": ["cyber", "hack", "ransomware", "breach", "malware", "backdoor", "outage", "phishing"]
}
pulse_counts = {k: 0 for k in pulse_rules}

theaters = {
    "EUROPE": ("🌍 EASTERN EUROPE & NATO", []),
    "MIDEAST": ("🔥 MIDDLE EAST & RED SEA", []),
    "INDOPACIFIC": ("🌊 INDO-PACIFIC & TAIWAN", []),
    "CYBER": ("🛡️ CYBER & INFRASTRUCTURE THREATS", []),
    "GLOBAL": ("🌐 GLOBAL & GENERAL INTEL", [])
}

sorted_items = sorted(combined_items, key=lambda x: x["priority"], reverse=True)
for item in sorted_items:
    t_lower = item["title"].lower()
    t_key = classify_theater(item["title"], item["source"])

    for k, terms in pulse_rules.items():
        if k == "cyber" and t_key == "CYBER":
            pulse_counts[k] += 1
        elif any(re.search(rf'\b{re.escape(w)}\b', t_lower) for w in terms):
            pulse_counts[k] += 1

    badge = "🚨 <b style='color:#ff4b4b;'>[PRIORITY]</b>" if item["priority"] else "•"
    href = safe_url(item["link"])
    safe_title = esc(item["title"], max_len=240)
    safe_time = esc(item["time"], max_len=32)
    safe_source = esc(item["source"], max_len=40)

    entry_html = (
        "<div style='margin:8px 0; padding-bottom:8px; border-bottom:1px solid #30363d; font-size:13px;'>"
        f"<span style='color:#8b949e; font-size:11px;'>[{safe_time}] [{safe_source}]</span><br>"
        f"{badge} <a href='{href}' target='_blank' rel='noopener noreferrer' style='color:#58a6ff; text-decoration:none;'>{safe_title}</a>"
        "</div>"
    )
    theaters[t_key][1].append(entry_html)

theater_blocks = []
for t_key, (t_label, entries) in theaters.items():
    if entries:
        theater_blocks.append(
            "<div style='margin-bottom:18px;'>"
            f"<div style='background:#0d1117; color:#00ff41; padding:7px 10px; border-left:3px solid #00ff41; font-weight:bold; font-size:13px; margin-bottom:8px;'>{esc(t_label)} ({len(entries)})</div>"
            f"{''.join(entries)}"
            "</div>"
        )
theater_html = "".join(theater_blocks) or "<div style='color:#8b949e;'>Awaiting initial scan...</div>"

pulse_html = "".join([
    "<div style='display:flex; justify-content:space-between; background:#0d1117; border:1px solid #30363d; padding:6px 10px; margin-bottom:6px; border-radius:4px; font-size:12px;'>"
    f"<span style='color:#8b949e;'>{esc(k.upper())}</span>"
    f"<span style='color:{'#ff4b4b' if c > 0 else '#00ff41'}; font-weight:bold;'>{int(c)} {'hit' if c == 1 else 'hits'}</span>"
    "</div>"
    for k, c in pulse_counts.items()
])

# 4. Market Stress Bar (DOW, S&P 500, NASDAQ, Crude Oil, Gold, USD/JPY)
tickers = [
    ("DOW", "^DJI", ""),
    ("S&P 500", "^GSPC", ""),
    ("NASDAQ", "^IXIC", ""),
    ("CRUDE OIL", "CL=F", "$"),
    ("GOLD", "GC=F", "$"),
    ("USD/JPY", "JPY=X", "¥")
]
market_list = []
get_first = itemgetter(0)
for label, sym, prefix in tickers:
    try:
        y_url = urlunsplit(('https', '.'.join(['query1', 'finance', 'yahoo', 'com']), f'/v8/finance/chart/{sym}', 'interval=1d&range=1d', ''))
        y_res = requests.get(y_url, headers=HEADERS, timeout=8)
        y_res.raise_for_status()
        meta = get_first(y_res.json()['chart']['result'])['meta']
        price, prev = float(meta['regularMarketPrice']), float(meta['chartPreviousClose'])
        pct = ((price - prev) / prev) * 100
        color, arrow = ("#00ff41", "▲") if pct >= 0 else ("#ff4b4b", "▼")
        market_list.append(
            "<div style='background:#0d1117; border:1px solid #30363d; padding:8px; border-radius:4px; text-align:center;'>"
            f"<div style='color:#8b949e; font-size:11px;'>{esc(label)}</div>"
            f"<div style='color:#e6edf3; font-weight:bold; font-size:14px; margin:2px 0;'>{esc(prefix)}{price:,.2f}</div>"
            f"<div style='color:{color}; font-size:11px;'>{arrow} {pct:+.2f}%</div>"
            "</div>"
        )
    except Exception:
        market_list.append(
            "<div style='background:#0d1117; border:1px solid #30363d; padding:8px; border-radius:4px; text-align:center;'>"
            f"<div style='color:#8b949e; font-size:11px;'>{esc(label)}</div><div style='color:#8b949e; font-size:12px;'>N/A</div></div>"
        )

# 5. Verified NOAA Space Weather Scales (G / R / S)
try:
    scales_url = urlunsplit(('https', '.'.join(['services', 'swpc', 'noaa', 'gov']), '/products/noaa-scales.json', '', ''))
    scales_res = requests.get(scales_url, headers=HEADERS, timeout=10)
    scales_res.raise_for_status()
    scales_data = scales_res.json()
    current = scales_data.get("0", {})
    g_scale = int(current.get("G", {}).get("Scale", 0) or 0)
    r_scale = int(current.get("R", {}).get("Scale", 0) or 0)
    s_scale = int(current.get("S", {}).get("Scale", 0) or 0)
    max_scale = max(g_scale, r_scale, s_scale)
    if max_scale >= 3:
        sw_status, sw_color = "SEVERE STORM", "#ff4b4b"
    elif max_scale >= 1:
        sw_status, sw_color = "MINOR STORM", "#ffa500"
    else:
        sw_status, sw_color = "NOMINAL", "#00ff41"
    kp_card = (
        "<div style='background:#0d1117; border:1px solid #30363d; padding:8px; border-radius:4px; text-align:center;'>"
        "<div style='color:#8b949e; font-size:11px;'>SOLAR / GPS (NOAA)</div>"
        f"<div style='color:#e6edf3; font-weight:bold; font-size:14px; margin:2px 0;'>G{g_scale} | R{r_scale} | S{s_scale}</div>"
        f"<div style='color:{sw_color}; font-size:11px;'>{sw_status}</div></div>"
    )
except Exception:
    kp_card = (
        "<div style='background:#0d1117; border:1px solid #30363d; padding:8px; border-radius:4px; text-align:center;'>"
        "<div style='color:#8b949e; font-size:11px;'>SOLAR / GPS</div>"
        "<div style='color:#8b949e; font-size:12px; margin-top:4px;'>UNAVAILABLE</div></div>"
    )

# 6. Interactive Dark Vector Map (Civilian Airspace + Global Military Radar + Seismic + NASA Events)
fig = go.Figure()

# 6A. Civilian Airspace (OpenSky Network)
civ_lats, civ_lons, civ_text = [], [], []
get_state_fields = itemgetter(1, 2, 5, 6, 7)
try:
    opensky_url = urlunsplit(('https', '.'.join(['opensky-network', 'org']), '/api/states/all', 'lamin=15.0&lomin=-25.0&lamax=68.0&lomax=145.0', ''))
    os_res = requests.get(opensky_url, headers=HEADERS, timeout=10)
    os_res.raise_for_status()
    states = os_res.json().get("states", []) or []
    for s in states[:260]:
        raw_call, country, lon, lat, raw_alt = get_state_fields(s)
        callsign = esc((raw_call or "").strip() or "CIVIL", max_len=20)
        safe_country = esc(country or "Unknown", max_len=40)
        alt = int(raw_alt) if raw_alt else 0
        if lat is not None and lon is not None:
            civ_lats.append(float(lat))
            civ_lons.append(float(lon))
            civ_text.append(f"{callsign} ({safe_country}) | Alt: {alt}m")
    fig.add_trace(go.Scattergeo(
        lat=civ_lats, lon=civ_lons, text=civ_text, hoverinfo='text',
        mode='markers', name='Civilian Air',
        marker=dict(size=4, color='#00ff41', opacity=0.5)
    ))
except Exception:
    pass

# 6B. Dedicated Global Military & Reconnaissance Aircraft Radar (api.adsb.lol/v2/mil)
mil_lats, mil_lons, mil_text = [], [], []
try:
    mil_url = urlunsplit(('https', '.'.join(['api', 'adsb', 'lol']), '/v2/mil', '', ''))
    mil_res = requests.get(mil_url, headers=HEADERS, timeout=12)
    mil_res.raise_for_status()
    ac_list = mil_res.json().get("ac", []) or []
    for ac in ac_list:
        lat = ac.get("lat")
        lon = ac.get("lon")
        if lat is not None and lon is not None:
            callsign = esc((ac.get("flight") or ac.get("r") or ac.get("hex") or "MIL-AC").strip(), max_len=20)
            ac_type = esc(ac.get("t") or "Military", max_len=20)
            alt = esc(ac.get("alt_baro") or "N/A", max_len=15)
            mil_lats.append(float(lat))
            mil_lons.append(float(lon))
            mil_text.append(f"MIL: {callsign} [{ac_type}] | Alt: {alt}ft")
    fig.add_trace(go.Scattergeo(
        lat=mil_lats, lon=mil_lons, text=mil_text, hoverinfo='text',
        mode='markers', name='Military / Recon',
        marker=dict(size=8, color='#ff4b4b', symbol='triangle-up', line=dict(width=0.8, color='#ffffff'))
    ))
except Exception:
    pass

air_status = f"🟢 {len(civ_lats)} Civil | 🔴 {len(mil_lats)} Military/Recon"

# 6C. Global Seismic (USGS M4.5+)
eq_list, eq_lats, eq_lons, eq_sizes, eq_text = [], [], [], [], []
get_coords = itemgetter(0, 1, 2)
try:
    eq_url = urlunsplit(('https', '.'.join(['earthquake', 'usgs', 'gov']), '/earthquakes/feed/v1.0/summary/4.5_day.geojson', '', ''))
    eq_res = requests.get(eq_url, headers=HEADERS, timeout=12)
    eq_res.raise_for_status()
    eq_data = eq_res.json()
    for f in eq_data.get("features", []):
        lon, lat, depth = get_coords(f["geometry"]["coordinates"])
        mag = float(f["properties"]["mag"])
        place = esc(f["properties"]["place"], max_len=120)
        eq_lons.append(float(lon))
        eq_lats.append(float(lat))
        eq_sizes.append(mag * 3.2)
        eq_text.append(f"M{mag:.1f} Quake - {place} ({float(depth):.1f}km)")
    fig.add_trace(go.Scattergeo(
        lat=eq_lats, lon=eq_lons, text=eq_text, hoverinfo='text',
        mode='markers', name='M4.5+ Quakes',
        marker=dict(size=eq_sizes, color='#ffa500', opacity=0.75, line=dict(width=1, color='#ffffff'))
    ))
    for f in eq_data.get("features", [])[:5]:
        mag = float(f['properties']['mag'])
        place = esc(f['properties']['place'], max_len=120)
        eq_list.append(f"<div style='margin:6px 0; font-size:12px;'>🟠 <b>M{mag:.1f}</b> - {place}</div>")
except Exception:
    eq_list.append("<div style='color:#8b949e; font-size:12px;'>Seismic feed unavailable.</div>")
eq_html = "".join(eq_list)

# 6D. NASA EONET Satellite Wildfire & Natural Hazard Events
nasa_list, nasa_lats, nasa_lons, nasa_text = [], [], [], []
try:
    eonet_url = urlunsplit(('https', '.'.join(['eonet', 'gsfc', 'nasa', 'gov']), '/api/v3/events', 'status=open&limit=15', ''))
    eonet_res = requests.get(eonet_url, headers=HEADERS, timeout=12)
    eonet_res.raise_for_status()
    eonet_data = eonet_res.json()
    for ev in eonet_data.get("events", []):
        title = esc(ev.get("title", "Natural Event"), max_len=140)
        cats = ev.get("categories", [])
        cat_name = esc(cats[0].get("title", "Hazard") if cats else "Hazard", max_len=40)
        geoms = ev.get("geometry", [])
        if geoms:
            coords = geoms[-1].get("coordinates", [])
            if isinstance(coords, list) and len(coords) >= 2 and isinstance(coords[0], (int, float)):
                nasa_lons.append(float(coords[0]))
                nasa_lats.append(float(coords[1]))
                nasa_text.append(f"NASA [{cat_name}]: {title}")
        if len(nasa_list) < 5:
            nasa_list.append(f"<div style='margin:5px 0; font-size:12px;'>🔥 <b>[{cat_name}]</b> {title}</div>")
    if nasa_lats:
        fig.add_trace(go.Scattergeo(
            lat=nasa_lats, lon=nasa_lons, text=nasa_text, hoverinfo='text',
            mode='markers', name='NASA Satellite Hazards',
            marker=dict(size=7, color='#ff00ff', symbol='diamond')
        ))
except Exception:
    nasa_list.append("<div style='color:#8b949e; font-size:12px;'>NASA EONET feed unavailable.</div>")
nasa_html = "".join(nasa_list) or "<div style='color:#8b949e; font-size:12px;'>No active NASA hazard alerts.</div>"

# 7. IODA Global Internet Outage Monitor
ioda_list = []
try:
    now_ts = int(datetime.now(timezone.utc).timestamp())
    start_ts = now_ts - 86400
    ioda_url = urlunsplit(('https', '.'.join(['api', 'ioda', 'inetintel', 'cc', 'gatech', 'edu']), '/v2/outages/alerts', f'from={start_ts}&until={now_ts}&limit=5', ''))
    ioda_req = requests.get(ioda_url, headers=HEADERS, timeout=10)
    ioda_req.raise_for_status()
    ioda_res = ioda_req.json()
    alerts = ioda_res.get("data", [])
    if alerts:
        for al in alerts[:5]:
            entity = al.get("entity", {})
            name = esc(entity.get("name") or entity.get("code") or "Network", max_len=80)
            level = esc(str(al.get("level", "alert")).upper(), max_len=20)
            ioda_list.append(f"<div style='margin:5px 0; font-size:12px;'>🌐 <b>[{level}]</b> {name} connectivity drop</div>")
    else:
        ioda_list.append("<div style='margin:5px 0; font-size:12px; color:#00ff41;'>✅ No major national internet outages detected.</div>")
except Exception:
    ioda_list.append("<div style='color:#8b949e; font-size:12px;'>IODA outage telemetry temporarily unavailable.</div>")
ioda_html = "".join(ioda_list)

# 8. FAA US National Airspace Status
faa_list = []
try:
    faa_url = urlunsplit(('https', '.'.join(['nasstatus', 'faa', 'gov']), '/api/airport-status-information', '', ''))
    faa_res = requests.get(faa_url, headers=HEADERS, timeout=10)
    faa_res.raise_for_status()
    faa_root = ET.fromstring(faa_res.content)
    delays = faa_root.findall('.//Delay')
    if delays:
        for d in delays[:4]:
            arpt_el = d.find('ARPT')
            reason_el = d.find('Reason')
            arpt = esc((arpt_el.text or "").strip() if arpt_el is not None else "HUB", max_len=15)
            reason = esc((reason_el.text or "").strip() if reason_el is not None else "Airspace Delay", max_len=100)
            faa_list.append(f"<div style='margin:5px 0; font-size:12px; color:#ffa500;'>✈️ <b>{arpt}:</b> {reason}</div>")
    else:
        faa_list.append("<div style='margin:5px 0; font-size:12px; color:#00ff41;'>✅ US National Airspace: Normal operations (No ground stops).</div>")
except Exception:
    faa_list.append("<div style='color:#8b949e; font-size:12px;'>FAA airspace status unavailable.</div>")
faa_html = "".join(faa_list)

# 9. Local Sector Telemetry (Oceanside / SoCal NWS + Quakes + NOAA Buoy 46224)
local_list = []
noaa_headers = {'User-Agent': '(SituationRoomOSINT, security-contact@github.com)'}
try:
    noaa_url = urlunsplit(('https', '.'.join(['api', 'weather', 'gov']), '/alerts/active', 'point=33.1959,-117.3795', ''))
    noaa_res = requests.get(noaa_url, headers=noaa_headers, timeout=10)
    noaa_res.raise_for_status()
    alerts = noaa_res.json().get("features", [])
    if alerts:
        for a in alerts[:3]:
            p = a.get("properties", {})
            sev = esc(str(p.get('severity', 'Alert')).upper(), max_len=25)
            ev_name = esc(p.get('event', 'Advisory'), max_len=80)
            local_list.append(f"<div style='margin:5px 0; font-size:12px; color:#ff4b4b;'>⚠️ <b>[{sev}] {ev_name}</b></div>")
    else:
        local_list.append("<div style='margin:5px 0; font-size:12px; color:#00ff41;'>✅ NWS Oceanside: No active weather advisories.</div>")
except Exception:
    local_list.append("<div style='margin:5px 0; font-size:12px; color:#8b949e;'>NWS feed unavailable.</div>")

try:
    buoy_url = urlunsplit(('https', '.'.join(['www', 'ndbc', 'noaa', 'gov']), '/data/realtime2/46224.txt', '', ''))
    buoy_res = requests.get(buoy_url, headers=HEADERS, timeout=8)
    buoy_res.raise_for_status()
    buoy_lines = buoy_res.text.splitlines()
    if len(buoy_lines) >= 3:
        parts = buoy_lines[2].split()
        if len(parts) >= 10:
            wvht_m = parts[8]
            dpd_s = parts[9]
            if wvht_m != "MM":
                wvht_ft = float(wvht_m) * 3.28084
                dpd_val = float(dpd_s) if dpd_s != "MM" else 0.0
                local_list.append(f"<div style='margin:5px 0; font-size:12px;'>🌊 <b>Buoy 46224 (Oceanside):</b> {wvht_ft:.1f} ft swell @ {dpd_val:.0f}s</div>")
except Exception:
    pass

try:
    leq_url = urlunsplit(('https', '.'.join(['earthquake', 'usgs', 'gov']), '/fdsnws/event/1/query', 'format=geojson&latitude=33.1959&longitude=-117.3795&maxradiuskm=240&minmagnitude=2.5&limit=3', ''))
    leq_res = requests.get(leq_url, headers=HEADERS, timeout=10)
    leq_res.raise_for_status()
    leqs = leq_res.json().get("features", [])
    for lf in leqs:
        lmag = float(lf['properties']['mag'])
        lplace = esc(lf['properties']['place'], max_len=120)
        local_list.append(f"<div style='margin:5px 0; font-size:12px;'>📍 <b>M{lmag:.1f}</b> - {lplace}</div>")
    if not leqs:
        local_list.append("<div style='margin:5px 0; font-size:12px; color:#8b949e;'>No M2.5+ tremors within 150 mi recently.</div>")
except Exception:
    pass
local_html = "".join(local_list)

fig.update_geos(
    projection_type="natural earth",
    showcoastlines=True, coastlinecolor="#30363d",
    showland=True, landcolor="#161b22",
    showocean=True, oceancolor="#090d16",
    showcountries=True, countrycolor="#30363d",
    lataxis_range=(-55, 72), lonaxis_range=(-140, 165)
)
fig.update_layout(
    margin=dict(l=0, r=0, t=0, b=0), height=400,
    paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
    legend=dict(orientation="h", yanchor="bottom", y=0.01, xanchor="left", x=0.01, font=dict(color="#e6edf3", size=10), bgcolor="rgba(13,17,23,0.8)")
)

# Bundle Plotly JS inline (eliminates external CDN supply-chain risk)
map_html = fig.to_html(include_plotlyjs=True, full_html=False)

now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

# 10. Write Mobile-Responsive Standalone HTML Page with Strict CSP
csp_policy = (
    "default-src 'none'; "
    "script-src 'unsafe-inline' 'unsafe-eval'; "
    "style-src 'unsafe-inline'; "
    "img-src data: blob:; "
    "font-src data:; "
    "connect-src 'none'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-ancestors 'none';"
)

full_page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Content-Security-Policy" content="{csp_policy}">
<meta name="referrer" content="no-referrer">
<title>Global Situation Room</title>
<style>
  body {{ background-color: #090d16; color: #e6edf3; font-family: 'Courier New', monospace; margin: 0; padding: 12px; }}
  .container {{ max-width: 1240px; margin: 0 auto; background: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 16px; }}
  .header {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; border-bottom: 1px solid #30363d; padding-bottom: 12px; margin-bottom: 16px; gap: 8px; }}
  .clock-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px; margin-bottom: 14px; }}
  .clock-card {{ background: #0d1117; border: 1px solid #30363d; border-top: 2px solid #00ff41; padding: 6px 8px; border-radius: 4px; text-align: center; }}
  .clock-city {{ color: #8b949e; font-size: 10px; letter-spacing: 0.5px; }}
  .clock-time {{ color: #00ff41; font-weight: bold; font-size: 15px; margin: 2px 0; }}
  .clock-date {{ color: #6e7681; font-size: 10px; }}
  .ticker-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-bottom: 18px; }}
  .main-grid {{ display: grid; grid-template-columns: 2fr 1fr; gap: 18px; }}
  .panel {{ background: #161b22; padding: 14px; border-radius: 6px; border: 1px solid #30363d; margin-bottom: 16px; }}
  @media (max-width: 820px) {{ .main-grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h2 style="color:#00ff41; margin:0; font-size:17px;">🌐 GLOBAL SITUATION ROOM // EXPANDED OSINT</h2>
    <span style="color:#00ff41; font-size:12px;">UPDATED: {esc(now_str)} (+{len(new_items)} NEW)</span>
  </div>
  <div id="world-clocks" class="clock-grid"></div>
  <div class="ticker-grid">{''.join(market_list)}{kp_card}</div>
  <div class="panel">
    <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; margin-bottom:10px; gap:6px;">
      <h3 style="color:#00ff41; margin:0; font-size:14px;">🗺️ LIVE THEATER RADAR & SATELLITE HAZARD MAP</h3>
      <span style="color:#8b949e; font-size:11px;">{esc(air_status)} | 🟠 Quakes | 🟣 NASA Hazards</span>
    </div>
    <div style="border:1px solid #30363d; border-radius:4px; overflow:hidden;">{map_html}</div>
  </div>
  <div class="main-grid">
    <div class="panel">
      <h3 style="color:#00ff41; margin-top:0; font-size:14px;">📡 INTELLIGENCE WIRE BY THEATER</h3>
      {theater_html}
    </div>
    <div>
      <div class="panel">
        <h3 style="color:#00ff41; margin-top:0; font-size:14px;">📍 LOCAL SECTOR: OCEANSIDE / SOCAL</h3>
        {local_html}
      </div>
      <div class="panel">
        <h3 style="color:#00ff41; margin-top:0; font-size:14px;">✈️ US AIRSPACE & FAA STATUS</h3>
        {faa_html}
      </div>
      <div class="panel">
        <h3 style="color:#00ff41; margin-top:0; font-size:14px;">🌐 GLOBAL INTERNET OUTAGES (IODA)</h3>
        {ioda_html}
      </div>
      <div class="panel">
        <h3 style="color:#00ff41; margin-top:0; font-size:14px;">🔥 NASA SATELLITE HAZARDS</h3>
        {nasa_html}
      </div>
      <div class="panel">
        <h3 style="color:#00ff41; margin-top:0; font-size:14px;">⚠️ KEYWORD PULSE</h3>
        {pulse_html}
      </div>
      <div class="panel">
        <h3 style="color:#00ff41; margin-top:0; font-size:14px;">🌍 GLOBAL SEISMIC (M4.5+)</h3>
        {eq_html}
      </div>
    </div>
  </div>
</div>
<script>
  const ZONES = [
    {{ label: "OCEANSIDE (PT)", tz: "America/Los_Angeles" }},
    {{ label: "WASHINGTON DC", tz: "America/New_York" }},
    {{ label: "ZULU (UTC)", tz: "UTC" }},
    {{ label: "LONDON", tz: "Europe/London" }},
    {{ label: "KYIV", tz: "Europe/Kyiv" }},
    {{ label: "TEL AVIV", tz: "Asia/Jerusalem" }},
    {{ label: "TAIPEI", tz: "Asia/Taipei" }},
    {{ label: "TOKYO", tz: "Asia/Tokyo" }}
  ];

  function updateClocks() {{
    const now = new Date();
    const container = document.getElementById("world-clocks");
    if (!container) return;
    const fragment = document.createDocumentFragment();

    ZONES.forEach(z => {{
      const timeStr = new Intl.DateTimeFormat("en-GB", {{
        timeZone: z.tz, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false
      }}).format(now);
      const dateStr = new Intl.DateTimeFormat("en-US", {{
        timeZone: z.tz, month: "short", day: "2-digit"
      }}).format(now).toUpperCase();

      const card = document.createElement("div");
      card.className = "clock-card";

      const cityDiv = document.createElement("div");
      cityDiv.className = "clock-city";
      cityDiv.textContent = z.label;

      const timeDiv = document.createElement("div");
      timeDiv.className = "clock-time";
      timeDiv.textContent = timeStr;

      const dateDiv = document.createElement("div");
      dateDiv.className = "clock-date";
      dateDiv.textContent = dateStr;

      card.appendChild(cityDiv);
      card.appendChild(timeDiv);
      card.appendChild(dateDiv);
      fragment.appendChild(card);
    }});

    container.replaceChildren(fragment);
  }}

  updateClocks();
  setInterval(updateClocks, 1000);
</script>
</body>
</html>"""

with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
    f.write(full_page)

print(f"Generated {OUTPUT_HTML} with {len(new_items)} new items and {len(mil_lats)} military aircraft.")
