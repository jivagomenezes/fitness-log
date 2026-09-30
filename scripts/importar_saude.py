#!/usr/bin/env python3
"""Importa as amostras do app Saúde enviadas pelo atalho do iPhone (raw/saude/*.txt) para data/recuperacao.csv.

Formato de cada arquivo (um por execução do atalho, nome AAAA-MM-DD_HHMM.txt):
    tipo;inicio;fim;valor
    hrv;2026-09-30T03:12:45+01:00;2026-09-30T03:13:45+01:00;48
    fcr;2026-09-30T00:00:00+01:00;2026-09-30T08:00:00+01:00;52
    sono;2026-09-29T23:40:00+01:00;2026-09-30T00:55:00+01:00;Principal
tipo: hrv (ms, SDNN do Apple Watch), fcr (FC de repouso, bpm), sono (fase: Principal/Profundo/REM/Acordado/Na Cama,
ou Core/Deep/REM/Awake/In Bed). As datas podem vir em ISO 8601 ou em "dd/mm/aaaa, HH:MM".

A data do registro é a do nome do arquivo (a manhã em que o atalho rodou); a "noite" é das 18:00 da véspera
às 14:00 desse dia. Se houver mais de um arquivo no mesmo dia, vale o mais recente.
Faz upsert: preenche hrv_ms, fc_repouso e sono_* do dia sem apagar os scores do Bevel.

Uso:  python3 scripts/importar_saude.py            (processa todos os arquivos de raw/saude)
"""
import csv
import re
import statistics
import sys
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


def uniao_horas(intervalos):
    tot, fim_atual, ini_atual = 0.0, None, None
    for ini, fim in sorted(intervalos):
        if fim_atual is None or ini > fim_atual:
            if fim_atual is not None:
                tot += (fim_atual - ini_atual).total_seconds()
            ini_atual, fim_atual = ini, fim
        else:
            fim_atual = max(fim_atual, fim)
    if fim_atual is not None:
        tot += (fim_atual - ini_atual).total_seconds()
    return tot / 3600


def resumo(arquivo, dia):
    noite_ini = datetime.combine(dia - timedelta(days=1), time(18, 0))
    noite_fim = datetime.combine(dia, time(14, 0))
    hrv, fcr, fases = [], [], {"leve": [], "profundo": [], "rem": []}
    for n, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
        linha = linha.strip()
        if not linha or linha.lower().startswith("tipo;"):
            continue
        partes = [p.strip() for p in linha.split(";")]
        if len(partes) < 4:
            avisos.append(f"{arquivo.name}:{n}: linha incompleta")
            continue
        tipo, ini, fim, valor = partes[0].lower(), quando(partes[1]), quando(partes[2]), partes[3]
        if tipo == "hrv" and noite_ini <= ini <= noite_fim and num(valor) is not None:
            hrv.append(num(valor))
        elif tipo == "fcr" and num(valor) is not None:
            fcr.append((ini, num(valor)))
        elif tipo == "sono" and noite_ini <= fim <= noite_fim:
            chave = valor.lower().replace("_", " ").strip()
            if chave not in FASES:
                avisos.append(f"{arquivo.name}:{n}: fase de sono desconhecida '{valor}' (não contada)")
                continue
            if FASES[chave]:
                fases[FASES[chave]].append((ini, fim))
    todas = fases["leve"] + fases["profundo"] + fases["rem"]
    return {
        "hrv_ms": f"{statistics.mean(hrv):.0f}" if hrv else "",
        "fc_repouso": f"{max(fcr)[1]:.0f}" if fcr else "",
        "sono_h": f"{uniao_horas(todas):.2f}" if todas else "",
        "sono_profundo_h": f"{uniao_horas(fases['profundo']):.2f}" if fases["profundo"] else "",
        "sono_rem_h": f"{uniao_horas(fases['rem']):.2f}" if fases["rem"] else "",
    }


def main():
    arquivos = {}
    for a in sorted(RAW.glob("*.txt")):
        m = re.match(r"(\d{4}-\d{2}-\d{2})", a.name)
        if m:
            arquivos[m.group(1)] = a  # o mais recente do dia sobrescreve
    if not arquivos:
        print("nenhum arquivo em raw/saude")
        return
    with CSV.open(newline="", encoding="utf-8") as f:
        leitor = csv.DictReader(f)
        campos, linhas = list(leitor.fieldnames), list(leitor)
    anterior = "sono_h"
    for c in ("sono_profundo_h", "sono_rem_h"):
        if c not in campos:
            campos.insert(campos.index(anterior) + 1, c)
        anterior = c
    por_data = {r["data"]: r for r in linhas}
    for d, a in sorted(arquivos.items()):
        r = resumo(a, datetime.strptime(d, "%Y-%m-%d").date())
        if not any(r.values()):
            avisos.append(f"{a.name}: nenhuma amostra da noite encontrada")
            continue
        linha = por_data.get(d)
        if linha is None:
            linha = {k: "" for k in campos}
            linha.update(data=d, fonte="saude")
            linhas.append(linha)
            por_data[d] = linha
        elif "saude" not in (linha.get("fonte") or ""):
            linha["fonte"] = f"{linha['fonte']}+saude" if linha.get("fonte") else "saude"
        for k, v in r.items():
            if v:
                linha[k] = v
        print(f"{d}: HRV {r['hrv_ms'] or '–'} ms · FC repouso {r['fc_repouso'] or '–'} · "
              f"sono {r['sono_h'] or '–'} h (profundo {r['sono_profundo_h'] or '–'}, REM {r['sono_rem_h'] or '–'})")
    linhas.sort(key=lambda r: r["data"])
    with CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in campos} for r in linhas)
    for x in avisos:
        print(f"aviso: {x}", file=sys.stderr)


if __name__ == "__main__":
    main()
