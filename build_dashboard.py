import json
import os
import requests
from operator import itemgetter
from urllib.parse import urlunsplit
from bs4 import BeautifulSoup
import plotly.graph_objects as go
from datetime import datetime, timezone

LOG_FILE = 'intel_log.json'
OUTPUT_HTML = 'index.html'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

if os.path.exists(LOG_FILE):
    with open(LOG_FILE, 'r') as f:
        intel_log = json.load(f)
else:
    intel_log = {"seen_links": [], "recent_items": []}

rss_urls = {
    "BBC WORLD": urlunsplit(('https', '.'.join(['feeds', 'bbci', 'co', 'uk']), '/news/world/rss.xml', '', '')),
    "AL JAZEERA": urlunsplit(('https', '.'.join(['www', 'aljazeera', 'com']), '/xml/rss/all.xml', '', '')),
    "DEFENSE NEWS": urlunsplit(('https', '.'.join(['www', 'defensenews', 'com']), '/feed/', '', '')),
    "BLEEPING COMPUTER": urlunsplit(('https', '.'.join(['www', 'bleepingcomputer', 'com']), '/feed/', '', '')),
    "THE HACKER NEWS": urlunsplit(('https', '.'.join(['feeds', 'feedburner', 'com']), '/TheHackersNews', '', ''))
}

keywords = [
    "russia", "ukraine", "nato", "europe", "missile", "military", "war",
    "nuclear", "china", "iran", "cyber", "ransomware", "breach", "hack",
    "outage", "san diego", "california", "tsunami"
]

def classify_theater(title, source):
    t = title.lower()
    if source in ("BLEEPING COMPUTER", "THE HACKER NEWS") or any(w in t for w in ["cyber", "hack", "ransomware", "malware", "breach", "vulnerability", "outage"]):
        return "CYBER"
    if any(w in t for w in ["russia", "ukraine", "nato", "poland", "estonia", "finland", "baltic", "europe", "moscow", "kyiv"]):
        return "EUROPE"
    if any(w in t for w in ["iran", "israel", "gaza", "houthi", "yemen", "iraq", "syria", "hezbollah", "hormuz", "red sea", "lebanon"]):
        return "MIDEAST"
    if any(w in t for w in ["china", "taiwan", "japan", "korea", "pacific", "philippines", "beijing"]):
        return "INDOPACIFIC"
    return "GLOBAL"

new_items = []
for source, url in rss_urls.items():
    try:
        res = requests.get(url, headers=HEADERS, timeout=12)
        res.raise_for_status()
        soup = BeautifulSoup(res.content, features='xml')
        for item in soup.find_all('item')[:7]:
            title = item.find('title').get_text(strip=True) if item.find('title') else "No Title"
            link = item.find('link').get_text(strip=True) if item.find('link') else "#"
            if link not in intel_log["seen_links"]:
                intel_log["seen_links"].append(link)
                new_items.append({
                    "time": datetime.now(timezone.utc).strftime("%m/%d %H:%M UTC"),
                    "source": source,
                    "title": title,
                    "link": link,
                    "priority": any(k in title.lower() for k in keywords),
                    "theater": classify_theater(title, source)
                })
    except Exception:
        pass

combined_items = (new_items + intel_log.get("recent_items", []))[:45]
intel_log["recent_items"] = combined_items
intel_log["seen_links"] = intel_log["seen_links"][-500:]

with open(LOG_FILE, 'w') as f:
    json.dump(intel_log, f, indent=2)

pulse_terms = ["russia", "ukraine", "nato", "iran", "china", "cyber"]
pulse_counts = {k: 0 for k in pulse_terms}

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
    for k in pulse_terms:
        if k in t_lower:
            pulse_counts[k] += 1
    badge = "🚨 <b style='color:#ff4b4b;'>[PRIORITY]</b>" if item["priority"] else "•"
    entry_html = (
        "<div style='margin:8px 0; padding-bottom:8px; border-bottom:1px solid #30363d; font-size:13px;'>"
        f"<span style='color:#8b949e; font-size:11px;'>[{item['time']}] [{item['source']}]</span><br>"
        f"{badge} <a href='{item['link']}' target='_blank' style='color:#58a6ff; text-decoration:none;'>{item['title']}</a>"
        "</div>"
    )
    t_key = item.get("theater", "GLOBAL")
    if t_key not in theaters:
        t_key = "GLOBAL"
    theaters[t_key].append(entry_html)

