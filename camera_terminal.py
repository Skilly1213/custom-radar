#!/usr/bin/env python3
"""
=============================================================
  NWS RADAR — TRAFFIC CAMERA FEED TERMINAL
  Python backend for traffic camera stream health monitoring
=============================================================
  Mirrors the in-browser camera terminal (cam-term-lines) as a
  standalone CLI tool.  Checks every HLS stream endpoint, logs
  status, and writes a JSON status file that index.html can poll.

  Usage:
      python camera_terminal.py                  # run once & loop
      python camera_terminal.py --once           # single scan, exit
      python camera_terminal.py --interval 60    # custom interval (sec)
      python camera_terminal.py --state NY       # filter by state
      python camera_terminal.py --open           # open browser on start
      python camera_terminal.py --log FILE.log   # append to logfile

  Output:
      camera_status.json  — machine-readable status (polled by HTML)
      camera_terminal.log — human-readable timestamped log
=============================================================
"""

import argparse
import asyncio
import datetime
import json
import os
import sys
import time
import urllib.request
import urllib.error
import webbrowser
from pathlib import Path

# ── ANSI colour codes (Windows 10+ supports these) ───────────────────────────
RESET  = "\033[0m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
DIM    = "\033[2m"
BOLD   = "\033[1m"
WHITE  = "\033[97m"

