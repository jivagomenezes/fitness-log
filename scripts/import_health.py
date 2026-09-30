#!/usr/bin/env python3
"""Import Apple Health samples sent by the iPhone shortcut (raw/health/*.txt) into data/daily_health.csv.

Each shortcut run writes raw/health/YYYY-MM-DD_HHMM.txt, one sample per line:
    type;start;end;value[;unit]

    hrv;2026-09-30T03:12:45+01:00;2026-09-30T03:13:45+01:00;48
    rhr;2026-09-30T00:00:00+01:00;2026-09-30T08:00:00+01:00;52
    sleep;2026-09-29T23:40:00+01:00;2026-09-30T00:55:00+01:00;Core
    steps;2026-09-30T00:00:00+01:00;2026-10-01T00:00:00+01:00;11234
    active_kcal;2026-09-30T00:00:00+01:00;2026-10-01T00:00:00+01:00;612;kcal
    basal_kcal;2026-09-30T00:00:00+01:00;2026-10-01T00:00:00+01:00;1788;kcal

types (Portuguese aliases accepted: fcr, sono, passos, kcal_ativas, kcal_repouso):
  hrv          HRV samples (ms, Apple Watch SDNN) → NIGHT mean (18:00 the day before to 14:00)
  rhr          resting heart rate (bpm) → mean of the day's samples (as the Health app shows it)
  sleep        sleep stages (Core/Deep/REM/Awake/In Bed or Essencial/Profundo/REM/Sem Dormir/Na Cama)
               → hours asleep in the night ending that day (union of intervals, overlaps counted once)
  vo2max       Apple Watch VO2 max estimate ("Cardio Fitness", mL/kg/min) → latest sample of the day
               (aliases: vo2, cardio_fitness, preparo_cardiovascular)
  steps, active_kcal, basal_kcal
               daily totals (the shortcut asks Health to "group by day"); the HIGHEST total received for
               a day wins, since totals only grow — the next morning's run closes the previous day.
               Energy in kJ is converted to kcal.

Samples from all files are merged (repeated lines count once), so the shortcut can run any number of times.
Upserts daily_health.csv without touching the Bevel scores.

Usage:  python3 scripts/import_health.py
"""
import csv
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Lisbon")
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw" / "health"
CSV = ROOT / "data" / "daily_health.csv"

TYPE_ALIASES = {"hrv": "hrv", "rhr": "rhr", "fcr": "rhr", "sleep": "sleep", "sono": "sleep",
                "steps": "steps", "passos": "steps", "active_kcal": "active_kcal", "kcal_ativas": "active_kcal",
                "basal_kcal": "basal_kcal", "kcal_repouso": "basal_kcal",
                "vo2max": "vo2max", "vo2_max": "vo2max", "vo2": "vo2max", "cardio_fitness": "vo2max",
                "preparo_cardiovascular": "vo2max"}
STAGES = {
    "deep": "deep", "asleepdeep": "deep", "profundo": "deep",
    "rem": "rem", "asleeprem": "rem",
    "core": "light", "asleepcore": "light", "light": "light", "principal": "light", "leve": "light",
    "essencial": "light",
    "asleep": "light", "asleepunspecified": "light", "unspecified": "light",
    "dormindo": "light", "a dormir": "light", "sono": "light", "não especificado": "light",
    "awake": None, "acordado": None, "desperto": None, "sem dormir": None,
    "in bed": None, "inbed": None, "na cama": None, "em cama": None,
}
DAILY_TOTALS = ("steps", "active_kcal", "basal_kcal")
NEW_COLUMNS = ["deep_sleep_h", "rem_sleep_h", "steps", "active_kcal", "basal_kcal", "vo2max"]
FORMATS = {"hrv_ms": "{:.0f}", "resting_hr": "{:.0f}", "sleep_h": "{:.2f}", "deep_sleep_h": "{:.2f}",
           "rem_sleep_h": "{:.2f}", "steps": "{:.0f}", "active_kcal": "{:.0f}", "basal_kcal": "{:.0f}",
           "vo2max": "{:.1f}"}
warnings = []


def num(s):
    m = re.search(r"-?\d+(?:[.,]\d+)?", s or "")
    return float(m.group().replace(",", ".")) if m else None