theater_blocks = []
for t_key, (t_label, entries) in theaters.items():
    if entries:
        theater_blocks.append(
            "<div style='margin-bottom:18px;'>"
            f"<div style='background:#0d1117; color:#00ff41; padding:7px 10px; border-left:3px solid #00ff41; font-weight:bold; font-size:13px; margin-bottom:8px;'>{t_label} ({len(entries)})</div>"
            f"{''.join(entries)}"
            "</div>"
        )
theater_html = "".join(theater_blocks) or "<div style='color:#8b949e;'>Awaiting initial scan...</div>"

pulse_html = "".join([
    "<div style='display:flex; justify-content:space-between; background:#0d1117; border:1px solid #30363d; padding:6px 10px; margin-bottom:6px; border-radius:4px; font-size:12px;'>"
    f"<span style='color:#8b949e;'>{k.upper()}</span>"
    f"<span style='color:{'#ff4b4b' if c > 0 else '#00ff41'}; font-weight:bold;'>{c} hits</span>"
    "</div>"
    for k, c in pulse_counts.items()
])

tickers = {"BRENT OIL": "BZ=F", "GOLD": "GC=F", "LOCKHEED (LMT)": "LMT", "BITCOIN": "BTC-USD"}
market_list = []
get_first = itemgetter(0)
for label, sym in tickers.items():
    try:
        y_url = urlunsplit(('https', '.'.join(['query1', 'finance', 'yahoo', 'com']), f'/v8/finance/chart/{sym}', 'interval=1d&range=1d', ''))
        y_res = requests.get(y_url, headers=HEADERS, timeout=8)
        meta = get_first(y_res.json()['chart']['result'])['meta']
        price, prev = meta['regularMarketPrice'], meta['chartPreviousClose']
        pct = ((price - prev) / prev) * 100
        color, arrow = ("#00ff41", "▲") if pct >= 0 else ("#ff4b4b", "▼")
        market_list.append(
            "<div style='background:#0d1117; border:1px solid #30363d; padding:8px; border-radius:4px; text-align:center;'>"
            f"<div style='color:#8b949e; font-size:11px;'>{label}</div>"
            f"<div style='color:#e6edf3; font-weight:bold; font-size:14px; margin:2px 0;'>${price:,.2f}</div>"
            f"<div style='color:{color}; font-size:11px;'>{arrow} {pct:+.2f}%</div>"
            "</div>"
        )
    except Exception:
        market_list.append(
            "<div style='background:#0d1117; border:1px solid #30363d; padding:8px; border-radius:4px; text-align:center;'>"
            f"<div style='color:#8b949e; font-size:11px;'>{label}</div><div style='color:#8b949e; font-size:12px;'>N/A</div></div>"
        )

try:
    kp_url = urlunsplit(('https', '.'.join(['services', 'swpc', 'noaa', 'gov']), '/products/noaa-planetary-k-index.json', '', ''))
    kp_rows = requests.get(kp_url, headers=HEADERS, timeout=8).json()
    last_kp_row = kp_rows[-1]
    if isinstance(last_kp_row, dict):
        raw_kp = last_kp_row.get('Kp') or last_kp_row.get('kp_index') or last_kp_row.get('kp')
    else:
        raw_kp = last_kp_row[1]
    latest_kp = float(raw_kp)
    kp_status, kp_color = ("G-STORM", "#ff4b4b") if latest_kp >= 5.0 else (("UNSETTLED", "#ffa500") if latest_kp >= 4.0 else ("NOMINAL", "#00ff41"))
    kp_card = (
        "<div style='background:#0d1117; border:1px solid #30363d; padding:8px; border-radius:4px; text-align:center;'>"
        "<div style='color:#8b949e; font-size:11px;'>SOLAR / GPS (KP)</div>"
        f"<div style='color:#e6edf3; font-weight:bold; font-size:14px; margin:2px 0;'>Kp {latest_kp:.1f}</div>"
        f"<div style='color:{kp_color}; font-size:11px;'>{kp_status}</div></div>"
    )
except Exception:
    kp_card = "<div style='background:#0d1117; border:1px solid #30363d; padding:8px; border-radius:4px; text-align:center;'><div style='color:#8b949e; font-size:11px;'>SOLAR / GPS</div><div style='color:#8b949e; font-size:12px;'>N/A</div></div>"

