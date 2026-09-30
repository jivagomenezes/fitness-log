#!/usr/bin/env python3
"""Import a run exported from the Apple Watch as JSON (workout_*.json) into data/runs.csv.

Usage:  python3 scripts/import_watch_run.py FILE.json --type z2 [--rpe 3] [--notes "..."] [--merge-notes "..."]
Never duplicates: if the workout uuid is already in source_id, nothing is written.
If a manual row exists for the same day (source=manual, no source_id), it is completed with the watch data
instead of adding a new row (id, type, location, rpe and notes typed by hand are kept).
"""
import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "runs.csv"
TZ = ZoneInfo("Europe/Lisbon")
RUN_TYPES = {"interval", "tempo", "long", "z2", "recovery", "race", "test"}
KEEP_FROM_MANUAL = ("id", "type", "location", "rpe", "notes")


def val(j, k):
    v = j.get(k)
    return v.get("value") if isinstance(v, dict) else v


def fmt_dur(s):
    s = int(round(s))
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--type", required=True, choices=sorted(RUN_TYPES))
    ap.add_argument("--rpe", default="")
    ap.add_argument("--notes", default="")
    ap.add_argument("--merge-notes", default="", help="text appended to the notes of a completed manual row")
    a = ap.parse_args()

    j = json.loads(Path(a.file).read_text(encoding="utf-8"))
    if (j.get("activity") or {}).get("name") != "Running":
        sys.exit(f"not a run: {(j.get('activity') or {}).get('name')}")
    start = datetime.fromisoformat(j["startDate"].replace("Z", "+00:00")).astimezone(TZ)
    indoor = j.get("location") == "Indoor"
    treadmill = "treadmill" in ((j.get("device") or {}).get("model") or "")
    location = "treadmill" if (indoor or treadmill) else "road"
    zones = j.get("zones") or {}
    z = [str(round(((zones.get(f"zone{i}") or {}).get("time") or {}).get("value", 0))) if zones else ""
         for i in range(1, 6)]
    temp = ""
    if location == "road":
        temp = ((j.get("weather") or {}).get("temperature") or "").replace("°C", "").strip()

    with CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)
    if any(r["source_id"] == j["uuid"] for r in rows):
        print(f"already imported: {j['uuid']}")
        return
    day = start.date().isoformat()
    n = sum(1 for r in rows if r["date"] == day) + 1
    manual = [r for r in rows if r["date"] == day and r["source"] == "manual" and not r["source_id"]]
    row = {
        "id": f"{day}-{n}", "date": day, "start_time": start.strftime("%H:%M"), "type": a.type, "location": location,
        "distance_km": f"{val(j, 'distance'):.2f}", "duration": fmt_dur(val(j, "duration")),
        "hr_avg": val(j, "averageHeartRate") or "", "hr_max": val(j, "maxHeartRate") or "",
        "z1_s": z[0], "z2_s": z[1], "z3_s": z[2], "z4_s": z[3], "z5_s": z[4],
        "cadence_spm": val(j, "cadence") or "", "elevation_m": val(j, "elevationAscended") or "",
        "power_w": val(j, "runningPower") or "", "gct_ms": val(j, "runningGroundContactTime") or "",
        "vertical_osc_cm": val(j, "runningVerticalOscillation") or "", "stride_m": val(j, "runningStrideLength") or "",
        "rpe": a.rpe, "temperature_c": temp, "source": "apple_watch", "source_id": j["uuid"], "notes": a.notes,
    }
    if len(manual) == 1:
        m = manual[0]
        for k, v in row.items():
            if k in KEEP_FROM_MANUAL and m.get(k):
                continue
            m[k] = v
        if a.merge_notes:
            m["notes"] = f"{m['notes']}; {a.merge_notes}" if m["notes"] else a.merge_notes
        with CSV.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print(f"completed manual row {m['id']} ({m['type']}) with watch data: "
              f"{m['distance_km']} km in {m['duration']} (HR {m['hr_avg']}/{m['hr_max']})")
        return
    if len(manual) > 1:
        sys.exit(f"{len(manual)} manual rows on {day}: complete by hand")
    with CSV.open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=fields).writerow({k: row.get(k, "") for k in fields})
    print(f"written: {row['id']} {a.type} {row['distance_km']} km in {row['duration']} "
          f"(HR {row['hr_avg']}/{row['hr_max']}, {location}, start {row['start_time']})")


if __name__ == "__main__":
    main()