def when(s):
    s = s.strip()
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo is None else d.astimezone(TZ).replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in ("%d/%m/%Y, %H:%M", "%d/%m/%Y %H:%M", "%d/%m/%Y, %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"unrecognized date: {s!r}")


def hours(intervals):
    """Hours covered by the union of intervals (overlaps counted once)."""
    total, cur_start, cur_end = 0.0, None, None
    for start, end in sorted(intervals):
        if cur_end is None or start > cur_end:
            if cur_end is not None:
                total += (cur_end - cur_start).total_seconds()
            cur_start, cur_end = start, end
        else:
            cur_end = max(cur_end, end)
    if cur_end is not None:
        total += (cur_end - cur_start).total_seconds()
    return total / 3600


def read_samples():
    seen, samples, file_dates, coverage = set(), [], set(), []
    for f in sorted(RAW.glob("*.txt")):
        m = re.match(r"(\d{4}-\d{2}-\d{2})", f.name)
        if m:
            file_dates.add(datetime.strptime(m.group(1), "%Y-%m-%d").date())
        first = len(samples)
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line or line.lower().startswith(("type;", "tipo;")) or line in seen:
                continue
            seen.add(line)
            p = [x.strip() for x in line.split(";")]
            if len(p) < 4:
                warnings.append(f"{f.name}:{n}: incomplete line")
                continue
            kind = TYPE_ALIASES.get(p[0].lower())
            if kind is None:
                warnings.append(f"{f.name}:{n}: unknown type '{p[0]}'")
                continue
            try:
                samples.append({"type": kind, "start": when(p[1]), "end": when(p[2]), "value": p[3],
                                "unit": p[4].lower() if len(p) > 4 else "", "ref": f"{f.name}:{n}"})
            except ValueError as e:
                warnings.append(f"{f.name}:{n}: {e}")
        mine = [s["start"] for s in samples[first:]]
        if mine:
            coverage.append(min(mine))  # the shortcut asks for "the last N days": this file starts here
    return samples, file_dates, coverage


def compute(samples, file_dates, coverage):
    per_day = defaultdict(dict)

    # daily totals: highest value received for each day
    for s in samples:
        if s["type"] not in DAILY_TOTALS or num(s["value"]) is None:
            continue
        v = num(s["value"])
        if s["type"].endswith("kcal") and (s["unit"] in ("kj", "kilojoule", "quilojoule") or "kj" in s["value"].lower()):
            v /= 4.184
        day = s["start"].date()
        per_day[day][s["type"]] = max(per_day[day].get(s["type"], 0), v)

    # night / daily metrics
    point_days = {s["start"].date() for s in samples if s["type"] in ("rhr", "vo2max")}
    for day in set(file_dates) | set(per_day) | point_days:
        night_start = datetime.combine(day - timedelta(days=1), time(18, 0))
        night_end = datetime.combine(day, time(14, 0))
        # a night is only complete if some file covers it from 18:00 the day before; otherwise the
        # start of the night may have been cut off by the shortcut's date window — skip it
        night_ok = any(c <= night_start for c in coverage)
        if not night_ok and any(s["type"] in ("hrv", "sleep") and night_start <= s["end"] <= night_end for s in samples):
            warnings.append(f"{day}: night skipped (not fully covered by any file; start may be cut off)")
        hrv = [num(s["value"]) for s in samples
               if s["type"] == "hrv" and night_start <= s["start"] <= night_end and num(s["value"]) is not None]
        rhr = [(s["start"], num(s["value"])) for s in samples
               if s["type"] == "rhr" and s["start"].date() == day and num(s["value"]) is not None]
        vo2 = [(s["start"], num(s["value"])) for s in samples
               if s["type"] == "vo2max" and s["start"].date() == day and num(s["value"]) is not None]
        stages = {"light": [], "deep": [], "rem": []}
        for s in samples:
            if s["type"] != "sleep" or not (night_start <= s["end"] <= night_end):
                continue
            key = s["value"].lower().replace("_", " ").strip()
            if key not in STAGES:
                warnings.append(f"{s['ref']}: unknown sleep stage '{s['value']}' (not counted)")
            elif STAGES[key]:
                stages[STAGES[key]].append((s["start"], s["end"]))
        d = per_day[day]
        if hrv and night_ok:
            d["hrv_ms"] = statistics.mean(hrv)
        if rhr:
            d["resting_hr"] = statistics.mean(v for _, v in rhr)
        if vo2:
            d["vo2max"] = max(vo2)[1]
        asleep = stages["light"] + stages["deep"] + stages["rem"]
        if asleep and night_ok:
            d["sleep_h"] = hours(asleep)
            d["deep_sleep_h"] = hours(stages["deep"])
            d["rem_sleep_h"] = hours(stages["rem"])
    return {k: v for k, v in per_day.items() if v}


def main():
    samples, file_dates, coverage = read_samples()
    if not samples:
        print("no samples in raw/health")
        return
    result = compute(samples, file_dates, coverage)

    with CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields, rows = list(reader.fieldnames), list(reader)
    prev = "sleep_h"
    for c in NEW_COLUMNS:
        if c not in fields:
            fields.insert(fields.index(prev) + 1, c)
        prev = c
    by_date = {r["date"]: r for r in rows}

    for day, vals in sorted(result.items()):
        d = day.isoformat()
        row = by_date.get(d)
        if row is None:
            row = {k: "" for k in fields}
            row.update(date=d, source="health")
            rows.append(row)
            by_date[d] = row
        elif "health" not in (row.get("source") or ""):
            row["source"] = f"{row['source']}+health" if row.get("source") else "health"
        for k, v in vals.items():
            row[k] = FORMATS[k].format(v)
        print(f"{d}: " + " · ".join(f"{k} {row[k]}" for k in FORMATS if row.get(k)))

    rows.sort(key=lambda r: r["date"])
    with CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in fields} for r in rows)
    for x in sorted(set(warnings)):
        print(f"warning: {x}", file=sys.stderr)


if __name__ == "__main__":
    main()