fig = go.Figure()
mil_prefixes = (
    "RCH", "REACH", "FORTE", "NATO", "DUKE", "JAKE", "HOMER", "LAGR", "RRR",
    "CNV", "ASY", "CFC", "QID", "HOBO", "NCHO", "MMF", "GAF", "FAF", "RAF",
    "IAM", "BAF", "PLF", "SWF", "HAF", "TUAF", "SPAR", "SAM", "EXEC", "PAT",
    "BOXER", "USAF", "NAVY", "ARMY", "GOLD", "BLUE", "VIPER", "CONV"
)
civ_lats, civ_lons, civ_text, mil_lats, mil_lons, mil_text = [], [], [], [], [], []
get_state_fields = itemgetter(1, 2, 5, 6, 7)

try:
    opensky_url = urlunsplit(('https', '.'.join(['opensky-network', 'org']), '/api/states/all', 'lamin=22.0&lomin=-12.0&lamax=64.0&lomax=60.0', ''))
    states = requests.get(opensky_url, headers=HEADERS, timeout=12).json().get("states", []) or []
    for s in states:
        raw_call, country, lon, lat, raw_alt = get_state_fields(s)
        callsign = (raw_call or "").strip().upper() or "UNKNOWN"
        alt = int(raw_alt) if raw_alt else 0
        if lat is not None and lon is not None:
            label = f"{callsign} ({country or 'Unknown'}) | Alt: {alt}m"
            if callsign.startswith(mil_prefixes):
                mil_lats.append(lat); mil_lons.append(lon); mil_text.append(label)
            elif len(civ_lats) < 250:
                civ_lats.append(lat); civ_lons.append(lon); civ_text.append(label)
    fig.add_trace(go.Scattergeo(lat=civ_lats, lon=civ_lons, text=civ_text, hoverinfo='text', mode='markers', name='Civilian Air', marker=dict(size=4, color='#00ff41', opacity=0.6)))
    fig.add_trace(go.Scattergeo(lat=mil_lats, lon=mil_lons, text=mil_text, hoverinfo='text', mode='markers', name='Tracked / Mil Callsigns', marker=dict(size=9, color='#ff4b4b', symbol='triangle-up', line=dict(width=0.8, color='#ffffff'))))
    air_status = f"🟢 {len(civ_lats)} Civ | 🔴 {len(mil_lats)} Tracked ({len(states)} Scanned)"
except Exception:
    air_status = "⚠️ Airspace Telemetry Throttled"

eq_list, eq_lats, eq_lons, eq_sizes, eq_text = [], [], [], [], []
get_coords = itemgetter(0, 1, 2)
try:
    eq_url = urlunsplit(('https', '.'.join(['earthquake', 'usgs', 'gov']), '/earthquakes/feed/v1.0/summary/4.5_day.geojson', '', ''))
    eq_data = requests.get(eq_url, headers=HEADERS, timeout=12).json()
    for f in eq_data["features"]:
        lon, lat, depth = get_coords(f["geometry"]["coordinates"])
        mag, place = f["properties"]["mag"], f["properties"]["place"]
        eq_lons.append(lon); eq_lats.append(lat); eq_sizes.append(mag * 3.2)
        eq_text.append(f"M{mag} - {place} ({depth}km)")
    fig.add_trace(go.Scattergeo(lat=eq_lats, lon=eq_lons, text=eq_text, hoverinfo='text', mode='markers', name='M4.5+ Quakes', marker=dict(size=eq_sizes, color='#ffa500', opacity=0.75, line=dict(width=1, color='#ffffff'))))
    for f in eq_data["features"][:5]:
        eq_list.append(f"<div style='margin:6px 0; font-size:12px;'>🟠 <b>M{f['properties']['mag']}</b> - {f['properties']['place']}</div>")
except Exception:
    eq_list.append("<div style='color:#8b949e; font-size:12px;'>Seismic feed unavailable.</div>")
eq_html = "".join(eq_list)