# ── Camera definitions (mirrored from index.html TRAFFIC_CAMERAS) ─────────────
TRAFFIC_CAMERAS = [
    # ── New York DOT ──────────────────────────────────────────────────────────
    {"id": "ny-r1-036",  "name": "I-87 Northway @ Exit 15 (Saratoga)",        "city": "Saratoga Springs", "state": "NY", "lat": 43.083, "lng": -73.774, "stream": "https://s51.nysdot.skyvdn.com:443/rtplive/R1_036/playlist.m3u8",         "provider": "NYSDOT"},
    {"id": "ny-r1-023",  "name": "I-87 Northway @ Exit 13N (Saratoga)",       "city": "Saratoga Springs", "state": "NY", "lat": 43.003, "lng": -73.785, "stream": "https://s53.nysdot.skyvdn.com:443/rtplive/R1_023/playlist.m3u8",         "provider": "NYSDOT"},
    {"id": "ny-r1-2107", "name": "I-87 Northway @ Exit 14 (Saratoga)",        "city": "Saratoga Springs", "state": "NY", "lat": 43.055, "lng": -73.804, "stream": "https://s9.nysdot.skyvdn.com:443/rtplive/R1_2107/playlist.m3u8",        "provider": "NYSDOT"},
    {"id": "ny-ta-100",  "name": "I-87 Thruway @ Tarrytown (Mario Cuomo Br)", "city": "Tarrytown",        "state": "NY", "lat": 41.073, "lng": -73.918, "stream": "https://s58.nysdot.skyvdn.com:443/rtplive/TA_100/playlist.m3u8",        "provider": "NYSDOT Thruway"},
    {"id": "ny-ta-101",  "name": "I-87 Thruway @ Tarrytown South",            "city": "Tarrytown",        "state": "NY", "lat": 41.065, "lng": -73.915, "stream": "https://s58.nysdot.skyvdn.com:443/rtplive/TA_101/playlist.m3u8",        "provider": "NYSDOT Thruway"},
    {"id": "ny-ta-102",  "name": "I-87 Thruway @ Yonkers — Ridge Hill",       "city": "Yonkers",          "state": "NY", "lat": 40.958, "lng": -73.875, "stream": "https://s58.nysdot.skyvdn.com:443/rtplive/TA_102/playlist.m3u8",        "provider": "NYSDOT Thruway"},
    {"id": "ny-ta-103",  "name": "I-87 Thruway @ Suffern",                    "city": "Suffern",          "state": "NY", "lat": 41.116, "lng": -74.149, "stream": "https://s58.nysdot.skyvdn.com:443/rtplive/TA_103/playlist.m3u8",        "provider": "NYSDOT Thruway"},
    {"id": "ny-ta-104",  "name": "I-87 Thruway @ Harriman",                   "city": "Harriman",         "state": "NY", "lat": 41.306, "lng": -74.147, "stream": "https://s58.nysdot.skyvdn.com:443/rtplive/TA_104/playlist.m3u8",        "provider": "NYSDOT Thruway"},
    {"id": "ny-ta-105",  "name": "I-87 Thruway @ Newburgh",                   "city": "Newburgh",         "state": "NY", "lat": 41.500, "lng": -74.010, "stream": "https://s58.nysdot.skyvdn.com:443/rtplive/TA_105/playlist.m3u8",        "provider": "NYSDOT Thruway"},
    {"id": "ny-ta-106",  "name": "I-87 Thruway @ Kingston",                   "city": "Kingston",         "state": "NY", "lat": 41.930, "lng": -73.988, "stream": "https://s58.nysdot.skyvdn.com:443/rtplive/TA_106/playlist.m3u8",        "provider": "NYSDOT Thruway"},
    {"id": "ny-ta-107",  "name": "I-87 Thruway @ Catskill",                   "city": "Catskill",         "state": "NY", "lat": 42.211, "lng": -73.869, "stream": "https://s58.nysdot.skyvdn.com:443/rtplive/TA_107/playlist.m3u8",        "provider": "NYSDOT Thruway"},
    {"id": "ny-ta-108",  "name": "I-87 Thruway @ Coxsackie",                  "city": "Coxsackie",        "state": "NY", "lat": 42.365, "lng": -73.823, "stream": "https://s58.nysdot.skyvdn.com:443/rtplive/TA_108/playlist.m3u8",        "provider": "NYSDOT Thruway"},
    {"id": "ny-ta-109",  "name": "I-87 Thruway @ Albany Interchange",         "city": "Albany",           "state": "NY", "lat": 42.691, "lng": -73.813, "stream": "https://s58.nysdot.skyvdn.com:443/rtplive/TA_109/playlist.m3u8",        "provider": "NYSDOT Thruway"},
    {"id": "ny-ta-110",  "name": "I-90 Thruway @ Schenectady",                "city": "Schenectady",      "state": "NY", "lat": 42.793, "lng": -73.975, "stream": "https://s58.nysdot.skyvdn.com:443/rtplive/TA_110/playlist.m3u8",        "provider": "NYSDOT Thruway"},
    {"id": "ny-ta-111",  "name": "I-90 Thruway @ Amsterdam",                  "city": "Amsterdam",        "state": "NY", "lat": 42.936, "lng": -74.183, "stream": "https://s58.nysdot.skyvdn.com:443/rtplive/TA_111/playlist.m3u8",        "provider": "NYSDOT Thruway"},
    {"id": "ny-ta-112",  "name": "I-90 Thruway @ Utica",                      "city": "Utica",            "state": "NY", "lat": 43.094, "lng": -75.233, "stream": "https://s58.nysdot.skyvdn.com:443/rtplive/TA_112/playlist.m3u8",        "provider": "NYSDOT Thruway"},
    {"id": "ny-ta-113",  "name": "I-90 Thruway @ Syracuse",                   "city": "Syracuse",         "state": "NY", "lat": 43.048, "lng": -76.147, "stream": "https://s58.nysdot.skyvdn.com:443/rtplive/TA_113/playlist.m3u8",        "provider": "NYSDOT Thruway"},
    {"id": "ny-ta-114",  "name": "I-90 Thruway @ Rochester",                  "city": "Rochester",        "state": "NY", "lat": 43.156, "lng": -77.615, "stream": "https://s58.nysdot.skyvdn.com:443/rtplive/TA_114/playlist.m3u8",        "provider": "NYSDOT Thruway"},
    {"id": "ny-ta-115",  "name": "I-90 Thruway @ Buffalo",                    "city": "Buffalo",          "state": "NY", "lat": 42.884, "lng": -78.878, "stream": "https://s58.nysdot.skyvdn.com:443/rtplive/TA_115/playlist.m3u8",        "provider": "NYSDOT Thruway"},
    {"id": "ny-ta-116",  "name": "I-90 Thruway @ Niagara Falls Exit",         "city": "Niagara Falls",    "state": "NY", "lat": 43.091, "lng": -78.950, "stream": "https://s58.nysdot.skyvdn.com:443/rtplive/TA_116/playlist.m3u8",        "provider": "NYSDOT Thruway"},
    # ── Virginia DOT (Hampton Roads) ─────────────────────────────────────────
    {"id": "va-mmbt-1",   "name": "I-664 MMBT NB Tunnel Exit",            "city": "Hampton",    "state": "VA", "lat": 36.959, "lng": -76.410, "stream": "https://s16.us-east-1.skyvdn.com:443/rtplive/MMBT1113/playlist.m3u8",            "provider": "VDOT Hampton Roads"},
    {"id": "va-hr-761",   "name": "I-64 Hampton Roads @ MM 7.6",          "city": "Hampton",    "state": "VA", "lat": 37.025, "lng": -76.393, "stream": "https://s15.us-east-1.skyvdn.com:443/rtplive/HamptonRoads761/playlist.m3u8",      "provider": "VDOT Hampton Roads"},
    {"id": "va-hr-wf104", "name": "VA-164 WB Cedar Lane",                 "city": "Portsmouth", "state": "VA", "lat": 36.833, "lng": -76.395, "stream": "https://s17.us-east-1.skyvdn.com:443/rtplive/HamptonRoadsWF104/playlist.m3u8",   "provider": "VDOT Hampton Roads"},
    {"id": "va-hamp-3",   "name": "Armistead Ave & LaSalle Ave",          "city": "Hampton",    "state": "VA", "lat": 37.021, "lng": -76.343, "stream": "https://s11.us-east-1.skyvdn.com:443/rtplive/CityofHampton3/playlist.m3u8",       "provider": "City of Hampton"},
    {"id": "va-hamp-6",   "name": "Magruder Blvd & HRCP",                 "city": "Hampton",    "state": "VA", "lat": 37.062, "lng": -76.374, "stream": "https://s11.us-east-1.skyvdn.com:443/rtplive/CityofHampton6/playlist.m3u8",       "provider": "City of Hampton"},
    {"id": "va-hamp-7",   "name": "Mercury Blvd & Armistead Ave",         "city": "Hampton",    "state": "VA", "lat": 37.028, "lng": -76.353, "stream": "https://s11.us-east-1.skyvdn.com:443/rtplive/CityofHampton7/playlist.m3u8",       "provider": "City of Hampton"},
    {"id": "va-hamp-12",  "name": "Coliseum Dr & Convention Center Blvd", "city": "Hampton",    "state": "VA", "lat": 37.046, "lng": -76.341, "stream": "https://s11.us-east-1.skyvdn.com:443/rtplive/CityofHampton12/playlist.m3u8",      "provider": "City of Hampton"},
    {"id": "va-hamp-21",  "name": "Coliseum Dr & Cunningham Dr",          "city": "Hampton",    "state": "VA", "lat": 37.048, "lng": -76.352, "stream": "https://s11.us-east-1.skyvdn.com:443/rtplive/CityofHampton21/playlist.m3u8",      "provider": "City of Hampton"},
    # ── Iowa DOT ─────────────────────────────────────────────────────────────
    {"id": "ia-qctv33",  "name": "I-80 @ Quad Cities Area",        "city": "Davenport",   "state": "IA", "lat": 41.572, "lng": -90.580, "stream": "https://iowadotsfs2.us-east-1.skyvdn.com:443/rtplive/qctv33qlb/playlist.m3u8",   "provider": "Iowa DOT"},
    {"id": "ia-qctv34",  "name": "I-80 @ Quad Cities West",        "city": "Davenport",   "state": "IA", "lat": 41.570, "lng": -90.598, "stream": "https://iowadotsfs2.us-east-1.skyvdn.com:443/rtplive/qctv34qlb/playlist.m3u8",   "provider": "Iowa DOT"},
    {"id": "ia-dsmtv1",  "name": "I-35/80 @ Des Moines",           "city": "Des Moines",  "state": "IA", "lat": 41.590, "lng": -93.620, "stream": "https://iowadotsfs2.us-east-1.skyvdn.com:443/rtplive/dsmtv01/playlist.m3u8",     "provider": "Iowa DOT"},
    {"id": "ia-dsmtv2",  "name": "I-235 @ Des Moines — Downtown",  "city": "Des Moines",  "state": "IA", "lat": 41.594, "lng": -93.633, "stream": "https://iowadotsfs2.us-east-1.skyvdn.com:443/rtplive/dsmtv02/playlist.m3u8",     "provider": "Iowa DOT"},
    {"id": "ia-dsmtv3",  "name": "I-80 @ Des Moines East",         "city": "Des Moines",  "state": "IA", "lat": 41.580, "lng": -93.570, "stream": "https://iowadotsfs2.us-east-1.skyvdn.com:443/rtplive/dsmtv03/playlist.m3u8",     "provider": "Iowa DOT"},
    {"id": "ia-cedarv1", "name": "I-380 @ Cedar Rapids",           "city": "Cedar Rapids", "state": "IA", "lat": 41.977, "lng": -91.668, "stream": "https://iowadotsfs2.us-east-1.skyvdn.com:443/rtplive/cedartv01/playlist.m3u8",  "provider": "Iowa DOT"},
    {"id": "ia-cedarv2", "name": "US-30 @ Cedar Rapids West",      "city": "Cedar Rapids", "state": "IA", "lat": 41.969, "lng": -91.710, "stream": "https://iowadotsfs2.us-east-1.skyvdn.com:443/rtplive/cedartv02/playlist.m3u8",  "provider": "Iowa DOT"},
]

