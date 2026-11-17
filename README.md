# 🌐 Global Situation Room // Expanded OSINT Dashboard

A serverless, automated Open-Source Intelligence (OSINT) dashboard hosted on GitHub Pages. Every 30 minutes, a GitHub Actions workflow aggregates global news wires, live aviation transponders, seismic telemetry, space weather, market stress indicators, and local Southern California coastal sensors into a single responsive HTML interface.

**Live Dashboard:** [https://github.io](https://github.io)

---

## 📡 Live Telemetry & Data Sources

* **Intelligence Wire (RSS):** Aggregates and deduplicates headlines from *BBC World*, *Al Jazeera*, *Defense News*, *Bleeping Computer*, and *The Hacker News*, automatically classifying items into regional theaters (`EUROPE`, `MIDEAST`, `INDOPACIFIC`, `CYBER`, `GLOBAL`) and flagging priority keywords.
* **Live Theater Radar & Hazard Map (Plotly):**
  * **Civilian Airspace:** Real-time ADS-B transponder positions via [OpenSky Network](https://opensky-network.org) (Europe/Middle East bounding box).
  * **Military & Recon Radar:** Live military aircraft tracking via [adsb.lol](https://adsb.lol).
  * **Global Seismic:** M4.5+ earthquakes over the past 24 hours via [USGS](https://usgs.gov).
  * **Satellite Hazards:** Active wildfires, severe storms, and natural events via [NASA EONET](https://nasa.gov).
* **Market Stress Bar:** Live pricing and daily percent change for Brent Crude (`BZ=F`), Gold (`GC=F`), Lockheed Martin (`LMT`), and Bitcoin (`BTC-USD`) via Yahoo Finance.
* **Space Weather:** NOAA SWPC Geomagnetic (`G`), Solar Radiation (`R`), and Radio Blackout (`S`) scales.
* **Infrastructure & Airspace:**
  * **Global Internet Outages:** 24-hour connectivity drop alerts via Georgia Tech's [IODA API](https://gatech.edu).
  * **US National Airspace:** Real-time airport delays and ground stops via [FAA NAS Status](https://faa.gov).
* **Local Sector (Oceanside / SoCal):** Active NWS weather advisories, swell height/period from **NOAA Buoy 46224**, and M2.5+ regional earthquakes within 240 km.

---

## ⚙️ Architecture & File Structure

```text
├── .github/workflows/update.yml  # Runs build_dashboard.py every 30 mins & commits output
├── build_dashboard.py            # Core ETL script: fetches APIs/RSS, builds map & HTML
├── index.html                    # Auto-generated static frontend deployed to GitHub Pages
├── intel_log.json                # Rolling state memory (last 500 seen URLs & 45 headlines)
└── requirements.txt              # Python dependencies (requests, beautifulsoup4, lxml, plotly)
```

## 🚀 Local Development & Manual Refresh

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
2. **Generate the dashboard locally:**
   ```bash
   python build_dashboard.py
   ```
3. **Manual Cloud Refresh:** Go to the **Actions** tab in GitHub, select **Update Situation Room**, and click **Run workflow**.