nasa_list, nasa_lats, nasa_lons, nasa_text = [], [], [], []
try:
    eonet_url = urlunsplit(('https', '.'.join(['eonet', 'gsfc', 'nasa', 'gov']), '/api/v3/events', 'status=open&limit=15', ''))
    events = requests.get(eonet_url, headers=HEADERS, timeout=10).json().get("events", [])
    for ev in events:
        title = ev.get("title", "Natural Event")
        cats = ev.get("categories", [])
        cat_name = cats[0].get("title", "Hazard") if cats else "Hazard"
        geom = ev.get("geometry", [])
        if geom:
            coords = geom[-1].get("coordinates", [])
            if isinstance(coords, list) and len(coords) >= 2 and isinstance(coords[0], (int, float)):
                nasa_lons.append(coords[0]); nasa_lats.append(coords[1])
                nasa_text.append(f"[{cat_name}] {title}")
        if len(nasa_list) < 5:
            nasa_list.append(f"<div style='margin:5px 0; font-size:12px;'>🔥 <b>[{cat_name}]</b> {title}</div>")
    if nasa_lats:
        fig.add_trace(go.Scattergeo(lat=nasa_lats, lon=nasa_lons, text=nasa_text, hoverinfo='text', mode='markers', name='NASA Satellite Events', marker=dict(size=7, color='#ff2a6d', symbol='diamond')))
except Exception:
    nasa_list.append("<div style='color:#8b949e; font-size:12px;'>NASA EONET feed temporarily unavailable.</div>")
nasa_html = "".join(nasa_list) or "<div style='color:#8b949e; font-size:12px;'>No active NASA EONET events.</div>"

ioda_list = []
try:
    ioda_url = urlunsplit(('https', '.'.join(['api', 'ioda', 'inetintel', 'cc', 'gatech', 'edu']), '/v2/outages/alerts', 'limit=5', ''))
    ioda_res = requests.get(ioda_url, headers=HEADERS, timeout=10).json()
    alerts_data = ioda_res.get("data", []) if isinstance(ioda_res, dict) else []
    for al in alerts_data[:5]:
        entity = al.get("entity", {})
        ename = entity.get("name", "Unknown Network/Region")
        etype = entity.get("type", "region")
        level = al.get("level", "warning").upper()
        ioda_list.append(f"<div style='margin:5px 0; font-size:12px;'>🌐 <b style='color:#ffa500;'>[{level}]</b> {ename} ({etype})</div>")
except Exception:
    pass
ioda_html = "".join(ioda_list) or "<div style='color:#00ff41; font-size:12px;'>✅ No major global BGP/internet outages flagged.</div>"

faa_list = []
try:
    faa_url = urlunsplit(('https', '.'.join(['nasstatus', 'faa', 'gov']), '/api/airport-status-information', '', ''))
    faa_res = requests.get(faa_url, headers=HEADERS, timeout=10)
    faa_soup = BeautifulSoup(faa_res.content, features='xml')
    delays = faa_soup.find_all('Delay')
    if delays:
        for d in delays[:4]:
            arpt = d.find('ARPT').get_text(strip=True) if d.find('ARPT') else "US Airport"
            reason = d.find('Reason').get_text(strip=True) if d.find('Reason') else "Airspace Delay"
            faa_list.append(f"<div style='margin:5px 0; font-size:12px; color:#ffa500;'>✈️ <b>{arpt}:</b> {reason}</div>")
    else:
        faa_list.append("<div style='margin:5px 0; font-size:12px; color:#00ff41;'>✅ FAA NAS: No major US ground stops or delays.</div>")
except Exception:
    faa_list.append("<div style='margin:5px 0; font-size:12px; color:#8b949e;'>FAA NAS feed temporarily unavailable.</div>")
faa_html = "".join(faa_list)

local_list = []
noaa_headers = {'User-Agent': '(SituationRoomOSINT, contact@example.com)'}
try:
    noaa_url = urlunsplit(('https', '.'.join(['api', 'weather', 'gov']), '/alerts/active', 'point=33.1959,-117.3795', ''))
    alerts = requests.get(noaa_url, headers=noaa_headers, timeout=10).json().get("features", [])
    if alerts:
        for a in alerts[:3]:
            p = a.get("properties", {})
            local_list.append(f"<div style='margin:5px 0; font-size:12px; color:#ff4b4b;'>⚠️ <b>[{p.get('severity','Alert').upper()}] {p.get('event','Advisory')}</b></div>")
    else:
        local_list.append("<div style='margin:5px 0; font-size:12px; color:#00ff41;'>✅ NOAA Oceanside: No active weather advisories.</div>")
except Exception:
    local_list.append("<div style='margin:5px 0; font-size:12px; color:#8b949e;'>NOAA feed unavailable.</div>")