STATUS_FILE = Path(__file__).parent / "camera_status.json"
LOG_FILE    = Path(__file__).parent / "camera_terminal.log"

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def ts() -> str:
    """HH:MM:SS timestamp, same format as browser terminal."""
    return datetime.datetime.now().strftime("%H:%M:%S")

def now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

_log_fh = None  # file handle opened once

def tlog(msg: str, level: str = "info", log_file: Path | None = None) -> None:
    """Print a coloured terminal line and optionally write to logfile."""
    global _log_fh
    colour = {
        "sys":   DIM + CYAN,
        "info":  GREEN,
        "new":   BOLD + GREEN,
        "warn":  YELLOW,
        "err":   RED,
        "dim":   DIM,
        "scan":  CYAN,
    }.get(level, WHITE)

    line = f"[{ts()}] {msg}"
    print(f"{colour}{line}{RESET}")

    # Write plain text to log
    target = log_file or _log_fh
    if target:
        try:
            if hasattr(target, "write"):
                target.write(line + "\n")
                target.flush()
            else:
                with open(target, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
        except Exception:
            pass

def divider(log_file=None):
    tlog("─" * 46, "dim", log_file)

# ─────────────────────────────────────────────────────────────────────────────
# Stream health check
# ─────────────────────────────────────────────────────────────────────────────

def check_stream(cam: dict, timeout: int = 5) -> dict:
    """
    HEAD-request the HLS playlist URL.
    Returns a result dict: {id, status, http_code, latency_ms, error}.
    """
    url = cam["stream"]
    t0  = time.monotonic()
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "NWSRadar-CamTerminal/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code    = resp.status
            latency = int((time.monotonic() - t0) * 1000)
            status  = "live" if code == 200 else "offline"
            return {"id": cam["id"], "status": status, "http_code": code,
                    "latency_ms": latency, "error": None}
    except urllib.error.HTTPError as e:
        latency = int((time.monotonic() - t0) * 1000)
        return {"id": cam["id"], "status": "offline", "http_code": e.code,
                "latency_ms": latency, "error": str(e)}
    except Exception as e:
        latency = int((time.monotonic() - t0) * 1000)
        return {"id": cam["id"], "status": "offline", "http_code": None,
                "latency_ms": latency, "error": str(e)[:80]}

# ─────────────────────────────────────────────────────────────────────────────
# Single scan pass
# ─────────────────────────────────────────────────────────────────────────────

def run_scan(cameras: list[dict], log_file=None) -> dict:
    """Check all cameras, log results, write status JSON. Returns summary."""
    divider(log_file)
    tlog(f"SCAN: Starting check of {len(cameras)} HLS streams...", "sys", log_file)
    divider(log_file)

    results  = []
    live_ids = []
    dead_ids = []

    for cam in cameras:
        result = check_stream(cam)
        results.append({**cam, **result})

        label = f"{cam['id']:20s}  {cam['name'][:38]:38s}"
        if result["status"] == "live":
            live_ids.append(cam["id"])
            tlog(f"LIVE ✓  {label}  ({result['latency_ms']}ms)", "new", log_file)
        else:
            dead_ids.append(cam["id"])
            err = result.get("error") or f"HTTP {result.get('http_code','?')}"
            tlog(f"OFFLINE {label}  [{err}]", "err", log_file)

    divider(log_file)
    live_pct = int(len(live_ids) / max(len(cameras), 1) * 100)
    tlog(f"SUMMARY: {len(live_ids)}/{len(cameras)} streams LIVE ({live_pct}%)", "sys", log_file)
    if dead_ids:
        tlog(f"OFFLINE: {', '.join(dead_ids)}", "warn", log_file)
    divider(log_file)

    # Write JSON status file (can be polled by index.html via fetch)
    status_doc = {
        "updated":    now_iso(),
        "total":      len(cameras),
        "live":       len(live_ids),
        "offline":    len(dead_ids),
        "live_pct":   live_pct,
        "cameras":    results,
    }
    try:
        STATUS_FILE.write_text(json.dumps(status_doc, indent=2), encoding="utf-8")
        tlog(f"SYS: Status written → {STATUS_FILE.name}", "sys", log_file)
    except Exception as e:
        tlog(f"SYS: Failed to write status file: {e}", "warn", log_file)

    return status_doc

# ─────────────────────────────────────────────────────────────────────────────
# Banner
# ─────────────────────────────────────────────────────────────────────────────

def print_banner(cameras: list[dict], args: argparse.Namespace) -> None:
    states = sorted({c["state"] for c in cameras})
    providers = sorted({c["provider"] for c in cameras})
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════╗
║    ⬡  NWS RADAR — TRAFFIC CAMERA FEED TERMINAL       ║
╚══════════════════════════════════════════════════════╝{RESET}
  {DIM}Cameras : {WHITE}{len(cameras)}{RESET}
  {DIM}States  : {WHITE}{', '.join(states)}{RESET}
  {DIM}Interval: {WHITE}{args.interval}s{RESET}
  {DIM}Log     : {WHITE}{args.log or 'stdout only'}{RESET}
  {DIM}Status  : {WHITE}{STATUS_FILE}{RESET}
  {DIM}Mode    : {WHITE}{'Single scan' if args.once else 'Continuous loop'}{RESET}
  {DIM}Providers:{RESET}
""")
    for p in providers:
        count = sum(1 for c in cameras if c["provider"] == p)
        print(f"    {DIM}·{RESET} {p} ({count} stream{'s' if count!=1 else ''})")
    print()

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="NWS Radar — Traffic Camera Feed Terminal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--once",     action="store_true",    help="Run one scan then exit")
    p.add_argument("--interval", type=int, default=30,   help="Scan interval in seconds (default: 30)")
    p.add_argument("--state",    type=str, default=None, help="Filter to one state code (e.g. NY, VA, IA)")
    p.add_argument("--open",     action="store_true",    help="Open index.html in browser on start")
    p.add_argument("--log",      type=str, default=None, help="Path to log file (appended)")
    p.add_argument("--timeout",  type=int, default=5,    help="HTTP timeout per stream in seconds (default: 5)")
    return p.parse_args()


def main() -> None:
    global _log_fh
    args    = parse_args()
    cameras = TRAFFIC_CAMERAS

    if args.state:
        cameras = [c for c in cameras if c["state"].upper() == args.state.upper()]
        if not cameras:
            print(f"{RED}No cameras found for state '{args.state}'. "
                  f"Available: {sorted({c['state'] for c in TRAFFIC_CAMERAS})}{RESET}")
            sys.exit(1)

    if args.log:
        _log_fh = open(args.log, "a", encoding="utf-8")  # noqa: WPS515

    # Enable ANSI on Windows terminal
    if sys.platform == "win32":
        os.system("")

    print_banner(cameras, args)

    if args.open:
        html_path = Path(__file__).parent / "index.html"
        if html_path.exists():
            webbrowser.open(html_path.as_uri())
            tlog(f"SYS: Opened {html_path.name} in browser.", "sys")
        else:
            tlog("SYS: index.html not found in same directory.", "warn")

    tlog("SYS: Camera terminal initialised.", "sys")
    tlog(f"SYS: {len(cameras)} HLS streams ready ({', '.join(sorted({c['state'] for c in cameras]))} DOT).", "sys")

    scan_count = 0
    try:
        while True:
            scan_count += 1
            tlog(f"SYS: === Scan #{scan_count} @ {now_iso()} ===", "scan")
            run_scan(cameras, _log_fh)

            if args.once:
                break

            tlog(f"SYS: Next scan in {args.interval}s. Press Ctrl+C to quit.", "sys")
            time.sleep(args.interval)

    except KeyboardInterrupt:
        tlog("\nSYS: Camera terminal stopped by user.", "sys")
    finally:
        if _log_fh:
            _log_fh.close()


if __name__ == "__main__":
    main()
