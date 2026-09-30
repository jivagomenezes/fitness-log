#!/usr/bin/env python3
"""Importa um treino do Hevy em texto (o "compartilhar" do app ou a descrição da atividade no Strava)
para data/academia.csv.

Uso:  python3 scripts/importar_hevy_texto.py --data 2026-09-29 --treino B [--fonte-id 20382218491] \
          [--rotina "Segunda - Push Day 1"] < treino.txt
Entende as marcas em PT e EN: [Aquecimento]/[Warm-up], [Falha]/[Failure], [Drop].
Não duplica: se o fonte_id (id da atividade no Strava) já existir, não grava de novo.
"""
import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "academia.csv"
EXS = ROOT / "data" / "exercicios.csv"
TIPOS = {"aquecimento": "aquecimento", "warm-up": "aquecimento", "falha": "falha", "failure": "falha", "drop": "drop"}
RE_SERIE = re.compile(
    r"^S[ée]rie\s+(\d+):\s*(?:(?P<carga>[\d.,]+)\s*kg\s*x\s*(?P<reps>\d+)|(?P<reps_pc>\d+)\s*repeti[çc][õo]es)"
    r"(?:\s*@\s*(?P<rpe>[\d.,]+)\s*rpe)?\s*(?:\[(?P<tipo>[^\]]+)\])?", re.I)
IGNORAR = re.compile(r"^(@hevyapp|https?://|registrado com hevyapp)", re.I)


def parse(texto):
    series, ex, nota_ex = [], None, ""
    for linha in (l.strip() for l in texto.splitlines()):
        if not linha or IGNORAR.match(linha):
            continue
        m = RE_SERIE.match(linha)
        if m:
            if ex is None:
                raise ValueError(f"série sem exercício: {linha}")
            tipo = TIPOS.get((m["tipo"] or "").strip().lower(), "normal")
            carga = (m["carga"] or "").replace(",", ".")
            if carga in ("0", "0.0"):
                carga = ""
            series.append({"exercicio": ex, "serie": m.group(1), "tipo_serie": tipo, "carga_kg": carga,
                           "reps": m["reps"] or m["reps_pc"], "rpe": (m["rpe"] or "").replace(",", "."),
                           "notas": nota_ex})
            nota_ex = ""
        elif linha.startswith('"') and linha.endswith('"'):
            nota_ex = linha.strip('"')
        elif re.match(r"^\w+-feira,|^(segunda|terça|quarta|quinta|sexta|sábado|domingo)", linha, re.I):
            continue  # linha de data do texto compartilhado
        else:
            ex = linha
    return series


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--treino", required=True, choices=["A", "B", "C", "D", "outro"])
    ap.add_argument("--fonte-id", default="")
    ap.add_argument("--rotina", default="")
    a = ap.parse_args()
    series = parse(sys.stdin.read())
    if not series:
        sys.exit("nenhuma série encontrada no texto")

    with CSV.open(newline="", encoding="utf-8") as f:
        leitor = csv.DictReader(f)
        campos, linhas = leitor.fieldnames, list(leitor)
    if a.fonte_id and any(r.get("fonte_id") == a.fonte_id for r in linhas):
        print(f"já importado: {a.fonte_id}")
        return
    if any(r["data"] == a.data and r["treino"] == a.treino for r in linhas):
        sys.exit(f"já existe treino {a.treino} em {a.data}: conferir antes de importar")
    if a.rotina:
        series[0]["notas"] = f"Hevy '{a.rotina}'" + (f"; {series[0]['notas']}" if series[0]["notas"] else "")
    with CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        for s in series:
            w.writerow({**{k: "" for k in campos}, **s, "data": a.data, "treino": a.treino, "fonte_id": a.fonte_id})

    conhecidos = {r["exercicio"] for r in csv.DictReader(EXS.open(encoding="utf-8"))}
    novos = sorted({s["exercicio"] for s in series} - conhecidos)
    print(f"gravado: {a.data} treino {a.treino} — {len(series)} séries, "
          f"{len({s['exercicio'] for s in series})} exercícios")
    for n in novos:
        print(f"exercício novo (adicionar em exercicios.csv): {n}")


if __name__ == "__main__":
    main()
