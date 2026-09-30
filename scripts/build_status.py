#!/usr/bin/env python3
"""Validate the CSVs in data/ and regenerate context/status.md (the human-facing summary, in Portuguese).

Usage:  python3 scripts/build_status.py [--today YYYY-MM-DD]
Standard library only. Exits with code 1 on data errors (and does not write the file).
"""
import argparse
import csv
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "context" / "status.md"

# --- program parameters (update when the plan changes) ---
BLOCK_START = date(2026, 9, 21)
BLOCK_WEEKS = 13
HR_MAX = 192
INTERVAL_HR_ALERT = 183       # base phase: a rep above this is too hard
TIMELINE_DAYS = 14
VOLUME_WEEKS = 6
HRV_DROP_ALERT = 0.10         # 7-day mean more than 10% below the baseline
LOW_RECOVERY = 40             # Bevel recovery score below this (today/yesterday) raises an alert

RUN_TYPES = {"interval", "tempo", "long", "z2", "recovery", "race", "test"}
HARD_TYPES = {"interval", "tempo", "race", "test"}
LOCATIONS = {"treadmill", "road", "track"}
WORKOUTS = {"A", "B", "C", "D", "other"}
SET_TYPES = {"normal", "warmup", "drop", "failure", ""}
HEALTH_METRICS = ("bevel_recovery_pct", "bevel_strain_pct", "bevel_sleep_pct", "hrv_ms", "resting_hr", "sleep_h",
                  "deep_sleep_h", "rem_sleep_h", "steps", "active_kcal", "basal_kcal", "vo2max")

# --- display labels (the summary is read in Portuguese) ---
PT_RUN_TYPE = {"interval": "intervalado", "tempo": "tempo", "long": "longao", "z2": "z2",
               "recovery": "regenerativo", "race": "prova", "test": "teste"}
PT_LOCATION = {"treadmill": "esteira", "road": "rua", "track": "pista"}
PT_WORKOUT = {"other": "outro"}
PT_GROUP = {"chest": "peito", "back": "costas", "shoulders": "ombro", "biceps": "biceps", "triceps": "triceps",
            "quads": "quadriceps", "hamstrings": "posterior", "glutes": "gluteo", "adductors": "adutor",
            "calves": "panturrilha", "core": "core", "cardio": "cardio"}
PT_WEEKDAY = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]

errors, warnings = [], []


# ---------- helpers ----------
def read(name):
    p = DATA / name
    if not p.exists():
        errors.append(f"{name}: arquivo não encontrado")
        return []
    with p.open(newline="", encoding="utf-8") as f:
        rows = []
        for i, r in enumerate(csv.DictReader(f), start=2):
            if any((v or "").strip() for v in r.values()):
                r = {k: (v or "").strip() for k, v in r.items()}
                r["_ref"] = f"{name}:{i}"
                rows.append(r)
        return rows


def to_date(s, ref):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        errors.append(f"{ref}: data inválida '{s}'")
        return None


def to_num(s, ref, field):
    if not s:
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        errors.append(f"{ref}: {field} não numérico '{s}'")
        return None


def to_sec(s, ref, field):
    if not s:
        return None
    try:
        t = 0.0
        for p in s.split(":"):
            t = t * 60 + float(p)
        return t
    except ValueError:
        errors.append(f"{ref}: {field} com formato inválido '{s}' (use m:ss ou h:mm:ss)")
        return None


def fmt_dur(s):
    s = int(round(s))
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_pace(sec_km):
    m, s = divmod(int(round(sec_km)), 60)
    return f"{m}:{s:02d}/km"


def fmt_num(x, places=1):
    if x is None:
        return "–"
    return f"{x:.{places}f}".rstrip("0").rstrip(".") if places else f"{x:.0f}"


def fmt_zones(zs):
    if not zs:
        return "–"
    z = [x or 0 for x in zs]
    t = sum(z)
    if not t:
        return "–"
    return f"{100 * (z[0] + z[1]) / t:.0f}% · {100 * z[2] / t:.0f}% · {100 * (z[3] + z[4]) / t:.0f}%"


def week_start(d):
    return d - timedelta(days=d.weekday())


def day_label(d):
    return f"{PT_WEEKDAY[d.weekday()]} {d:%d/%m}"


