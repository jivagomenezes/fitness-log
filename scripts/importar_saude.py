#!/usr/bin/env python3
"""Importa as amostras do app Saúde enviadas pelo atalho do iPhone (raw/saude/*.txt) para data/recuperacao.csv.

Cada execução do atalho grava um arquivo raw/saude/AAAA-MM-DD_HHMM.txt, uma amostra por linha:
    tipo;inicio;fim;valor[;unidade]

    hrv;2026-09-30T03:12:45+01:00;2026-09-30T03:13:45+01:00;48
    fcr;2026-09-30T00:00:00+01:00;2026-09-30T08:00:00+01:00;52
    sono;2026-09-29T23:40:00+01:00;2026-09-30T00:55:00+01:00;Principal
    passos;2026-09-30T00:00:00+01:00;2026-10-01T00:00:00+01:00;11234
    kcal_ativas;2026-09-30T00:00:00+01:00;2026-10-01T00:00:00+01:00;612;kcal
    kcal_repouso;2026-09-30T00:00:00+01:00;2026-10-01T00:00:00+01:00;1788;kcal

tipos:
  hrv           amostras de HRV (ms, SDNN do Apple Watch) — média da NOITE (18:00 da véspera às 14:00)
  fcr           FC de repouso (bpm) — a amostra mais recente do dia
  sono          fases do sono (Principal/Profundo/REM/Acordado/Na Cama ou Core/Deep/REM/Awake/In Bed)
                — horas dormidas na noite que termina naquele dia (união dos intervalos, sem contar 2×)
  passos, kcal_ativas, kcal_repouso
                totais do dia (o atalho pede ao Saúde "agrupado por dia"); vale o MAIOR total recebido
                para o dia, porque o total só cresce — a execução da manhã seguinte fecha o dia anterior.
                Energia em kJ é convertida para kcal.

Todas as amostras de todos os arquivos são juntadas (linhas repetidas contam uma vez), então o atalho pode
rodar quantas vezes quiser. Faz upsert em recuperacao.csv sem apagar os scores do Bevel.

Uso:  python3 scripts/importar_saude.py
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
RAW = ROOT / "raw" / "saude"
CSV = ROOT / "data" / "recuperacao.csv"

FASES = {
    "profundo": "profundo", "deep": "profundo", "asleepdeep": "profundo",
    "rem": "rem", "asleeprem": "rem",
    "principal": "leve", "core": "leve", "leve": "leve", "light": "leve", "asleepcore": "leve",
    "dormindo": "leve", "a dormir": "leve", "asleep": "leve", "sono": "leve", "asleepunspecified": "leve",
    "não especificado": "leve", "unspecified": "leve",
    "acordado": None, "desperto": None, "awake": None,
    "na cama": None, "em cama": None, "in bed": None, "inbed": None,
}
DIARIOS = {"passos": "passos", "kcal_ativas": "kcal_ativas", "kcal_repouso": "kcal_repouso"}
NOVAS_COLUNAS = ["sono_profundo_h", "sono_rem_h", "passos", "kcal_ativas", "kcal_repouso"]
avisos = []


def num(s):
    m = re.search(r"-?\d+(?:[.,]\d+)?", s or "")
    return float(m.group().replace(",", ".")) if m else None


def quando(s):
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
    raise ValueError(f"data não reconhecida: {s!r}")


def horas(intervalos):
    """Horas cobertas pela união dos intervalos (trechos sobrepostos contam uma vez)."""
    tot, ini_a, fim_a = 0.0, None, None
    for ini, fim in sorted(intervalos):
        if fim_a is None or ini > fim_a:
            if fim_a is not None:
                tot += (fim_a - ini_a).total_seconds()
            ini_a, fim_a = ini, fim
        else:
            fim_a = max(fim_a, fim)
    if fim_a is not None:
        tot += (fim_a - ini_a).total_seconds()
    return tot / 3600


def ler_amostras():
    vistas, amostras, datas_arquivos = set(), [], set()
    for a in sorted(RAW.glob("*.txt")):
        m = re.match(r"(\d{4}-\d{2}-\d{2})", a.name)
        if m:
            datas_arquivos.add(datetime.strptime(m.group(1), "%Y-%m-%d").date())
        for n, linha in enumerate(a.read_text(encoding="utf-8").splitlines(), 1):
            linha = linha.strip()
            if not linha or linha.lower().startswith("tipo;") or linha in vistas:
                continue
            vistas.add(linha)
            p = [x.strip() for x in linha.split(";")]
            if len(p) < 4:
                avisos.append(f"{a.name}:{n}: linha incompleta")
                continue
            try:
                amostras.append({"tipo": p[0].lower(), "ini": quando(p[1]), "fim": quando(p[2]),
                                 "valor": p[3], "unidade": p[4].lower() if len(p) > 4 else "",
                                 "ref": f"{a.name}:{n}"})
            except ValueError as e:
                avisos.append(f"{a.name}:{n}: {e}")
    return amostras, datas_arquivos


def calcular(amostras, datas_arquivos):
    por_dia = defaultdict(dict)

    # totais diários: maior valor recebido por dia
    for s in amostras:
        col = DIARIOS.get(s["tipo"])
        if not col or num(s["valor"]) is None:
            continue
        v = num(s["valor"])
        if col.startswith("kcal") and (s["unidade"] in ("kj", "kilojoule", "quilojoule") or "kj" in s["valor"].lower()):
            v /= 4.184
        dia = s["ini"].date()
        por_dia[dia][col] = max(por_dia[dia].get(col, 0), v)

    # métricas da noite / do dia
    dias = set(datas_arquivos) | set(por_dia)
    for dia in dias:
        n_ini = datetime.combine(dia - timedelta(days=1), time(18, 0))
        n_fim = datetime.combine(dia, time(14, 0))
        hrv = [num(s["valor"]) for s in amostras
               if s["tipo"] == "hrv" and n_ini <= s["ini"] <= n_fim and num(s["valor"]) is not None]
        fcr = [(s["ini"], num(s["valor"])) for s in amostras
               if s["tipo"] == "fcr" and s["ini"].date() == dia and num(s["valor"]) is not None]
        fases = {"leve": [], "profundo": [], "rem": []}
        for s in amostras:
            if s["tipo"] != "sono" or not (n_ini <= s["fim"] <= n_fim):
                continue
            chave = s["valor"].lower().replace("_", " ").strip()
            if chave not in FASES:
                avisos.append(f"{s['ref']}: fase de sono desconhecida '{s['valor']}' (não contada)")
            elif FASES[chave]:
                fases[FASES[chave]].append((s["ini"], s["fim"]))
        d = por_dia[dia]
        if hrv:
            d["hrv_ms"] = statistics.mean(hrv)
        if fcr:
            d["fc_repouso"] = max(fcr)[1]
        todas = fases["leve"] + fases["profundo"] + fases["rem"]
        if todas:
            d["sono_h"] = horas(todas)
            d["sono_profundo_h"] = horas(fases["profundo"])
            d["sono_rem_h"] = horas(fases["rem"])
    return {k: v for k, v in por_dia.items() if v}


FORMATOS = {"hrv_ms": "{:.0f}", "fc_repouso": "{:.0f}", "sono_h": "{:.2f}", "sono_profundo_h": "{:.2f}",
            "sono_rem_h": "{:.2f}", "passos": "{:.0f}", "kcal_ativas": "{:.0f}", "kcal_repouso": "{:.0f}"}


def main():
    amostras, datas_arquivos = ler_amostras()
    if not amostras:
        print("nenhuma amostra em raw/saude")
        return
    resultado = calcular(amostras, datas_arquivos)

    with CSV.open(newline="", encoding="utf-8") as f:
        leitor = csv.DictReader(f)
        campos, linhas = list(leitor.fieldnames), list(leitor)
    anterior = "sono_h"
    for c in NOVAS_COLUNAS:
        if c not in campos:
            campos.insert(campos.index(anterior) + 1, c)
        anterior = c
    por_data = {r["data"]: r for r in linhas}

    for dia, vals in sorted(resultado.items()):
        d = dia.isoformat()
        linha = por_data.get(d)
        if linha is None:
            linha = {k: "" for k in campos}
            linha.update(data=d, fonte="saude")
            linhas.append(linha)
            por_data[d] = linha
        elif "saude" not in (linha.get("fonte") or ""):
            linha["fonte"] = f"{linha['fonte']}+saude" if linha.get("fonte") else "saude"
        for k, v in vals.items():
            linha[k] = FORMATOS[k].format(v)
        print(f"{d}: " + " · ".join(f"{k} {linha[k]}" for k in FORMATOS if linha.get(k)))

    linhas.sort(key=lambda r: r["data"])
    with CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in campos} for r in linhas)
    for x in sorted(set(avisos)):
        print(f"aviso: {x}", file=sys.stderr)


if __name__ == "__main__":
    main()
