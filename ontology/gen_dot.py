import sys, html
sys.path.insert(0, sys.argv[1])
from spec import *

COL = {  # riempimento, bordo/testo
    "1": ("#E1F5EE", "#0F6E56"), "2": ("#FAEEDA", "#854F0B"), "3": ("#EEEDFE", "#534AB7"),
    "4": ("#FAECE7", "#993C1D"), "D": ("#F1EFE8", "#5F5E5A"),
}
NOMI_FONTE = {"1": "Dataset 1", "2": "Dataset 2", "3": "Dataset 3", "4": "Dataset 4", "D": "Derivata / regola"}
dettaglio = sys.argv[2] == "full"

def domini(nome, base):
    return DOMINI_MULTIPLI.get(nome, [base])

righe_dati = {c[0]: [] for c in CLASSI}
for nome, dom, tipo, fonte, orig, comm in DATI:
    for d in domini(nome, dom):
        righe_dati[d].append((nome, tipo, fonte))
righe_dati["Person"] += [("schema:givenName", "string", "1"), ("schema:familyName", "string", "1"),
                         ("schema:birthDate", "date", "1")]

L = []
w = L.append
w('digraph ontologia {')
w('  graph [rankdir=LR, fontname="Helvetica", nodesep=0.35, ranksep=0.9, pad=0.3, splines=true, newrank=true];')
w('  node [shape=plain, fontname="Helvetica", fontsize=11];')
w('  edge [fontname="Helvetica", fontsize=9, arrowsize=0.7];')

gruppi = {"struttura": "Struttura del torneo", "squadre": "Squadre e partecipazioni",
          "persone": "Persone e convocazioni", "eventi": "Eventi di partita", "esterni": "Entità dalle fonti Kaggle"}
for g, titolo in gruppi.items():
    w(f'  subgraph cluster_{g} {{ label="{titolo}"; fontsize=12; fontcolor="#444441"; style="rounded,dashed"; color="#B4B2A9";')
    for nome, sup, fonte, gruppo, it, comm, uri in CLASSI:
        if gruppo != g:
            continue
        fill, line = COL[fonte]
        ext = ", ".join(s for s in sup if not s.startswith("wc:"))
        t = [f'<table border="1" cellborder="0" cellspacing="0" cellpadding="4" color="{line}" bgcolor="{fill}">',
             f'<tr><td><font color="{line}" point-size="13"><b>{nome}</b></font></td></tr>']
        if ext:
            t.append(f'<tr><td><font color="#5F5E5A" point-size="9"><i>⊑ {html.escape(ext)}</i></font></td></tr>')
        if dettaglio and righe_dati[nome]:
            t.append('<tr><td cellpadding="0"><table border="0" cellborder="0" cellspacing="0" cellpadding="1" bgcolor="white">')
            for pn, tp, fo in righe_dati[nome]:
                c = COL[fo][1]
                t.append(f'<tr><td align="left"><font color="{c}" point-size="9">{html.escape(pn)} : {tp}</font></td></tr>')
            t.append('</table></td></tr>')
        t.append('</table>')
        w(f'    {nome} [label=<{"".join(t)}>];')
    w('  }')

for nome, sup, fonte, gruppo, it, comm, uri in CLASSI:
    for s in sup:
        if s.startswith("wc:"):
            w(f'  {nome} -> {s[3:]} [style=dashed, arrowhead=onormal, color="#888780", label=<<font color="#888780">subClassOf</font>>];')

for nome, dom, rng, fonte, orig, comm in OGGETTO:
    c = COL[fonte][1]
    for d in domini(nome, dom):
        w(f'  {d} -> {rng} [color="{c}", label=<<font color="{c}">{nome}</font>>];')

leg = ['<table border="0" cellborder="1" cellspacing="0" cellpadding="4">',
       '<tr><td colspan="2"><b>Fonte</b></td></tr>']
for k in ["1", "2", "3", "4", "D"]:
    leg.append(f'<tr><td bgcolor="{COL[k][0]}" width="18"> </td><td align="left"><font color="{COL[k][1]}">{NOMI_FONTE[k]}</font></td></tr>')
leg.append('</table>')
w(f'  legenda [label=<{"".join(leg)}>];')
w('}')
open(sys.argv[3], "w", encoding="utf-8").write("\n".join(L))