# ---------- load and validate ----------
def load():
    runs = []
    for r in read("runs.csv"):
        ref = r["_ref"]
        r["date"] = to_date(r["date"], ref)
        if r["type"] not in RUN_TYPES:
            errors.append(f"{ref}: type '{r['type']}' inválido ({', '.join(sorted(RUN_TYPES))})")
        if r["location"] and r["location"] not in LOCATIONS:
            errors.append(f"{ref}: location '{r['location']}' inválido")
        r["km"] = to_num(r["distance_km"], ref, "distance_km")
        r["sec"] = to_sec(r["duration"], ref, "duration")
        for c in ("hr_avg", "hr_max", "rpe", "temperature_c"):
            r[c] = to_num(r[c], ref, c)
        r["pace"] = r["sec"] / r["km"] if r["km"] and r["sec"] else None
        zs = [to_num(r.get(f"z{i}_s", ""), ref, f"z{i}_s") for i in range(1, 6)]
        r["zs"] = zs if any(z is not None for z in zs) else None
        runs.append(r)
    for col in ("source_id", "strava_id"):
        vals = [x[col] for x in runs if x.get(col)]
        for i in {i for i in vals if vals.count(i) > 1}:
            errors.append(f"runs.csv: {col} duplicado '{i}' (treino importado duas vezes)")
    ids = [x["id"] for x in runs]
    for i in {i for i in ids if ids.count(i) > 1}:
        errors.append(f"runs.csv: id duplicado '{i}'")

    intervals = []
    id_set = set(ids)
    for r in read("intervals.csv"):
        ref = r["_ref"]
        if r["run_id"] not in id_set:
            errors.append(f"{ref}: run_id '{r['run_id']}' não existe em runs.csv")
        r["rep"] = int(to_num(r["rep"], ref, "rep") or 0)
        r["dist"] = to_num(r["distance_m"], ref, "distance_m")
        r["sec"] = to_sec(r["duration"], ref, "duration")
        r["speed"] = to_num(r["speed_kmh"], ref, "speed_kmh")
        if r["speed"] is None and r["dist"] and r["sec"]:
            r["speed"] = r["dist"] / r["sec"] * 3.6
        r["rec"] = to_sec(r["recovery"], ref, "recovery")
        r["hr_peak"] = to_num(r["hr_peak"], ref, "hr_peak")
        r["hr_end_recovery"] = to_num(r["hr_end_recovery"], ref, "hr_end_recovery")
        intervals.append(r)

    groups = {r["exercise"]: r["muscle_group"] or "?" for r in read("exercises.csv")}

    sets = []
    for r in read("strength_sets.csv"):
        ref = r["_ref"]
        r["date"] = to_date(r["date"], ref)
        if r["workout"] not in WORKOUTS:
            errors.append(f"{ref}: workout '{r['workout']}' inválido ({', '.join(sorted(WORKOUTS))})")
        if r["set_type"] not in SET_TYPES:
            errors.append(f"{ref}: set_type '{r['set_type']}' inválido")
        r["weight"] = to_num(r["weight_kg"], ref, "weight_kg")
        r["reps"] = to_num(r["reps"], ref, "reps")
        r["group"] = groups.get(r["exercise"])
        if r["group"] is None:
            warnings.append(f"exercício sem grupo em exercises.csv: '{r['exercise']}'")
        sets.append(r)

    health, health_dates = [], []
    for r in read("daily_health.csv"):
        ref = r["_ref"]
        r["date"] = to_date(r["date"], ref)
        for c in HEALTH_METRICS:
            r[c] = to_num(r.get(c, ""), ref, c)
        health_dates.append(r["date"])
        health.append(r)
    for d in {d for d in health_dates if health_dates.count(d) > 1}:
        errors.append(f"daily_health.csv: data duplicada {d}")

    races = []
    for r in read("races.csv"):
        ref = r["_ref"]
        r["date"] = to_date(r["date"], ref)
        r["dist"] = to_num(r["distance_km"], ref, "distance_km")
        r["chip"] = to_sec(r["chip_time"], ref, "chip_time")
        if r["run_id"] and r["run_id"] not in id_set:
            errors.append(f"{ref}: run_id '{r['run_id']}' não existe em runs.csv")
        races.append(r)

    return runs, intervals, sets, health, races


