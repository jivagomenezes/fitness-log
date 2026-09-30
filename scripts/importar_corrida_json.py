#!/usr/bin/env python3
"""Importa uma corrida exportada do Apple Watch em JSON (workout_*.json) para data/corridas.csv.

Uso:  python3 scripts/importar_corrida_json.py ARQUIVO.json --tipo z2 [--rpe 3] [--notas "..."]
Não duplica: se o uuid do treino já estiver em fonte_id, não grava de novo.
"""
import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "corridas.csv"
TZ = ZoneInfo("Europe/Lisbon")
TIPOS = {"intervalado", "tempo", "longao", "z2", "regenerativo", "prova", "teste"}


def val(j, k):
    v = j.get(k)
    return v.get("value") if isinstance(v, dict) else v


def fdur(s):
    s = int(round(s))
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arquivo")
    ap.add_argument("--tipo", required=True, choices=sorted(TIPOS))
    ap.add_argument("--rpe", default="")
    ap.add_argument("--notas", default="")
    a = ap.parse_args()

    j = json.loads(Path(a.arquivo).read_text(encoding="utf-8"))
    if (j.get("activity") or {}).get("name") != "Running":
        sys.exit(f"não é corrida: {(j.get('activity') or {}).get('name')}")
    ini = datetime.fromisoformat(j["startDate"].replace("Z", "+00:00")).astimezone(TZ)
    indoor = j.get("location") == "Indoor"
    esteira = "treadmill" in ((j.get("device") or {}).get("model") or "")
    local = "esteira" if (indoor or esteira) else "rua"
    zonas = j.get("zones") or {}
    z = [str(round(((zonas.get(f"zone{i}") or {}).get("time") or {}).get("value", 0))) if zonas else ""
         for i in range(1, 6)]
    temp = ""
    if local == "rua":
        t = ((j.get("weather") or {}).get("temperature") or "").replace("°C", "").strip()
        temp = t

    with CSV.open(newline="", encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    if any(r["fonte_id"] == j["uuid"] for r in linhas):
        print(f"já importado: {j['uuid']}")
        return
    data = ini.date().isoformat()
    n = sum(1 for r in linhas if r["data"] == data) + 1
    manuais = [r for r in linhas if r["data"] == data and r["fonte"] == "manual" and not r["fonte_id"]]
    row = {
        "id": f"{data}-{n}", "data": data, "inicio": ini.strftime("%H:%M"), "tipo": a.tipo, "local": local,
        "distancia_km": f"{val(j, 'distance'):.2f}", "duracao": fdur(val(j, "duration")),
        "fc_media": val(j, "averageHeartRate") or "", "fc_max": val(j, "maxHeartRate") or "",
        "z1_s": z[0], "z2_s": z[1], "z3_s": z[2], "z4_s": z[3], "z5_s": z[4],
        "cadencia_spm": val(j, "cadence") or "", "elevacao_m": val(j, "elevationAscended") or "",
        "rpe": a.rpe, "temperatura_c": temp, "fonte": "apple_watch", "fonte_id": j["uuid"], "notas": a.notas,
    }
    if len(manuais) == 1:
        # já existe registro manual desse dia: completa com os dados do relógio,
        # mantendo id, tipo, local e notas informados à mão
        m = manuais[0]
        for k, v in row.items():
            if k in ("id", "tipo", "notas", "rpe") and m[k]:
                continue
            if k == "local" and m[k]:
                continue
            m[k] = v
        m["notas"] = m["notas"] or row["notas"]
        with CSV.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
            w.writeheader()
            w.writerows(linhas)
        print(f"completado registro manual {m['id']} ({m['tipo']}) com dados do relógio: "
              f"{m['distancia_km']} km em {m['duracao']} (FC {m['fc_media']}/{m['fc_max']})")
        return
    if len(manuais) > 1:
        sys.exit(f"há {len(manuais)} registros manuais em {data}: completar à mão")
    with CSV.open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=list(row)).writerow(row)
    print(f"gravado: {row['id']} {a.tipo} {row['distancia_km']} km em {row['duracao']} "
          f"(FC {row['fc_media']}/{row['fc_max']}, {local}, início {row['inicio']})")


if __name__ == "__main__":
    main()