try:
    buoy_url = urlunsplit(('https', '.'.join(['www', 'ndbc', 'noaa', 'gov']), '/data/realtime2/46224.txt', '', ''))
    buoy_lines = requests.get(buoy_url, headers=HEADERS, timeout=8).text.splitlines()
    if len(buoy_lines) >= 3:
        parts = buoy_lines[2].split()
        wvht_m = float(parts[8]) if parts[8] != 'MM' else None
        dpd_s = parts[9] if parts[9] != 'MM' else 'N/A'
        if wvht_m is not None:
            wvht_ft = wvht_m * 3.28084
            local_list.append(f"<div style='margin:5px 0; font-size:12px;'>🌊 <b>Oceanside Buoy 46224:</b> Swell {wvht_ft:.1f} ft @ {dpd_s}s</div>")
except Exception:
    pass

try:
    leq_url = urlunsplit(('https', '.'.join(['earthquake', 'usgs', 'gov']), '/fdsnws/event/1/query', 'format=geojson&latitude=33.1959&longitude=-117.3795&maxradiuskm=240&minmagnitude=2.5&limit=3', ''))
    leqs = requests.get(leq_url, headers=HEADERS, timeout=10).json().get("features", [])
    for lf in leqs:
        local_list.append(f"<div style='margin:5px 0; font-size:12px;'>📍 <b>M{lf['properties']['mag']}</b> - {lf['properties']['place']}</div>")
    if not leqs:
        local_list.append("<div style='margin:5px 0; font-size:12px; color:#8b949e;'>No M2.5+ tremors within 150 mi recently.</div>")
except Exception:
    pass
local_html = "".join(local_list)

fig.update_geos(projection_type="natural earth", showcoastlines=True, coastlinecolor="#30363d", showland=True, landcolor="#161b22", showocean=True, oceancolor="#090d16", showcountries=True, countrycolor="#30363d", lataxis_range=(20, 65), lonaxis_range=(-20, 80))
fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=360, paper_bgcolor="#0d1117", plot_bgcolor="#0d1117", legend=dict(orientation="h", yanchor="bottom", y=0.01, xanchor="left", x=0.01, font=dict(color="#e6edf3", size=10), bgcolor="rgba(13,17,23,0.8)"))
map_html = fig.to_html(include_plotlyjs='cdn', full_html=False)

now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

full_page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Global Situation Room</title>
<style>
  body {{ background-color: #090d16; color: #e6edf3; font-family: 'Courier New', monospace; margin: 0; padding: 12px; }}
  .container {{ max-width: 1240px; margin: 0 auto; background: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 16px; }}
  .header {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; border-bottom: 1px solid #30363d; padding-bottom: 12px; margin-bottom: 16px; gap: 8px; }}
  .ticker-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-bottom: 18px; }}
  .main-grid {{ display: grid; grid-template-columns: 2fr 1fr; gap: 18px; }}
  .panel {{ background: #161b22; padding: 14px; border-radius: 6px; border: 1px solid #30363d; margin-bottom: 16px; }}
  @media (max-width: 820px) {{ .main-grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h2 style="color:#00ff41; margin:0; font-size:17px;">🌐 GLOBAL SITUATION ROOM // FULL OSINT CLOUD</h2>
    <span style="color:#00ff41; font-size:12px;">UPDATED: {now_str} (+{len(new_items)} NEW)</span>
  </div>
  <div class="ticker-grid">{''.join(market_list)}{kp_card}</div>
  <div class="panel">
    <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; margin-bottom:10px; gap:6px;">
      <h3 style="color:#00ff41; margin:0; font-size:14px;">🗺️ LIVE THEATER RADAR, SEISMIC & SATELLITE MAP</h3>
      <span style="color:#8b949e; font-size:11px;">{air_status} | 🟠 Quakes | ♦️ NASA</span>
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
        <h3 style="color:#00ff41; margin-top:0; font-size:14px;">🛰️ NASA SATELLITE & GLOBAL INFRASTRUCTURE</h3>
        {nasa_html}
        <hr style="border:0; border-top:1px solid #30363d; margin:10px 0;">
        {ioda_html}
        <hr style="border:0; border-top:1px solid #30363d; margin:10px 0;">
        {faa_html}
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
</body>
</html>"""

with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
    f.write(full_page)

print(f"Generated {OUTPUT_HTML} with {len(new_items)} new items.")