# ---------- sections (Portuguese output) ----------
def section_races(races):
    out = ["## Provas e recordes", ""]
    valid = [p for p in races if p["date"] and p["dist"] and p["chip"]]
    if not valid:
        return out + ["Sem provas registradas.", ""]
    prs = {}
    for p in valid:
        if p["dist"] not in prs or p["chip"] < prs[p["dist"]]["chip"]:
            prs[p["dist"]] = p
    for d, p in sorted(prs.items()):
        out.append(f"- **PR {fmt_num(d, 1)} km: {fmt_dur(p['chip'])}** ({fmt_pace(p['chip'] / d)}) — {p['name']}, {p['date']:%d/%m/%Y}")
    if 10 in prs and 5 not in prs:
        eq = prs[10]["chip"] * (5 / 10) ** 1.06
        out.append(f"- Equivalente 5K do PR de 10K (Riegel): ~{fmt_dur(eq)} ({fmt_pace(eq / 5)})")
    out += ["", "| data | prova | km | chip | pace | oficial | lugar geral / escalão |", "|---|---|---|---|---|---|---|"]
    for p in sorted(valid, key=lambda p: p["date"], reverse=True):
        place = f"{p['overall_place'] or '–'} / {p['category_place'] or '–'}"
        out.append(f"| {p['date']:%d/%m/%Y} | {p['name']} | {fmt_num(p['dist'], 1)} | {fmt_dur(p['chip'])} | "
                   f"{fmt_pace(p['chip'] / p['dist'])} | {p['gun_time'] or '–'} | {place} |")
    return out + [""]


def section_timeline(today, runs, sets, health):
    start = today - timedelta(days=TIMELINE_DAYS - 1)
    per_day = defaultdict(list)
    for c in runs:
        if c["date"] and start <= c["date"] <= today:
            p = f", {fmt_pace(c['pace'])}" if c["pace"] else ""
            hr = f", FC {fmt_num(c['hr_avg'], 0)}" if c["hr_avg"] else ""
            if c["km"]:
                qty = f"{fmt_num(c['km'], 2)} km"
            elif c["sec"]:
                qty = f"{fmt_dur(c['sec'])} (sem distância)"
            else:
                qty = "(sem distância/tempo)"
            per_day[c["date"]].append(f"🏃 {PT_RUN_TYPE[c['type']]} {qty}{p}{hr}")
    sessions = defaultdict(lambda: {"sets": 0, "ex": set()})
    for s in sets:
        if s["date"] and start <= s["date"] <= today and s["set_type"] != "warmup":
            k = (s["date"], s["workout"])
            sessions[k]["sets"] += 1
            sessions[k]["ex"].add(s["exercise"])
    for (d, w), v in sessions.items():
        per_day[d].append(f"🏋️ treino {PT_WORKOUT.get(w, w)} ({v['sets']} séries, {len(v['ex'])} exercícios)")
    by_date = {r["date"]: r for r in health}

    out = ["## Últimos 14 dias", "", "| dia | atividades | recup. · esforço · sono (Bevel) · HRV · passos |", "|---|---|---|"]
    d = today
    while d >= start:
        acts = "; ".join(per_day.get(d, [])) or "descanso / sem registro"
        r = by_date.get(d)
        hv = "–"
        if r:
            parts = [f"{fmt_num(r[c], 0)}%" if r[c] is not None else "–"
                     for c in ("bevel_recovery_pct", "bevel_strain_pct", "bevel_sleep_pct")]
            if r["hrv_ms"]:
                parts.append(f"{fmt_num(r['hrv_ms'], 0)} ms")
            if r["steps"]:
                parts.append(f"{r['steps'] / 1000:.1f}k passos")
            hv = " · ".join(parts)
        mark = " (hoje)" if d == today else ""
        out.append(f"| {day_label(d)}{mark} | {acts} | {hv} |")
        d -= timedelta(days=1)
    return out


def weekly_volume(today, runs, sets):
    weeks = [week_start(today) - timedelta(weeks=i) for i in range(VOLUME_WEEKS)]
    v = {w: {"km": 0.0, "km_easy": 0.0, "runs": 0, "sessions": set(), "sets": 0, "tonnage": 0.0,
             "z_easy": 0.0, "z_total": 0.0}
         for w in weeks}
    for c in runs:
        if c["date"] and week_start(c["date"]) in v:
            x = v[week_start(c["date"])]
            x["km"] += c["km"] or 0
            x["runs"] += 1
            if c["type"] not in HARD_TYPES:
                x["km_easy"] += c["km"] or 0
            if c["zs"]:
                zs = [z or 0 for z in c["zs"]]
                x["z_easy"] += zs[0] + zs[1]
                x["z_total"] += sum(zs)
    for s in sets:
        if s["date"] and week_start(s["date"]) in v and s["set_type"] != "warmup":
            x = v[week_start(s["date"])]
            x["sessions"].add((s["date"], s["workout"]))
            x["sets"] += 1
            x["tonnage"] += (s["weight"] or 0) * (s["reps"] or 0)
    return weeks, v


