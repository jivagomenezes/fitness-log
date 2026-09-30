#!/usr/bin/env python3
"""Import a Hevy workout as text (the app's "share" text or the Strava activity description)
into data/strength_sets.csv.

Usage:  python3 scripts/import_hevy_text.py --date 2026-09-29 --workout B [--source-id 20382218491] \
            [--routine "Segunda - Push Day 1"] < workout.txt
Understands Hevy's Portuguese and English tags: [Aquecimento]/[Warm-up], [Falha]/[Failure], [Drop].
Never duplicates: if source_id (the Strava activity id) already exists, nothing is written.
"""
import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "strength_sets.csv"
EXERCISES = ROOT / "data" / "exercises.csv"
SET_TYPES = {"aquecimento": "warmup", "warm-up": "warmup", "warmup": "warmup",
             "falha": "failure", "failure": "failure", "drop": "drop"}
RE_SET = re.compile(
    r"^(?:S[ée]rie|Set)\s+(\d+):\s*(?:(?P<weight>[\d.,]+)\s*kg\s*x\s*(?P<reps>\d+)|(?P<reps_bw>\d+)\s*(?:repeti[çc][õo]es|reps))"
    r"(?:\s*@\s*(?P<rpe>[\d.,]+)\s*rpe)?\s*(?:\[(?P<tag>[^\]]+)\])?", re.I)
SKIP = re.compile(r"^(@hevyapp|https?://|registrado com hevyapp|logged with hevy)", re.I)
DATE_LINE = re.compile(r"^(\w+-feira,|segunda|terça|quarta|quinta|sexta|sábado|domingo|monday|tuesday|wednesday|"
                       r"thursday|friday|saturday|sunday)", re.I)


def parse(text):
    sets, exercise, ex_note = [], None, ""
    for line in (l.strip() for l in text.splitlines()):
        if not line or SKIP.match(line):
            continue
        m = RE_SET.match(line)
        if m:
            if exercise is None:
                raise ValueError(f"set without exercise: {line}")
            weight = (m["weight"] or "").replace(",", ".")
            if weight in ("0", "0.0"):
                weight = ""
            sets.append({"exercise": exercise, "set": m.group(1),
                         "set_type": SET_TYPES.get((m["tag"] or "").strip().lower(), "normal"),
                         "weight_kg": weight, "reps": m["reps"] or m["reps_bw"],
                         "rpe": (m["rpe"] or "").replace(",", "."), "notes": ex_note})
            ex_note = ""
        elif line.startswith('"') and line.endswith('"'):
            ex_note = line.strip('"')
        elif DATE_LINE.match(line):
            continue
        else:
            exercise = line
    return sets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--workout", required=True, choices=["A", "B", "C", "D", "other"])
    ap.add_argument("--source-id", default="")
    ap.add_argument("--routine", default="")
    a = ap.parse_args()
    sets = parse(sys.stdin.read())
    if not sets:
        sys.exit("no sets found in the text")

    with CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)
    if a.source_id and any(r.get("source_id") == a.source_id for r in rows):
        print(f"already imported: {a.source_id}")
        return
    if any(r["date"] == a.date and r["workout"] == a.workout for r in rows):
        sys.exit(f"workout {a.workout} already exists on {a.date}: check before importing")
    if a.routine:
        sets[0]["notes"] = f"Hevy '{a.routine}'" + (f"; {sets[0]['notes']}" if sets[0]["notes"] else "")
    with CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        for s in sets:
            w.writerow({**{k: "" for k in fields}, **s, "date": a.date, "workout": a.workout, "source_id": a.source_id})

    known = {r["exercise"] for r in csv.DictReader(EXERCISES.open(encoding="utf-8"))}
    new = sorted({s["exercise"] for s in sets} - known)
    print(f"written: {a.date} workout {a.workout} — {len(sets)} sets, {len({s['exercise'] for s in sets})} exercises")
    for n in new:
        print(f"new exercise (add to exercises.csv with name_en and muscle_group): {n}")


if __name__ == "__main__":
    main()
