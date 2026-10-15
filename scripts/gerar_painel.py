#!/usr/bin/env python3
"""Gera docs/runs.json (dados do Painel de Corrida) a partir de data/corridas.csv.

Faz parte do pipeline do fitness-log: os CSVs sao a fonte de verdade; este script
le as corridas e computa volume, ACWR, checagem 80/20, eficiencia, benchmarks e a
tabela de corridas que o docs/index.html consome via fetch.

Uso:
    python3 scripts/gerar_painel.py                 # escreve docs/runs.json
    python3 scripts/gerar_painel.py --out /tmp/x    # escreve em outro lugar (teste)
"""
import csv, json, argparse, datetime as dt
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TIPO_MAP = {"prova": "race", "intervalado": "interval", "longao": "long",
            "tempo": "tempo", "z2": "z2"}
FRAG_MIN_KM = 1.0  # ignora fragmentos/reinicios curtos


def dur_s(s):
    s = (s or "").strip()
    if not s:
        return 0
    p = [int(x) for x in s.split(":")]
    if len(p) == 3:
        return p[0] * 3600 + p[1] * 60 + p[2]
    if len(p) == 2:
        return p[0] * 60 + p[1]
    return p[0]


def fmt_pace(sec_per_km):
    m, s = divmod(int(round(sec_per_km)), 60)
    return f"{m}:{s:02d}"


def monday(d):
    return d - dt.timedelta(days=d.weekday())


def num(x, cast=float, default=0):
    x = (x or "").strip()
    if not x:
        return default
    try:
        return cast(x)
    except ValueError:
        return default


def load_runs(path):
    runs = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            dist = num(r.get("distancia_km"))
            if dist < FRAG_MIN_KM:
                continue
            d = dt.date.fromisoformat(r["data"].strip())
            dur = dur_s(r.get("duracao"))
            z = [int(num(r.get(f"z{i}_s"), int)) for i in range(1, 6)]
            sumz = sum(z) or 1
            runs.append({
                "date": d.isoformat(),
                "_d": d,
                "type": TIPO_MAP.get(r.get("tipo", "").strip(), r.get("tipo", "").strip()),
                "dist": round(dist, 2),
                "dur": dur,
                "pace": fmt_pace(dur / dist) if dist else "-",
                "hr": int(num(r.get("fc_media"), int)),
                "hrmax": int(num(r.get("fc_max"), int)),
                "cad": int(num(r.get("cadencia_spm"), int)),
                "easy": round((z[0] + z[1]) / sumz * 100),
                "z1": z[0], "z2": z[1], "z3": z[2], "z4": z[3], "z5": z[4],
                "note": (r.get("notas") or "").strip(),
                "_kmh": round(dist / (dur / 3600), 2) if dur else 0,
            })
    runs.sort(key=lambda x: x["_d"])
    return runs


def build(runs):
    if not runs:
        return {"runs": [], "weeks": [], "months": [], "acwr": 0, "acute": 0,
                "chronic": 0, "intensity": {"easy": 0, "mod": 0, "hard": 0},
                "typedist": {}, "eff": [], "totkm": 0, "nruns": 0}
    asof = runs[-1]["_d"]

    # semanas (segunda a domingo)
    wk = {}
    for r in runs:
        k = monday(r["_d"])
        wk.setdefault(k, {"km": 0.0, "n": 0})
        wk[k]["km"] += r["dist"]; wk[k]["n"] += 1
    w0, w1 = monday(runs[0]["_d"]), monday(asof)
    weeks, cur = [], w0
    while cur <= w1:
        v = wk.get(cur, {"km": 0.0, "n": 0})
        weeks.append({"label": cur.strftime("%d/%m"), "km": round(v["km"], 1), "n": v["n"]})
        cur += dt.timedelta(days=7)

    # meses
    mo = {}
    for r in runs:
        k = r["date"][:7]
        mo.setdefault(k, {"km": 0.0, "n": 0})
        mo[k]["km"] += r["dist"]; mo[k]["n"] += 1
    months = [{"m": k, "km": round(v["km"], 1), "n": v["n"]} for k, v in sorted(mo.items())]

    # ACWR (relativo ao ultimo treino)
    acute = round(sum(r["dist"] for r in runs if (asof - r["_d"]).days < 7), 1)
    chronic = round(sum(r["dist"] for r in runs if (asof - r["_d"]).days < 28) / 4, 1)
    acwr = round(acute / chronic, 2) if chronic else 0

    # intensidade 80/20 por tempo
    easy = sum(r["z1"] + r["z2"] for r in runs)
    mod = sum(r["z3"] for r in runs)
    hard = sum(r["z4"] + r["z5"] for r in runs)
    tot = (easy + mod + hard) or 1
    intensity = {"easy": round(easy / tot * 100), "mod": round(mod / tot * 100),
                 "hard": round(hard / tot * 100)}

    # distribuicao por tipo
    typedist = {}
    for r in runs:
        t = typedist.setdefault(r["type"], {"n": 0, "km": 0.0})
        t["n"] += 1; t["km"] += r["dist"]
    for t in typedist.values():
        t["km"] = round(t["km"], 1)

    # eficiencia (corridas faceis em Z2/longao)
    eff = [{"date": r["date"], "kmh": r["_kmh"], "hr": r["hr"]}
           for r in runs if r["type"] in ("z2", "long") and r["hr"]]

    # benchmarks
    longest = max(runs, key=lambda r: r["dist"])
    tempos = [r for r in runs if r["type"] == "tempo"]
    fastest = min(tempos, key=lambda r: r["dur"] / r["dist"]) if tempos else None
    best_eff = max(eff, key=lambda e: e["kmh"]) if eff else None

    out = {
        "runs": [{k: r[k] for k in ("date", "type", "dist", "dur", "pace", "hr",
                                    "hrmax", "cad", "easy", "z1", "z2", "z3", "z4",
                                    "z5", "note")} for r in runs],
        "weeks": weeks, "months": months,
        "acwr": acwr, "acute": acute, "chronic": chronic,
        "intensity": intensity, "typedist": typedist, "eff": eff,
        "totkm": round(sum(r["dist"] for r in runs), 1), "nruns": len(runs),
        "longest": {"date": longest["date"], "dist": longest["dist"]},
        "asof": asof.isoformat(),
    }
    if fastest:
        out["fastest_tempo"] = {"date": fastest["date"], "pace": fastest["pace"]}
    if best_eff:
        out["best_eff"] = best_eff
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(REPO / "data" / "corridas.csv"))
    ap.add_argument("--out", default=str(REPO / "docs" / "runs.json"))
    a = ap.parse_args()
    data = build(load_runs(a.csv))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"OK: {a.out} — {data['nruns']} corridas, {data['totkm']} km, "
          f"ACWR {data['acwr']}, 80/20 {data['intensity']}")


if __name__ == "__main__":
    main()