def section_volume(today, weeks, v):
    out = ["## Volume semanal", "",
           "| semana (seg) | km | corridas | % tempo Z1–2 (FC) | sessões academia | séries | tonelagem (kg) |",
           "|---|---|---|---|---|---|---|"]
    for w in weeks:
        x = v[w]
        easy = f"{100 * x['z_easy'] / x['z_total']:.0f}%" if x["z_total"] else "–"
        current = " (atual)" if w == week_start(today) else ""
        out.append(f"| {w:%d/%m}{current} | {fmt_num(x['km'], 1) if x['km'] else '0'} | {x['runs']} | {easy} | "
                   f"{len(x['sessions'])} | {x['sets']} | {x['tonnage']:.0f} |")
    return out


def section_runs(runs):
    last = sorted([c for c in runs if c["date"]], key=lambda c: (c["date"], c.get("start_time", ""), c["id"]))[-6:]
    out = ["## Corridas recentes", ""]
    if not last:
        return out + ["Sem corridas registradas.", ""]
    out += ["| data | tipo | local | km | tempo | pace | FC méd/máx | zonas Z1-2 · Z3 · Z4-5 | RPE | notas |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for c in reversed(last):
        out.append(f"| {day_label(c['date'])} | {PT_RUN_TYPE[c['type']]} | {PT_LOCATION.get(c['location'], '–')} | "
                   f"{fmt_num(c['km'], 2)} | {fmt_dur(c['sec']) if c['sec'] else '–'} | "
                   f"{fmt_pace(c['pace']) if c['pace'] else '–'} | {fmt_num(c['hr_avg'], 0)}/{fmt_num(c['hr_max'], 0)} | "
                   f"{fmt_zones(c['zs'])} | {fmt_num(c['rpe'], 0)} | {c['notes'] or ''} |")
    return out + [""]


def section_intervals(runs, intervals):
    ivs = sorted([c for c in runs if c["type"] == "interval" and c["date"]], key=lambda c: (c["date"], c["id"]))
    out = ["## Intervalados — tiros", ""]
    if not ivs:
        return out + ["Sem intervalados registrados.", ""]
    for c in ivs[-2:][::-1]:
        reps = sorted([t for t in intervals if t["run_id"] == c["id"]], key=lambda t: t["rep"])
        out.append(f"**{day_label(c['date'])}** ({c['id']}) — {c['notes'] or ''}")
        if not reps:
            out += ["", "_tiros não detalhados_", ""]
            continue
        out += ["", "| # | vel. km/h | pace | duração/dist. | recup. | FC pico | FC fim rec. |",
                "|---|---|---|---|---|---|---|"]
        for t in reps:
            p = fmt_pace(3600 / t["speed"]) if t["speed"] else "–"
            dd = " / ".join(x for x in [fmt_dur(t["sec"]) if t["sec"] else "",
                                        f"{fmt_num(t['dist'], 0)} m" if t["dist"] else ""] if x) or "–"
            out.append(f"| {t['rep']} | {fmt_num(t['speed'], 2)} | {p} | {dd} | {fmt_dur(t['rec']) if t['rec'] else '–'} | "
                       f"{fmt_num(t['hr_peak'], 0)} | {fmt_num(t['hr_end_recovery'], 0)} |")
        out.append("")
    return out


def section_strength(today, sets):
    out = ["## Academia — cargas por exercício", ""]
    valid = [s for s in sets if s["date"] and s["set_type"] != "warmup"]
    if not valid:
        return out + ["Sem séries registradas.", ""]
    by_ex = defaultdict(lambda: defaultdict(list))
    for s in valid:
        by_ex[s["exercise"]][s["date"]].append(s)

    def top(ss):  # best set: heaviest weight, then most reps
        return max(ss, key=lambda s: ((s["weight"] or 0), (s["reps"] or 0)))

    def txt(s):
        return f"{fmt_num(s['weight'], 1)} kg × {fmt_num(s['reps'], 0)}" if s["weight"] else f"PC × {fmt_num(s['reps'], 0)}"

    rows = []
    for ex, days in by_ex.items():
        ds = sorted(days)
        u = top(days[ds[-1]])
        group = PT_GROUP.get(u["group"], u["group"] or "?")
        arrow, prev = "", "–"
        if len(ds) > 1:
            a = top(days[ds[-2]])
            prev = txt(a)
            ku, ka = ((u["weight"] or 0), (u["reps"] or 0)), ((a["weight"] or 0), (a["reps"] or 0))
            arrow = "↑" if ku > ka else ("↓" if ku < ka else "→")
        rows.append((PT_WORKOUT.get(u["workout"], u["workout"]), group, ex, ds[-1], txt(u), len(days[ds[-1]]), prev, arrow))
    out += ["| treino | grupo | exercício | última | melhor série | séries | anterior | |",
            "|---|---|---|---|---|---|---|---|"]
    for w, g, ex, d, best, n, prev, arrow in sorted(rows):
        out.append(f"| {w} | {g} | {ex} | {d:%d/%m} | {best} | {n} | {prev} | {arrow} |")

    start = today - timedelta(days=6)
    per_group = defaultdict(int)
    for s in valid:
        if start <= s["date"] <= today:
            per_group[PT_GROUP.get(s["group"], s["group"] or "?")] += 1
    if per_group:
        out += ["", "Séries por grupo muscular (últimos 7 dias): "
                + ", ".join(f"{g} {n}" for g, n in sorted(per_group.items(), key=lambda x: -x[1]))]
    return out + [""]


def health_stats(health, today):
    """7-day mean vs. a baseline of the 28 days BEFORE that window."""
    def mean(field, start, end):
        vals = [r[field] for r in health if r["date"] and start <= r["date"] <= end and r[field] is not None]
        return (statistics.mean(vals), len(vals)) if vals else (None, 0)
    s7 = today - timedelta(days=6)
    base_end = s7 - timedelta(days=1)
    base_start = base_end - timedelta(days=27)
    return {c: (mean(c, s7, today), mean(c, base_start, base_end)) for c in HEALTH_METRICS}


def section_health(health, st):
    out = ["## Recuperação", ""]
    if not health:
        return out + ["Sem dados de recuperação registrados.", ""]
    labels = {"bevel_recovery_pct": "recuperação Bevel (%)", "bevel_strain_pct": "esforço Bevel (%)",
              "bevel_sleep_pct": "sono Bevel (%)", "hrv_ms": "HRV noite (ms)", "resting_hr": "FC repouso",
              "sleep_h": "sono (h)", "deep_sleep_h": "sono profundo (h)", "rem_sleep_h": "sono REM (h)",
              "steps": "passos", "active_kcal": "kcal ativas", "basal_kcal": "kcal em repouso",
              "vo2max": "VO2máx estimado (Watch)"}
    out += ["| métrica | média 7d | base (28d anteriores) | dias com dado (7d/base) |", "|---|---|---|---|"]
    for c, label in labels.items():
        (m7, n7), (mb, nb) = st[c]
        places = 0 if (m7 or 0) >= 100 else 1
        out.append(f"| {label} | {fmt_num(m7, places)} | {fmt_num(mb, places)} | {n7}/{nb} |")
    return out + [""]


def alerts(today, runs, intervals, sets, health, st, weeks, vol):
    a = []
    dates = [x["date"] for x in runs + sets + health if x["date"]]
    if not dates:
        return ["Base vazia — nenhum treino registrado ainda."]
    last = max(dates)
    if (today - last).days >= 3:
        a.append(f"Último registro em {last:%d/%m} ({(today - last).days} dias) — pode haver treinos não registrados.")

    start = today - timedelta(days=TIMELINE_DAYS - 1)
    by_id = {c["id"]: c for c in runs}
    for t in intervals:
        c = by_id.get(t["run_id"])
        if c and c["date"] and c["date"] >= start and t["hr_peak"] and t["hr_peak"] >= INTERVAL_HR_ALERT:
            a.append(f"Tiro {t['rep']} de {c['date']:%d/%m} com FC pico {t['hr_peak']:.0f} (≥ {INTERVAL_HR_ALERT}) — "
                     "conferir se era a intenção da fase.")

    hard = sorted({c["date"] for c in runs if c["date"] and c["type"] in HARD_TYPES and c["date"] >= start})
    for d1, d2 in zip(hard, hard[1:]):
        if (d2 - d1).days == 1:
            a.append(f"Dois dias duros seguidos: {d1:%d/%m} e {d2:%d/%m}.")

    (h7, n7), (hb, nb) = st["hrv_ms"]
    if h7 and hb and n7 >= 3 and nb >= 7 and h7 < hb * (1 - HRV_DROP_ALERT):
        a.append(f"HRV 7d ({h7:.0f} ms) mais de {HRV_DROP_ALERT:.0%} abaixo da base ({hb:.0f} ms) — considerar aliviar.")
    for r in sorted(health, key=lambda r: r["date"] or date.min)[-2:]:
        if r["date"] and (today - r["date"]).days <= 1 and r["bevel_recovery_pct"] is not None \
                and r["bevel_recovery_pct"] < LOW_RECOVERY:
            a.append(f"Recuperação Bevel baixa em {r['date']:%d/%m}: {r['bevel_recovery_pct']:.0f}% (< {LOW_RECOVERY}%).")
    (r7, rn7), (rb, rnb) = st["resting_hr"]
    if r7 and rb and rn7 >= 3 and rnb >= 7 and r7 >= rb + 3:
        a.append(f"FC de repouso 7d ({r7:.0f}) ≥ 3 bpm acima da base ({rb:.0f}).")

    prev_w, prev_w2 = weeks[1], weeks[2]
    k1, k2 = vol[prev_w]["km"], vol[prev_w2]["km"]
    if k2 and k1 > k2 * 1.15:
        a.append(f"Semana de {prev_w:%d/%m}: {k1:.1f} km, +{(k1 / k2 - 1):.0%} sobre a anterior ({k2:.1f} km).")
    k = vol[prev_w]
    if k["z_total"] and k["z_easy"] / k["z_total"] < 0.7:
        a.append(f"Semana de {prev_w:%d/%m}: só {k['z_easy'] / k['z_total']:.0%} do tempo de corrida em Z1–2 (alvo ~80%).")
    elif not k["z_total"] and k["km"] and k["km_easy"] / k["km"] < 0.7:
        a.append(f"Semana de {prev_w:%d/%m}: só {k['km_easy'] / k['km']:.0%} do km em treinos fáceis "
                 "(alvo ~80%; sem dados de zona).")
    return a


# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", help="reference date YYYY-MM-DD (default: today)")
    args = ap.parse_args()
    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else date.today()

    runs, intervals, sets, health, races = load()
    if errors:
        print("DATA ERRORS — context/status.md was not written:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    block_week = (today - BLOCK_START).days // 7 + 1
    st = health_stats(health, today)
    weeks, vol = weekly_volume(today, runs, sets)
    al = alerts(today, runs, intervals, sets, health, st, weeks, vol)

    doc = [
        "# Estado atual — fitness_log",
        "",
        f"> Gerado automaticamente por `scripts/build_status.py` em {datetime.now():%Y-%m-%d %H:%M}. "
        "Não editar à mão. O plano está em `plano.md`.",
        "",
        f"**Hoje:** {day_label(today)}/{today:%Y} · **Bloco 5K:** semana {block_week} de {BLOCK_WEEKS} "
        f"(início {BLOCK_START:%d/%m/%Y}) · **FC máx:** {HR_MAX}",
        "",
        "## Alertas",
        "",
    ]
    doc += [f"- {x}" for x in al] or ["- Nenhum."]
    doc += [""]
    doc += section_timeline(today, runs, sets, health) + [""]
    doc += section_volume(today, weeks, vol) + [""]
    doc += section_races(races)
    doc += section_runs(runs)
    doc += section_intervals(runs, intervals)
    doc += section_strength(today, sets)
    doc += section_health(health, st)
    if warnings:
        doc += ["## Pendências de dados", ""] + [f"- {x}" for x in sorted(set(warnings))] + [""]

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(doc), encoding="utf-8")
    print(f"ok: {OUT.relative_to(ROOT)} — {len(runs)} runs, {len(intervals)} intervals, "
          f"{len(sets)} sets, {len(health)} health days")
    for x in sorted(set(warnings)):
        print(f"warning: {x}")


if __name__ == "__main__":
    main()
