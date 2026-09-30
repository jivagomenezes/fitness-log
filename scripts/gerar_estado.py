#!/usr/bin/env python3
"""Valida os CSVs de data/ e regenera contexto/estado_atual.md.

Uso:  python3 scripts/gerar_estado.py [--hoje AAAA-MM-DD]
Só biblioteca padrão. Sai com código 1 se houver erro de dados (e não gera o arquivo).
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
OUT = ROOT / "contexto" / "estado_atual.md"

# --- parâmetros do programa (ajustar aqui quando o plano mudar) ---
INICIO_BLOCO = date(2026, 9, 21)
SEMANAS_BLOCO = 13
FC_MAX = 192
FC_TIRO_ALERTA = 183          # na fase de base, tiro acima disso = rápido demais
DIAS_TIMELINE = 14
SEMANAS_VOLUME = 6
QUEDA_HRV_ALERTA = 0.10       # média 7d abaixo da linha de base 28d em mais de 10%
RECUP_BAIXA = 40              # score de recuperação do Bevel abaixo disso (hoje/ontem) gera alerta

TIPOS_CORRIDA = {"intervalado", "tempo", "longao", "z2", "regenerativo", "prova", "teste"}
DUROS = {"intervalado", "tempo", "prova", "teste"}
LOCAIS = {"esteira", "rua", "pista"}
TREINOS = {"A", "B", "C", "D", "outro"}
TIPOS_SERIE = {"normal", "aquecimento", "drop", "falha", ""}
DIAS_PT = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]

erros, avisos = [], []


# ---------- utilitários ----------
def ler(nome):
    p = DATA / nome
    if not p.exists():
        erros.append(f"{nome}: arquivo não encontrado")
        return []
    with p.open(newline="", encoding="utf-8") as f:
        linhas = []
        for i, r in enumerate(csv.DictReader(f), start=2):
            if any((v or "").strip() for v in r.values()):
                r = {k: (v or "").strip() for k, v in r.items()}
                r["_linha"] = f"{nome}:{i}"
                linhas.append(r)
        return linhas


def dt(s, ref):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        erros.append(f"{ref}: data inválida '{s}'")
        return None


def num(s, ref, campo):
    if not s:
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        erros.append(f"{ref}: {campo} não numérico '{s}'")
        return None


def seg(s, ref, campo):
    if not s:
        return None
    try:
        t = 0.0
        for p in s.split(":"):
            t = t * 60 + float(p)
        return t
    except ValueError:
        erros.append(f"{ref}: {campo} com formato inválido '{s}' (use m:ss ou h:mm:ss)")
        return None


def fdur(s):
    s = int(round(s))
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fpace(sec_km):
    m, s = divmod(int(round(sec_km)), 60)
    return f"{m}:{s:02d}/km"


def fnum(x, casas=1):
    if x is None:
        return "–"
    return f"{x:.{casas}f}".rstrip("0").rstrip(".") if casas else f"{x:.0f}"


def fzonas(zs):
    if not zs:
        return "–"
    z = [x or 0 for x in zs]
    t = sum(z)
    if not t:
        return "–"
    return f"{100 * (z[0] + z[1]) / t:.0f}% · {100 * z[2] / t:.0f}% · {100 * (z[3] + z[4]) / t:.0f}%"


def seg_semana(d):
    return d - timedelta(days=d.weekday())


def dia_label(d):
    return f"{DIAS_PT[d.weekday()]} {d:%d/%m}"


# ---------- carga e validação ----------
def carregar():
    corridas = []
    for r in ler("corridas.csv"):
        ref = r["_linha"]
        r["data"] = dt(r["data"], ref)
        if r["tipo"] not in TIPOS_CORRIDA:
            erros.append(f"{ref}: tipo '{r['tipo']}' inválido ({', '.join(sorted(TIPOS_CORRIDA))})")
        if r["local"] and r["local"] not in LOCAIS:
            erros.append(f"{ref}: local '{r['local']}' inválido")
        r["km"] = num(r["distancia_km"], ref, "distancia_km")
        r["seg"] = seg(r["duracao"], ref, "duracao")
        for c in ("fc_media", "fc_max", "rpe", "temperatura_c"):
            r[c] = num(r[c], ref, c)
        r["pace"] = r["seg"] / r["km"] if r["km"] and r["seg"] else None
        zs = [num(r.get(f"z{i}_s", ""), ref, f"z{i}_s") for i in range(1, 6)]
        r["zs"] = zs if any(z is not None for z in zs) else None
        corridas.append(r)
    fids = [c["fonte_id"] for c in corridas if c.get("fonte_id")]
    for i in {i for i in fids if fids.count(i) > 1}:
        erros.append(f"corridas.csv: fonte_id duplicado '{i}' (treino importado duas vezes)")
    ids = [c["id"] for c in corridas]
    for i in {i for i in ids if ids.count(i) > 1}:
        erros.append(f"corridas.csv: id duplicado '{i}'")

    tiros = []
    idset = set(ids)
    for r in ler("tiros.csv"):
        ref = r["_linha"]
        if r["corrida_id"] not in idset:
            erros.append(f"{ref}: corrida_id '{r['corrida_id']}' não existe em corridas.csv")
        r["n"] = int(num(r["n"], ref, "n") or 0)
        r["dist"] = num(r["distancia_m"], ref, "distancia_m")
        r["seg"] = seg(r["duracao"], ref, "duracao")
        r["vel"] = num(r["velocidade_kmh"], ref, "velocidade_kmh")
        if r["vel"] is None and r["dist"] and r["seg"]:
            r["vel"] = r["dist"] / r["seg"] * 3.6
        r["rec"] = seg(r["recuperacao"], ref, "recuperacao")
        r["fc_pico"] = num(r["fc_pico"], ref, "fc_pico")
        r["fc_fim_rec"] = num(r["fc_fim_rec"], ref, "fc_fim_rec")
        tiros.append(r)

    grupos = {}
    for r in ler("exercicios.csv"):
        grupos[r["exercicio"]] = r["grupo"] or "?"

    series = []
    for r in ler("academia.csv"):
        ref = r["_linha"]
        r["data"] = dt(r["data"], ref)
        if r["treino"] not in TREINOS:
            erros.append(f"{ref}: treino '{r['treino']}' inválido ({', '.join(sorted(TREINOS))})")
        if r["tipo_serie"] not in TIPOS_SERIE:
            erros.append(f"{ref}: tipo_serie '{r['tipo_serie']}' inválido")
        r["carga"] = num(r["carga_kg"], ref, "carga_kg")
        r["reps"] = num(r["reps"], ref, "reps")
        r["grupo"] = grupos.get(r["exercicio"])
        if r["grupo"] is None:
            avisos.append(f"exercício sem grupo em exercicios.csv: '{r['exercicio']}'")
        series.append(r)

    rec = []
    datas_rec = []
    for r in ler("recuperacao.csv"):
        ref = r["_linha"]
        r["data"] = dt(r["data"], ref)
        for c in ("recuperacao_pct", "esforco_pct", "sono_pct", "hrv_ms", "fc_repouso", "sono_h",
                  "sono_profundo_h", "sono_rem_h", "passos", "kcal_ativas", "kcal_repouso"):
            r[c] = num(r.get(c, ""), ref, c)
        datas_rec.append(r["data"])
        rec.append(r)
    for d in {d for d in datas_rec if datas_rec.count(d) > 1}:
        erros.append(f"recuperacao.csv: data duplicada {d}")

    provas = []
    for r in ler("provas.csv"):
        ref = r["_linha"]
        r["data"] = dt(r["data"], ref)
        r["dist"] = num(r["distancia_km"], ref, "distancia_km")
        r["chip"] = seg(r["tempo_chip"], ref, "tempo_chip")
        if r["corrida_id"] and r["corrida_id"] not in idset:
            erros.append(f"{ref}: corrida_id '{r['corrida_id']}' não existe em corridas.csv")
        provas.append(r)

    return corridas, tiros, series, rec, provas


def secao_provas(provas):
    out = ["## Provas e recordes", ""]
    validas = [p for p in provas if p["data"] and p["dist"] and p["chip"]]
    if not validas:
        return out + ["Sem provas registradas.", ""]
    prs = {}
    for p in validas:
        if p["dist"] not in prs or p["chip"] < prs[p["dist"]]["chip"]:
            prs[p["dist"]] = p
    for d, p in sorted(prs.items()):
        out.append(f"- **PR {fnum(d, 1)} km: {fdur(p['chip'])}** ({fpace(p['chip'] / d)}) — {p['nome']}, {p['data']:%d/%m/%Y}")
    if 10 in prs and 5 not in prs:
        eq = prs[10]["chip"] * (5 / 10) ** 1.06
        out.append(f"- Equivalente 5K do PR de 10K (Riegel): ~{fdur(eq)} ({fpace(eq / 5)})")
    out += ["", "| data | prova | km | chip | pace | oficial | lugar geral / escalão |", "|---|---|---|---|---|---|---|"]
    for p in sorted(validas, key=lambda p: p["data"], reverse=True):
        lug = f"{p['lugar_geral'] or '–'} / {p['lugar_escalao'] or '–'}"
        out.append(f"| {p['data']:%d/%m/%Y} | {p['nome']} | {fnum(p['dist'], 1)} | {fdur(p['chip'])} | "
                   f"{fpace(p['chip'] / p['dist'])} | {p['tempo_oficial'] or '–'} | {lug} |")
    return out + [""]


# ---------- seções ----------
def secao_timeline(hoje, corridas, series, rec):
    inicio = hoje - timedelta(days=DIAS_TIMELINE - 1)
    por_dia = defaultdict(list)
    for c in corridas:
        if c["data"] and inicio <= c["data"] <= hoje:
            p = f", {fpace(c['pace'])}" if c["pace"] else ""
            fc = f", FC {fnum(c['fc_media'], 0)}" if c["fc_media"] else ""
            if c["km"]:
                qt = f"{fnum(c['km'], 2)} km"
            elif c["seg"]:
                qt = f"{fdur(c['seg'])} (sem distância)"
            else:
                qt = "(sem distância/tempo)"
            por_dia[c["data"]].append(f"🏃 {c['tipo']} {qt}{p}{fc}")
    sess = defaultdict(lambda: {"series": 0, "ex": set()})
    for s in series:
        if s["data"] and inicio <= s["data"] <= hoje and s["tipo_serie"] != "aquecimento":
            k = (s["data"], s["treino"])
            sess[k]["series"] += 1
            sess[k]["ex"].add(s["exercicio"])
    for (d, t), v in sess.items():
        por_dia[d].append(f"🏋️ treino {t} ({v['series']} séries, {len(v['ex'])} exercícios)")
    rmap = {r["data"]: r for r in rec}

    out = ["## Últimos 14 dias", "", "| dia | atividades | recup. · esforço · sono (Bevel) · HRV · passos |", "|---|---|---|"]
    d = hoje
    while d >= inicio:
        ativ = "; ".join(por_dia.get(d, [])) or "descanso / sem registro"
        r = rmap.get(d)
        rv = "–"
        if r:
            partes = [f"{fnum(r[c], 0)}%" if r[c] is not None else "–" for c in ("recuperacao_pct", "esforco_pct", "sono_pct")]
            if r["hrv_ms"]:
                partes.append(f"{fnum(r['hrv_ms'], 0)} ms")
            if r["passos"]:
                partes.append(f"{r['passos'] / 1000:.1f}k passos")
            rv = " · ".join(partes)
        marca = " (hoje)" if d == hoje else ""
        out.append(f"| {dia_label(d)}{marca} | {ativ} | {rv} |")
        d -= timedelta(days=1)
    return out


def volume_semanal(hoje, corridas, series):
    semanas = [seg_semana(hoje) - timedelta(weeks=i) for i in range(SEMANAS_VOLUME)]
    v = {s: {"km": 0.0, "km_facil": 0.0, "corridas": 0, "sessoes": set(), "series": 0, "ton": 0.0,
             "z_facil": 0.0, "z_total": 0.0}
         for s in semanas}
    for c in corridas:
        if c["data"] and seg_semana(c["data"]) in v:
            x = v[seg_semana(c["data"])]
            x["km"] += c["km"] or 0
            x["corridas"] += 1
            if c["tipo"] not in DUROS:
                x["km_facil"] += c["km"] or 0
            if c["zs"]:
                zs = [z or 0 for z in c["zs"]]
                x["z_facil"] += zs[0] + zs[1]
                x["z_total"] += sum(zs)
    for s in series:
        if s["data"] and seg_semana(s["data"]) in v and s["tipo_serie"] != "aquecimento":
            x = v[seg_semana(s["data"])]
            x["sessoes"].add((s["data"], s["treino"]))
            x["series"] += 1
            x["ton"] += (s["carga"] or 0) * (s["reps"] or 0)
    return semanas, v


def secao_volume(hoje, semanas, v):
    out = ["## Volume semanal", "",
           "| semana (seg) | km | corridas | % tempo Z1–2 (FC) | sessões academia | séries | tonelagem (kg) |",
           "|---|---|---|---|---|---|---|"]
    for s in semanas:
        x = v[s]
        pf = f"{100 * x['z_facil'] / x['z_total']:.0f}%" if x["z_total"] else "–"
        atual = " (atual)" if s == seg_semana(hoje) else ""
        out.append(f"| {s:%d/%m}{atual} | {fnum(x['km'], 1) if x['km'] else '0'} | {x['corridas']} | {pf} | "
                   f"{len(x['sessoes'])} | {x['series']} | {x['ton']:.0f} |")
    return out


def secao_corridas(corridas):
    ult = sorted([c for c in corridas if c["data"]], key=lambda c: (c["data"], c.get("inicio", ""), c["id"]))[-6:]
    out = ["## Corridas recentes", ""]
    if not ult:
        return out + ["Sem corridas registradas.", ""]
    out += ["| data | tipo | local | km | tempo | pace | FC méd/máx | zonas Z1-2 · Z3 · Z4-5 | RPE | notas |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for c in reversed(ult):
        out.append(f"| {dia_label(c['data'])} | {c['tipo']} | {c['local'] or '–'} | {fnum(c['km'], 2)} | "
                   f"{fdur(c['seg']) if c['seg'] else '–'} | {fpace(c['pace']) if c['pace'] else '–'} | "
                   f"{fnum(c['fc_media'], 0)}/{fnum(c['fc_max'], 0)} | {fzonas(c['zs'])} | {fnum(c['rpe'], 0)} | {c['notas'] or ''} |")
    return out + [""]


def secao_tiros(corridas, tiros):
    inter = sorted([c for c in corridas if c["tipo"] == "intervalado" and c["data"]],
                   key=lambda c: (c["data"], c["id"]))
    out = ["## Intervalados — tiros", ""]
    if not inter:
        return out + ["Sem intervalados registrados.", ""]
    for c in inter[-2:][::-1]:
        ts = sorted([t for t in tiros if t["corrida_id"] == c["id"]], key=lambda t: t["n"])
        out.append(f"**{dia_label(c['data'])}** ({c['id']}) — {c['notas'] or ''}")
        if not ts:
            out += ["", "_tiros não detalhados_", ""]
            continue
        out += ["", "| # | vel. km/h | pace | duração/dist. | recup. | FC pico | FC fim rec. |",
                "|---|---|---|---|---|---|---|"]
        for t in ts:
            p = fpace(3600 / t["vel"]) if t["vel"] else "–"
            dd = " / ".join(x for x in [fdur(t["seg"]) if t["seg"] else "", f"{fnum(t['dist'], 0)} m" if t["dist"] else ""] if x) or "–"
            out.append(f"| {t['n']} | {fnum(t['vel'], 2)} | {p} | {dd} | {fdur(t['rec']) if t['rec'] else '–'} | "
                       f"{fnum(t['fc_pico'], 0)} | {fnum(t['fc_fim_rec'], 0)} |")
        out.append("")
    return out


def secao_academia(hoje, series):
    out = ["## Academia — cargas por exercício", ""]
    validas = [s for s in series if s["data"] and s["tipo_serie"] != "aquecimento"]
    if not validas:
        return out + ["Sem séries registradas.", ""]
    por_ex = defaultdict(lambda: defaultdict(list))
    for s in validas:
        por_ex[s["exercicio"]][s["data"]].append(s)

    def top(ss):  # melhor série: maior carga, desempate por reps
        return max(ss, key=lambda s: ((s["carga"] or 0), (s["reps"] or 0)))

    def txt(s):
        return f"{fnum(s['carga'], 1)} kg × {fnum(s['reps'], 0)}" if s["carga"] else f"PC × {fnum(s['reps'], 0)}"

    linhas = []
    for ex, dias in por_ex.items():
        ds = sorted(dias)
        u = top(dias[ds[-1]])
        grupo = u["grupo"] or "?"
        seta, ant = "", "–"
        if len(ds) > 1:
            a = top(dias[ds[-2]])
            ant = txt(a)
            ku, ka = ((u["carga"] or 0), (u["reps"] or 0)), ((a["carga"] or 0), (a["reps"] or 0))
            seta = "↑" if ku > ka else ("↓" if ku < ka else "→")
        linhas.append((u["treino"], grupo, ex, ds[-1], txt(u), len(dias[ds[-1]]), ant, seta))
    out += ["| treino | grupo | exercício | última | melhor série | séries | anterior | |",
            "|---|---|---|---|---|---|---|---|"]
    for t, g, ex, d, m, n, a, st in sorted(linhas):
        out.append(f"| {t} | {g} | {ex} | {d:%d/%m} | {m} | {n} | {a} | {st} |")

    ini = hoje - timedelta(days=6)
    por_grupo = defaultdict(int)
    for s in validas:
        if ini <= s["data"] <= hoje:
            por_grupo[s["grupo"] or "?"] += 1
    if por_grupo:
        out += ["", "Séries por grupo muscular (últimos 7 dias): "
                + ", ".join(f"{g} {n}" for g, n in sorted(por_grupo.items(), key=lambda x: -x[1]))]
    return out + [""]


def stats_rec(rec, hoje):
    """Média dos últimos 7 dias vs. linha de base dos 28 dias ANTERIORES a essa janela."""
    def media(campo, ini, fim):
        vals = [r[campo] for r in rec if r["data"] and ini <= r["data"] <= fim and r[campo] is not None]
        return (statistics.mean(vals), len(vals)) if vals else (None, 0)
    i7 = hoje - timedelta(days=6)
    fim_base = i7 - timedelta(days=1)
    i_base = fim_base - timedelta(days=27)
    return {c: (media(c, i7, hoje), media(c, i_base, fim_base))
            for c in ("recuperacao_pct", "esforco_pct", "sono_pct", "hrv_ms", "fc_repouso", "sono_h",
                  "sono_profundo_h", "sono_rem_h", "passos", "kcal_ativas", "kcal_repouso")}


def secao_recuperacao(rec, st):
    out = ["## Recuperação", ""]
    if not rec:
        return out + ["Sem dados de recuperação registrados.", ""]
    nomes = {"recuperacao_pct": "recuperação Bevel (%)", "esforco_pct": "esforço Bevel (%)", "sono_pct": "sono Bevel (%)",
             "hrv_ms": "HRV noite (ms)", "fc_repouso": "FC repouso", "sono_h": "sono (h)",
             "sono_profundo_h": "sono profundo (h)", "sono_rem_h": "sono REM (h)", "passos": "passos",
             "kcal_ativas": "kcal ativas", "kcal_repouso": "kcal em repouso"}
    out += ["| métrica | média 7d | base (28d anteriores) | dias com dado (7d/base) |", "|---|---|---|---|"]
    for c, n in nomes.items():
        (m7, n7), (m28, n28) = st[c]
        casas = 0 if (m7 or 0) >= 100 else 1
        out.append(f"| {n} | {fnum(m7, casas)} | {fnum(m28, casas)} | {n7}/{n28} |")
    return out + [""]


def alertas(hoje, corridas, tiros, series, rec, st, semanas, vol):
    a = []
    datas = [x["data"] for x in corridas + series + rec if x["data"]]
    if not datas:
        return ["Base vazia — nenhum treino registrado ainda."]
    ult = max(datas)
    if (hoje - ult).days >= 3:
        a.append(f"Último registro em {ult:%d/%m} ({(hoje - ult).days} dias) — pode haver treinos não registrados.")

    ini = hoje - timedelta(days=DIAS_TIMELINE - 1)
    cmap = {c["id"]: c for c in corridas}
    for t in tiros:
        c = cmap.get(t["corrida_id"])
        if c and c["data"] and c["data"] >= ini and t["fc_pico"] and t["fc_pico"] >= FC_TIRO_ALERTA:
            a.append(f"Tiro {t['n']} de {c['data']:%d/%m} com FC pico {t['fc_pico']:.0f} (≥ {FC_TIRO_ALERTA}) — conferir se era a intenção da fase.")

    duros = sorted({c["data"] for c in corridas if c["data"] and c["tipo"] in DUROS and c["data"] >= ini})
    for d1, d2 in zip(duros, duros[1:]):
        if (d2 - d1).days == 1:
            a.append(f"Dois dias duros seguidos: {d1:%d/%m} e {d2:%d/%m}.")

    (h7, n7), (h28, n28) = st["hrv_ms"]
    if h7 and h28 and n7 >= 3 and n28 >= 7 and h7 < h28 * (1 - QUEDA_HRV_ALERTA):
        a.append(f"HRV 7d ({h7:.0f} ms) mais de {QUEDA_HRV_ALERTA:.0%} abaixo da base ({h28:.0f} ms) — considerar aliviar.")
    for r in sorted(rec, key=lambda r: r["data"] or date.min)[-2:]:
        if r["data"] and (hoje - r["data"]).days <= 1 and r["recuperacao_pct"] is not None \
                and r["recuperacao_pct"] < RECUP_BAIXA:
            a.append(f"Recuperação Bevel baixa em {r['data']:%d/%m}: {r['recuperacao_pct']:.0f}% (< {RECUP_BAIXA}%).")
    (r7, rn7), (r28, rn28) = st["fc_repouso"]
    if r7 and r28 and rn7 >= 3 and rn28 >= 7 and r7 >= r28 + 3:
        a.append(f"FC de repouso 7d ({r7:.0f}) ≥ 3 bpm acima da base ({r28:.0f}).")

    s_ant, s_ant2 = semanas[1], semanas[2]
    k1, k2 = vol[s_ant]["km"], vol[s_ant2]["km"]
    if k2 and k1 > k2 * 1.15:
        a.append(f"Semana de {s_ant:%d/%m}: {k1:.1f} km, +{(k1 / k2 - 1):.0%} sobre a anterior ({k2:.1f} km).")
    k = vol[s_ant]
    if k["z_total"] and k["z_facil"] / k["z_total"] < 0.7:
        a.append(f"Semana de {s_ant:%d/%m}: só {k['z_facil'] / k['z_total']:.0%} do tempo de corrida em Z1–2 (alvo ~80%).")
    elif not k["z_total"] and k["km"] and k["km_facil"] / k["km"] < 0.7:
        a.append(f"Semana de {s_ant:%d/%m}: só {k['km_facil'] / k['km']:.0%} do km em treinos fáceis (alvo ~80%; sem dados de zona).")
    return a


# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hoje", help="data de referência AAAA-MM-DD (padrão: hoje)")
    args = ap.parse_args()
    hoje = datetime.strptime(args.hoje, "%Y-%m-%d").date() if args.hoje else date.today()

    corridas, tiros, series, rec, provas = carregar()
    if erros:
        print("ERROS DE DADOS — estado_atual.md não foi gerado:", file=sys.stderr)
        for e in erros:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    semana_bloco = (hoje - INICIO_BLOCO).days // 7 + 1
    st = stats_rec(rec, hoje)
    semanas, vol = volume_semanal(hoje, corridas, series)
    al = alertas(hoje, corridas, tiros, series, rec, st, semanas, vol)

    doc = [
        "# Estado atual — fitness_log",
        "",
        f"> Gerado automaticamente por `scripts/gerar_estado.py` em {datetime.now():%Y-%m-%d %H:%M}. "
        "Não editar à mão. O plano está em `plano.md`.",
        "",
        f"**Hoje:** {dia_label(hoje)}/{hoje:%Y} · **Bloco 5K:** semana {semana_bloco} de {SEMANAS_BLOCO} "
        f"(início {INICIO_BLOCO:%d/%m/%Y}) · **FC máx:** {FC_MAX}",
        "",
        "## Alertas",
        "",
    ]
    doc += [f"- {x}" for x in al] or ["- Nenhum."]
    doc += [""]
    doc += secao_timeline(hoje, corridas, series, rec) + [""]
    doc += secao_volume(hoje, semanas, vol) + [""]
    doc += secao_provas(provas)
    doc += secao_corridas(corridas)
    doc += secao_tiros(corridas, tiros)
    doc += secao_academia(hoje, series)
    doc += secao_recuperacao(rec, st)
    if avisos:
        doc += ["## Pendências de dados", ""] + [f"- {x}" for x in sorted(set(avisos))] + [""]

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(doc), encoding="utf-8")
    print(f"ok: {OUT.relative_to(ROOT)} — {len(corridas)} corridas, {len(tiros)} tiros, "
          f"{len(series)} séries, {len(rec)} dias de recuperação")
    for x in sorted(set(avisos)):
        print(f"aviso: {x}")


if __name__ == "__main__":
    main()
