"""App di dimostrazione del retrieval sul knowledge graph dei Mondiali (meccanismo A: ricerca guidata; meccanismo B: domanda libera).

Avvio, dalla cartella del progetto e con il .venv attivo:
    streamlit run app/app.py
Si apre nel browser (http://localhost:8501). Serve Neo4j avviato con il grafo e gli indici creati dai notebook 02–05.

Struttura:
- barra laterale: connessione a Neo4j, scelta del meccanismo e del tipo di domanda;
- A, ricerca guidata: il modulo del tipo scelto (campi con suggerimenti) e la risposta (scheda, tabella,
  grafico, immagini);
- B, domanda libera: Gemini scrive la query Cypher (llm.py); si mostrano la query, i nomi e i testi cercati
  e i risultati (tabella, immagini, scheda del giocatore). La chiave API si legge da GEMINI_API_KEY o si
  scrive nella barra laterale (resta solo nella sessione);
- C, query Cypher: l'utente scrive una query, che gira in sola lettura e con un tempo massimo;
- riquadro "Come ho trovato la risposta": tutte le query Cypher eseguite, una clausola per riga, con i parametri.
Tutta la logica sta in src/wc_retrieval (modelli Cypher, ricerca per nome, vettoriale e per immagini):
l'app si limita a raccogliere i parametri e a mostrare i risultati (B riusa gli stessi modelli).

Streamlit riesegue lo script dall'inizio a ogni interazione: le risposte si ricalcolano dai valori dei campi
(le query durano millisecondi), mentre connessione e modelli si tengono in memoria.
"""
import os
import re
import sys
import textwrap
import time
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
from wc_retrieval import embedding as emb                  # noqa: E402
from wc_retrieval import llm, modelli, ricerca             # noqa: E402
from wc_retrieval.grafo import BASE, Grafo                 # noqa: E402

DIR4 = ROOT / "data" / "raw" / "dataset_4" / "Images" / "Images"     # immagini dei giocatori (filePath)

TIPI = {
    "S1": "Scheda giocatore",
    "S2": "Una nazionale in un Mondiale",
    "S3": "Partite e scheda partita",
    "S4": "Scheda torneo",
    "C1": "Classifica dei giocatori",
    "F1": "Testa a testa tra nazionali",
    "R1": "Descrivi chi o cosa cerchi",
    "R2": "Cerca immagini a parole",
}
METRICHE = {
    "gol": "Gol", "gol_su_rigore": "Gol su rigore", "presenze": "Presenze",
    "presenze_da_titolare": "Presenze da titolare", "gialli": "Cartellini gialli",
    "espulsioni": "Espulsioni", "premi": "Premi individuali", "mondiali": "Mondiali giocati",
}
GENERI = {"men": "maschile", "women": "femminile"}
CLASSI = {"Player": "giocatore", "Participation": "nazionale in un Mondiale", "Match": "partita",
          "Federation": "federazione", "Club": "club", "Stadium": "stadio"}
TUTTI = "tutti"

st.set_page_config(page_title="Mondiali — retrieval su knowledge graph", page_icon="⚽", layout="wide")


# =====================================================================================================
# Risorse tenute in memoria: connessione (per sessione) e modelli (per tutta l'app)
# =====================================================================================================
def connetti(password):
    """Apre la connessione e la salva nella sessione; la password non si scrive da nessuna parte."""
    try:
        st.session_state["grafo"] = Grafo(password)
        st.session_state.pop("errore_connessione", None)
    except Exception as e:                                  # password errata, Neo4j spento…
        st.session_state["errore_connessione"] = f"{type(e).__name__}: {e}"


@st.cache_resource(show_spinner="Carico il modello di frasi (la prima volta qualche secondo)…")
def modello_testo():
    return emb.carica_modello_testo()


@st.cache_resource(show_spinner="Carico CLIP (la prima volta anche qualche minuto)…")
def modello_clip():
    return emb.carica_clip()


def tornei(g):
    """Anni dei Mondiali per genere e nomi delle fasi: letti una volta per sessione."""
    if "tornei" not in st.session_state:
        t = g.leggi("MATCH (t:Tournament) RETURN t.year AS anno, t.gender AS genere ORDER BY anno")
        f = g.leggi("MATCH (s:Stage) RETURN DISTINCT s.stageName AS fase ORDER BY fase")
        st.session_state["tornei"] = (t, f["fase"].tolist())
    return st.session_state["tornei"]


# =====================================================================================================
# Pezzi di interfaccia riusati dai moduli
# =====================================================================================================
def scegli_entita(g, classe, etichetta, chiave, esempio=""):
    """Campo di testo + elenco dei nodi trovati dal full-text (con errori di battitura tollerati).

    Restituisce l'URI scelto, oppure None se il campo è vuoto o non si trova nulla.
    """
    testo = st.text_input(etichetta, value=esempio, key=f"{chiave}_testo",
                          help="Si può scrivere anche solo una parte del nome, con errori di battitura")
    if not testo.strip():
        return None
    trovati = ricerca.cerca_nome(g, classe, testo, k=10)
    if trovati.empty:
        st.warning(f"Nessun risultato per «{testo}».")
        return None

    def voce(i):
        r = trovati.iloc[i]
        dettaglio = ", ".join(str(x) for x in (r["dettaglio"] or []) if x)
        return r["nome"] + (f" — {dettaglio}" if dettaglio else "")

    i = st.selectbox(f"{etichetta}: scegli", range(len(trovati)), format_func=voce, key=f"{chiave}_scelta")
    return trovati["uri"].iloc[i]


def scegli_anno(g, genere, chiave, facoltativo=False, predefinito=None):
    anni = tornei(g)[0]
    anni = anni.loc[anni["genere"] == genere, "anno"].tolist() if genere else sorted(set(anni["anno"]))
    opzioni = ([TUTTI] if facoltativo else []) + [int(a) for a in reversed(anni)]
    indice = opzioni.index(predefinito) if predefinito in opzioni else 0
    scelta = st.selectbox("Mondiale", opzioni, index=indice, key=chiave)
    return None if scelta == TUTTI else int(scelta)


def scegli_genere(chiave, facoltativo=False):
    opzioni = ([TUTTI] if facoltativo else []) + list(GENERI)
    scelta = st.radio("Genere", opzioni, horizontal=True, key=chiave,
                      format_func=lambda x: GENERI.get(x, "entrambi"))
    return None if scelta == TUTTI else scelta


def tabella(df, **rinomina):
    """DataFrame leggibile: liste come testo separato da virgole, valori mancanti vuoti."""
    df = df.copy()
    for c in df.columns:
        if df[c].map(lambda x: isinstance(x, (list, tuple))).any():
            df[c] = df[c].map(lambda x: ", ".join(map(str, x)) if isinstance(x, (list, tuple)) else x)
    st.dataframe(df.rename(columns=rinomina), hide_index=True)


def immagine(percorso, larghezza, didascalia=None):
    """Mostra un'immagine dal disco (percorso relativo alla cartella delle immagini)."""
    file = DIR4 / percorso if percorso else None
    if file is not None and file.is_file():
        st.image(str(file), width=larghezza, caption=didascalia)
    else:
        st.caption("(immagine non disponibile)")


def numero(x):
    """Intero da mostrare, oppure '–' se il dato non c'è."""
    return "–" if x is None or pd.isna(x) else int(x)


# =====================================================================================================
# Risposte: una funzione per tipo di scheda (riusate anche da R1 e dal meccanismo B)
# =====================================================================================================
def mostra_giocatore(g, uri):
    s = modelli.scheda_giocatore(g, uri)
    a, t = s["anagrafica"], s["totali"]
    sinistra, destra = st.columns([1, 3])
    with sinistra:
        if s["immagine"] and s["immagine"]["percorso"]:
            conf = s["immagine"]["confidenza"]
            immagine(s["immagine"]["percorso"], 240,
                     f"{s['immagine']['immagini']} immagini; scelta con CLIP (labelConfidence {conf:.3f})"
                     if conf is not None else None)
        else:
            st.caption("Nessuna immagine (le immagini riguardano i convocati del 2022)")
    with destra:
        st.subheader(a["nome"])
        nascita = a["nascita"].strftime("%d/%m/%Y") if a["nascita"] is not None and not pd.isna(a["nascita"]) else "–"
        st.write(f"Nato/a il {nascita}" + (f" · [DBpedia]({a['dbpedia']})" if a["dbpedia"] else ""))
        c = st.columns(6)
        c[0].metric("Mondiali", t["mondiali"])
        c[1].metric("Presenze", t["presenze"])
        c[2].metric("Da titolare", t["titolare"])
        c[3].metric("Gol", t["gol"], help=f"di cui {t['gol_su_rigore']} su rigore; autogol: {t['autogol']}")
        c[4].metric("Gialli / espulsioni", f"{t['gialli']} / {t['espulsioni']}")
        c[5].metric("Premi", t["premi"])
        st.caption("Presenze e cartellini esistono nel dataset 1 dal 1970 (non per il Mondiale femminile 1999): "
                   "dove mancano la cella è vuota, non zero.")
    st.markdown("**Mondiali giocati**")
    tabella(s["mondiali"], anno="Anno", squadra="Squadra", maglia="Maglia", ruolo="Ruolo", presenze="Presenze",
            titolare="Titolare", gol="Gol", gol_su_rigore="Su rigore", autogol="Autogol", gialli="Gialli",
            espulsioni="Espulsioni", premi="Premi", capitano="Capitano", club="Club", scarpe="Scarpe",
            risultato_squadra="Risultato della squadra")
    if s["statistiche_2022"]:
        st.markdown("**Statistiche del Mondiale 2022** (dataset 3)")
        tabella(pd.DataFrame([s["statistiche_2022"]]).dropna(axis=1, how="all"))


def mostra_partecipazione(g, federazione_uri, anno, genere):
    s = modelli.scheda_partecipazione(g, federazione_uri, anno, genere)
    if s is None:
        st.info("Questa nazionale non ha partecipato a quel Mondiale.")
        return
    i = s["info"]
    st.subheader(i["partecipazione"])
    c = st.columns(4)
    c[0].metric("Risultato", i["risultato"])
    c[1].metric("Posizione finale", numero(i["classifica_finale"]), help="classifica completa (dataset 2)")
    c[2].metric("Allenatore", ", ".join(i["allenatori"]) or "–")
    c[3].metric("Ranking FIFA", numero(i["ranking_fifa"]), help="solo 2022 (dataset 3)")
    extra = []
    if i["ospitante"]:
        extra.append("paese ospitante")
    if i["sponsor_tecnico"]:
        extra.append(f"sponsor tecnico {i['sponsor_tecnico']}")
    if extra:
        st.caption(" · ".join(extra))
    st.markdown("**Partite**")
    tabella(s["partite"].drop(columns="uri"), data="Data", fase="Fase", girone="Girone", casa="Casa",
            gol_casa="Gol casa", gol_trasferta="Gol trasferta", trasferta="Trasferta",
            supplementari="Supplementari", rigori_casa="Rigori casa", rigori_trasferta="Rigori trasferta")
    sinistra, destra = st.columns(2)
    with sinistra:
        st.markdown("**Girone**")
        tabella(s["gironi"])
    with destra:
        st.markdown("**Marcatori**")
        tabella(s["marcatori"])
    st.markdown("**Rosa**")
    tabella(s["rosa"].drop(columns="uri"))


def mostra_partita(g, uri):
    p = modelli.scheda_partita(g, uri)
    i = p["info"]
    st.subheader(f"{i['casa']} {i['gol_casa']}–{i['gol_trasferta']} {i['trasferta']}")
    dettagli = [f"{i['torneo']}, {i['fase']}" + (f" ({i['girone']})" if i["girone"] else ""), str(i["data"])]
    if i["supplementari"]:
        dettagli.append("dopo i supplementari")
    if i["serie_di_rigori"]:
        dettagli.append(f"rigori {numero(i['rigori_casa'])}–{numero(i['rigori_trasferta'])}")
    if i["stadio"]:
        dettagli.append(f"{i['stadio']}, {i['citta']}")
    if i["arbitro"]:
        dettagli.append(f"arbitro {i['arbitro']}")
    st.write(" · ".join(dettagli))
    sinistra, destra = st.columns(2)
    with sinistra:
        st.markdown("**Gol**")
        tabella(p["gol"])
        if len(p["rigori"]):
            st.markdown("**Serie di rigori**")
            tabella(p["rigori"])
    with destra:
        st.markdown("**Cartellini**")
        tabella(p["cartellini"])
        st.markdown("**Sostituzioni**")
        tabella(p["sostituzioni"])


def mostra_torneo(g, anno, genere):
    s = modelli.scheda_torneo(g, anno, genere)
    if s is None:
        st.info("Nessun Mondiale per questo anno e genere.")
        return
    i = s["info"]
    st.subheader(i["torneo"])
    c = st.columns(5)
    c[0].metric("Ospitante", ", ".join(i["ospitanti"]))
    c[1].metric("Squadre", i["squadre"])
    c[2].metric("Partite", i["partite"])
    c[3].metric("Gol", i["gol"])
    c[4].metric("Media gol a partita", i["media_gol"])
    st.caption(f"dal {i['inizio']} al {i['fine']}")
    sinistra, centro, destra = st.columns(3)
    with sinistra:
        st.markdown("**Podio**")
        tabella(s["podio"])
    with centro:
        st.markdown("**Marcatori**")
        tabella(s["marcatori"])
    with destra:
        st.markdown("**Premi**")
        tabella(s["premi"])


def mostra_nodo(g, uri, classe):
    """Apre la scheda di un nodo trovato dalla ricerca vettoriale (R1): la ricerca trova, il grafo risponde."""
    if classe == "Player":
        mostra_giocatore(g, uri)
    elif classe == "Match":
        mostra_partita(g, uri)
    elif classe == "Participation":
        r = g.leggi("""
            MATCH (pa:Participation {uri: $uri})-[:team]->(n:NationalTeam)-[:representsFederation]->(f:Federation),
                  (pa)-[:tournament]->(t:Tournament)
            RETURN f.uri AS federazione, t.year AS anno, t.gender AS genere""", uri=uri).iloc[0]
        mostra_partecipazione(g, r["federazione"], int(r["anno"]), r["genere"])
    else:
        st.info("La scheda di questa classe arriverà con i tipi P2 (S5 storia di una nazionale, S6 club, "
                "S7 stadio); qui sopra c'è la sua descrizione.")


# =====================================================================================================
# Moduli della ricerca guidata (A): uno per tipo di domanda
# =====================================================================================================
def modulo_s1(g):
    uri = scegli_entita(g, "Player", "Giocatore o giocatrice", "s1", "Lionel Messi")
    if uri:
        mostra_giocatore(g, uri)


def modulo_s2(g):
    c = st.columns(3)
    with c[0]:
        fed = scegli_entita(g, "Federation", "Nazionale", "s2", "Italy")
    with c[1]:
        genere = scegli_genere("s2_genere")
    with c[2]:
        anno = scegli_anno(g, genere, "s2_anno", predefinito=2006)
    if fed:
        mostra_partecipazione(g, fed, anno, genere)


def modulo_s3(g):
    c = st.columns(2)
    with c[0]:
        fed = scegli_entita(g, "Federation", "Nazionale", "s3", "Argentina")
    with c[1]:
        avv = scegli_entita(g, "Federation", "Avversario (facoltativo)", "s3_avv", "France")
    c = st.columns(3)
    with c[0]:
        genere = scegli_genere("s3_genere", facoltativo=True)
    with c[1]:
        anno = scegli_anno(g, genere, "s3_anno", facoltativo=True)
    with c[2]:
        fase = st.selectbox("Fase", [TUTTI] + tornei(g)[1], key="s3_fase")
    if not fed:
        return
    partite = modelli.cerca_partite(g, fed, avv, anno=anno, fase=None if fase == TUTTI else fase, genere=genere)
    st.markdown(f"**{len(partite)} partite trovate**")
    if partite.empty:
        return
    tabella(partite.drop(columns=["uri", "federazione_casa"]))
    voci = [f"{r.anno} · {r.fase} · {r.casa} {r.gol_casa}–{r.gol_trasferta} {r.trasferta}" for r in partite.itertuples()]
    i = st.selectbox("Apri la scheda della partita", range(len(partite)), index=len(partite) - 1,
                     format_func=lambda k: voci[k], key="s3_partita")
    mostra_partita(g, partite["uri"].iloc[i])


def modulo_s4(g):
    c = st.columns(2)
    with c[0]:
        genere = scegli_genere("s4_genere")
    with c[1]:
        anno = scegli_anno(g, genere, "s4_anno")
    mostra_torneo(g, anno, genere)


def modulo_c1(g):
    c = st.columns(4)
    with c[0]:
        metrica = st.selectbox("Metrica", list(METRICHE), format_func=METRICHE.get, key="c1_metrica")
    with c[1]:
        genere = scegli_genere("c1_genere", facoltativo=True)
    with c[2]:
        anno = scegli_anno(g, genere, "c1_anno", facoltativo=True)
    with c[3]:
        n = st.slider("Quanti", 5, 30, 10, key="c1_n")
    fed = scegli_entita(g, "Federation", "Solo per una nazionale (facoltativo, con i predecessori)", "c1_fed")
    r = modelli.classifica(g, metrica, anno=anno, federazione_uri=fed, genere=genere, n=n)["classifica"]
    if r.empty:
        st.info("Nessun dato per questi filtri (presenze e cartellini esistono dal 1970).")
        return
    r = r.assign(squadre=r["squadre"].map(", ".join))
    grafico = alt.Chart(r).mark_bar().encode(
        x=alt.X("valore:Q", title=METRICHE[metrica]),
        y=alt.Y("giocatore:N", sort="-x", title=None),
        tooltip=["giocatore", "squadre", "valore", "dal", "al"])
    sinistra, destra = st.columns([3, 2])
    with sinistra:
        st.altair_chart(grafico)
    with destra:
        tabella(r.drop(columns="uri"), giocatore="Giocatore", squadre="Squadre", valore=METRICHE[metrica],
                dal="Dal", al="Al")


def modulo_f1(g):
    c = st.columns(3)
    with c[0]:
        a = scegli_entita(g, "Federation", "Nazionale", "f1_a", "Argentina")
    with c[1]:
        b = scegli_entita(g, "Federation", "Avversario", "f1_b", "Germany")
    with c[2]:
        genere = scegli_genere("f1_genere", facoltativo=True)
    if not (a and b):
        return
    r = modelli.testa_a_testa(g, a, b, genere=genere)
    b_ = r["bilancio"]
    c = st.columns(6)
    for col, (nome, chiave) in zip(c, [("Partite", "partite"), ("Vittorie", "vittorie"), ("Pareggi", "pareggi"),
                                       ("Sconfitte", "sconfitte"), ("Gol fatti", "gol_fatti"),
                                       ("Gol subiti", "gol_subiti")]):
        col.metric(nome, b_[chiave])
    st.caption(f"Dal punto di vista della prima nazionale, predecessori compresi (es. Germania Ovest). "
               f"Una partita decisa ai rigori conta come pareggio; serie di rigori vinte "
               f"{b_['serie_di_rigori_vinte']}, perse {b_['serie_di_rigori_perse']}.")
    tabella(r["partite"].drop(columns="uri"))


def modulo_r1(g):
    st.caption("Ricerca semantica: la descrizione passa nel modello di frasi all-MiniLM-L6-v2 e si cercano le "
               "descrizioni dei nodi più vicine (indici vettoriali). Funziona con descrizioni, "
               "non con i nomi: per i nomi usa le altre schede.")
    c = st.columns([3, 1])
    with c[0]:
        testo = st.text_input("Descrizione (in inglese)", "Croatian midfielder who won the Golden Ball in 2018",
                              key="r1_testo")
    with c[1]:
        classe = st.selectbox("Cosa cerchi", [TUTTI] + list(CLASSI), key="r1_classe",
                              format_func=lambda x: "qualsiasi cosa" if x == TUTTI else CLASSI[x])
    if not testo.strip():
        return
    vettore = emb.vettori_testo(modello_testo(), [testo])[0]
    trovati = ricerca.cerca_descrizioni(g, vettore, classi=None if classe == TUTTI else [classe], k=10)
    if trovati.empty:
        st.warning("Nessun risultato: gli indici delle descrizioni ci sono? (notebook 05)")
        return
    st.markdown("**Nodi più vicini** (punteggio = (1 + coseno) / 2; i primi sono spesso molto vicini tra loro)")
    st.dataframe(trovati.assign(classe=trovati["classe"].map(CLASSI))[["nome", "classe", "punteggio", "descrizione"]]
                 .round({"punteggio": 3}), hide_index=True)
    i = st.selectbox("Apri la scheda", range(len(trovati)), key="r1_scelta",
                     format_func=lambda k: f"{trovati['nome'].iloc[k]} ({CLASSI[trovati['classe'].iloc[k]]})")
    mostra_nodo(g, trovati["uri"].iloc[i], trovati["classe"].iloc[i])


def modulo_r2(g):
    st.caption("Ricerca multimediale: il testo passa nella parte testuale di CLIP e si cercano le immagini più "
               "vicine (indice vettoriale image_clip); ogni immagine porta al giocatore raffigurato.")
    c = st.columns([3, 1])
    with c[0]:
        testo = st.text_input("Descrivi l'immagine (in inglese)", "a goalkeeper diving to save the ball",
                              key="r2_testo")
    with c[1]:
        n = st.slider("Quante immagini", 4, 24, 12, step=4, key="r2_n")
    if not testo.strip():
        return
    vettore = emb.vettori_testo(modello_clip(), [testo])[0]
    trovate = ricerca.cerca_immagini(g, vettore, k=n)
    if trovate.empty:
        st.warning("Nessuna immagine: l'indice image_clip c'è? (notebook 04)")
        return
    colonne = st.columns(4)
    for k, r in enumerate(trovate.itertuples()):
        with colonne[k % 4]:
            conf = f" · conf. {r.confidenza:.2f}" if r.confidenza is not None and not pd.isna(r.confidenza) else ""
            immagine(r.percorso, 200, f"{r.giocatore} ({r.punteggio:.3f}{conf})" + (" · duplicata" if r.duplicata else ""))
    giocatori = trovate.drop_duplicates("giocatore_uri")
    i = st.selectbox("Apri la scheda del giocatore", range(len(giocatori)), key="r2_scelta",
                     format_func=lambda k: giocatori["giocatore"].iloc[k])
    if st.toggle("Mostra la scheda", key="r2_scheda"):
        mostra_giocatore(g, giocatori["giocatore_uri"].iloc[i])


MODULI = {"S1": modulo_s1, "S2": modulo_s2, "S3": modulo_s3, "S4": modulo_s4,
          "C1": modulo_c1, "F1": modulo_f1, "R1": modulo_r1, "R2": modulo_r2}


# =====================================================================================================
# Query Cypher leggibili: una clausola per riga, rientro dentro le graffe
# =====================================================================================================
# Testi tra apici (non si toccano) e simboli che contano: parentesi, graffe e parole chiave delle clausole.
# Una clausola non segue mai ".", ":", "$" o una lettera (n.match, :Match, $limit) e non è una chiave (with: 1).
STRINGHE = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`[^`]*`")
SIMBOLI = re.compile(r"[()\[\]{}]|(?<![\w.:$])(?:OPTIONAL MATCH|MATCH|WHERE|WITH|RETURN|ORDER BY|SKIP|LIMIT|UNWIND|CALL|"
                     r"YIELD|UNION ALL|UNION)\b(?!\s*:)", re.IGNORECASE)


def cypher_leggibile(query, larghezza=100):
    """La query da mostrare: com'è scritta se è già su righe brevi, altrimenti una clausola per riga.

    Le query generate da Gemini arrivano spesso su una riga sola. Si va a capo prima di ogni clausola (MATCH,
    WHERE, WITH, RETURN, ...) e si rientra di due spazi per ogni graffa aperta (EXISTS { ... }, CALL { ... }).
    Non si va a capo dentro parentesi tonde e quadre (pattern, liste) né in "STARTS WITH" / "ENDS WITH".
    """
    query = textwrap.dedent(query).strip()
    if all(len(r) <= larghezza for r in query.splitlines()):
        return query
    # pezzi alternati: codice e testi tra apici
    pezzi, fine = [], 0
    for m in STRINGHE.finditer(query):
        pezzi += [(query[fine:m.start()], False), (m.group(), True)]
        fine = m.end()
    pezzi.append((query[fine:], False))
    righe, riga, rientro, tonde = [], "", 0, 0
    aperte = []                                        # una voce per graffa aperta: True se dentro si è andati a capo
    for testo, tra_apici in pezzi:
        if tra_apici:
            riga += testo
            continue
        testo = re.sub(r"\s+", " ", testo)
        pos = 0
        for m in SIMBOLI.finditer(testo):
            riga += testo[pos:m.start()]
            pos, t = m.end(), m.group()
            if t in "([":
                tonde += 1
            elif t in ")]":
                tonde -= 1
            elif t == "{":
                aperte.append(False)
            elif t == "}":
                if aperte and aperte.pop() and riga.strip():   # blocco su più righe: la graffa chiusa va a capo
                    righe.append("  " * rientro + riga.strip())
                    riga, rientro = "", len(aperte)
            elif tonde == 0 and not (t.upper() == "WITH" and re.search(r"(STARTS|ENDS)\s*$", riga, re.IGNORECASE)):
                if riga.strip():                       # a capo prima della clausola
                    righe.append("  " * rientro + riga.strip())
                riga, rientro = "", len(aperte)
                if aperte:
                    aperte[-1] = True
            riga += t
        riga += testo[pos:]
    if riga.strip():
        righe.append("  " * rientro + riga.strip())
    return "\n".join(righe)


def mostra_query(k, query, parametri):
    """Una query della traccia: titolo, testo su più righe e tabella dei parametri (i vettori riassunti)."""
    st.markdown(f"**Query {k}**")
    st.code(cypher_leggibile(query), language="cypher")
    if parametri:
        valori = [{"parametro": f"${p}",
                   "valore": f"vettore di {len(v)} numeri" if isinstance(v, list) and len(v) > 50 else str(v)}
                  for p, v in parametri.items()]
        st.dataframe(pd.DataFrame(valori), hide_index=True)


# =====================================================================================================
# C: query Cypher scritta dall'utente
# =====================================================================================================
ESEMPIO_CYPHER = """MATCH (t:Tournament)
RETURN t.label AS torneo, t.year AS anno, t.gender AS genere
ORDER BY anno DESC
LIMIT 10"""
MASSIMO_RIGHE = 1000


def pagina_cypher(g):
    st.caption("Scrivi una query Cypher sul grafo. Gira in sola lettura (Neo4j rifiuta le query che modificano il "
               "grafo) e si ferma dopo 30 secondi; si mostrano al massimo 1.000 righe.")
    if "schema_c" not in st.session_state:             # etichette e relazioni, lette una volta per sessione
        st.session_state["schema_c"] = (
            g.leggi("CALL db.labels() YIELD label RETURN label ORDER BY label")["label"].tolist(),
            g.leggi("CALL db.relationshipTypes() YIELD relationshipType AS tipo RETURN tipo ORDER BY tipo")["tipo"].tolist())
    etichette, relazioni = st.session_state["schema_c"]
    with st.expander("Classi e relazioni del grafo"):
        st.markdown("**Classi:** " + ", ".join(f"`{e}`" for e in etichette if e not in ("Resource", "_GraphConfig")))
        st.markdown("**Relazioni:** " + ", ".join(f"`{r}`" for r in relazioni))
    # form: la query si esegue solo premendo "Esegui", non a ogni interazione con la pagina
    with st.form("query_c"):
        query = st.text_area("Query Cypher", ESEMPIO_CYPHER, height=160)
        if st.form_submit_button("Esegui") and query.strip():
            inizio = time.perf_counter()
            try:
                st.session_state["risposta_c"] = (g.leggi_libera(query), time.perf_counter() - inizio, None)
            except Exception as e:
                errore = f"{type(e).__name__}: {e}"
                if "AccessMode" in errore or "read access mode" in errore:
                    errore = "La query modifica il grafo: qui sono ammesse solo letture."
                st.session_state["risposta_c"] = (None, 0, errore)
    if "risposta_c" not in st.session_state:
        return
    righe, durata, errore = st.session_state["risposta_c"]
    if errore:
        st.error(errore)
    elif righe.empty:
        st.info(f"Nessuna riga ({durata * 1000:.0f} ms).")
    else:
        st.markdown(f"**{len(righe)} righe** in {durata * 1000:.0f} ms"
                    + (f" (mostrate le prime {MASSIMO_RIGHE})" if len(righe) > MASSIMO_RIGHE else ""))
        tabella(righe.head(MASSIMO_RIGHE).map(_leggibile))


# =====================================================================================================
# Meccanismo B: domanda libera → Gemini scrive la query Cypher (llm.py)
# =====================================================================================================
@st.cache_resource(show_spinner=False)
def assistente(chiave):
    return llm.AssistenteCypher(chiave, {"text": modello_testo, "image": modello_clip})


def mostra_tentativo(k, t):
    """Cosa ha deciso Gemini in un tentativo: strategia, nomi (full-text), testi (ricerca semantica), query."""
    piano = t["piano"]
    st.markdown(f"**Tentativo {k}** · {piano['spiegazione']}")
    for n in piano["nomi"]:
        st.caption(f"nome ${n['param']}: «{n['testo']}» → full-text `{ricerca.query_lucene(n['testo'])}`")
    for v in piano["vettori"]:
        modello = "MiniLM (descrizioni)" if v["tipo"] == "text" else "CLIP (immagini)"
        st.caption(f"ricerca semantica ${v['param']}: «{v['testo']}» → vettore {modello}")
    if piano["cypher"]:
        st.code(cypher_leggibile(piano["cypher"]), language="cypher")
    if t["errore"]:
        st.warning(t["errore"])
    elif t["righe"] is not None and t["righe"].empty:
        st.caption("nessuna riga")


def _leggibile(x):
    """Un nodo o un arco restituito da una query generata diventa il suo nome (la tabella non sa mostrarli).

    Nodi e archi del driver Neo4j si riconoscono da element_id (senza importare il driver nell'app).
    """
    if hasattr(x, "element_id") and hasattr(x, "get"):
        return x.get("label") or x.get("uri") or str(x)
    return x


def mostra_risposta_b(g, r):
    """Passaggi di Gemini e risultato: tabella; immagini e scheda del giocatore se la query le restituisce."""
    with st.expander("Come ho interpretato la domanda", expanded=True):
        for k, t in enumerate(r["tentativi"], 1):
            mostra_tentativo(k, t)
    righe = r["righe"]
    if righe is None or righe.empty:
        st.info("Nessun risultato. Prova a riformulare la domanda o usa la ricerca guidata (A).")
        return
    righe = righe.map(_leggibile)
    st.markdown(f"**{len(righe)} righe**")
    tabella(righe.drop(columns=[c for c in ("giocatore_uri", "immagine") if c in righe.columns]))
    if "immagine" in righe.columns:
        colonne = st.columns(4)
        for k, (_, x) in enumerate(righe.head(12).iterrows()):
            with colonne[k % 4]:
                immagine(x["immagine"], 200, x.get("giocatore"))
    if "giocatore_uri" in righe.columns:
        giocatori = righe.drop_duplicates("giocatore_uri")
        i = st.selectbox("Apri la scheda del giocatore", range(len(giocatori)), key="b_scelta",
                         format_func=lambda k: str(giocatori["giocatore"].iloc[k]) if "giocatore" in giocatori else str(k))
        if st.toggle("Mostra la scheda", key="b_scheda"):
            mostra_giocatore(g, giocatori["giocatore_uri"].iloc[i])


def pagina_b(g):
    st.caption("Scrivi una domanda: Gemini la traduce in una query Cypher sullo schema del grafo, usando la ricerca "
               "per nome (full-text) per i nomi e la ricerca semantica (indici vettoriali, CLIP) per le descrizioni "
               "e le immagini. La query gira in sola lettura.")
    chiave = os.environ.get("GEMINI_API_KEY") or st.session_state.get("chiave_gemini")
    if not chiave:
        st.info("Inserisci la chiave API di Gemini nella barra laterale (oppure imposta GEMINI_API_KEY).")
        return
    # form: la domanda va a Gemini solo premendo "Chiedi", non a ogni interazione con la pagina
    with st.form("domanda_b"):
        domanda = st.text_input("Domanda", "photos of Japanese players celebrating at the 2022 World Cup")
        if st.form_submit_button("Chiedi") and domanda.strip():
            with st.spinner("Gemini scrive la query…"):
                st.session_state["risposta_b"] = assistente(chiave).rispondi(g, domanda)
    if "risposta_b" in st.session_state:
        mostra_risposta_b(g, st.session_state["risposta_b"])


def mostra_traccia(g):
    """Le query Cypher eseguite per costruire la risposta (la traccia di grafo.py), con i parametri."""
    with st.expander(f"Come ho trovato la risposta: {len(g.traccia)} query Cypher"):
        for k, q in enumerate(g.traccia, 1):
            if k > 1:
                st.divider()
            mostra_query(k, q["query"], q["parametri"])


# =====================================================================================================
# Pagina
# =====================================================================================================
with st.sidebar:
    st.title("⚽ Mondiali KG")
    st.caption("Retrieval multimediale sul knowledge graph dei Mondiali (dataset 1, 2, 3 e 4)")
    if "grafo" not in st.session_state:
        # NEO4J_PASSWORD facoltativa: evita di riscrivere la password a ogni avvio (non viene salvata)
        if os.environ.get("NEO4J_PASSWORD") and "errore_connessione" not in st.session_state:
            connetti(os.environ["NEO4J_PASSWORD"])
    if "grafo" not in st.session_state:
        with st.form("connessione"):
            password = st.text_input("Password di Neo4j", type="password")
            if st.form_submit_button("Connetti"):
                connetti(password)
                st.rerun()
        if "errore_connessione" in st.session_state:
            st.error(st.session_state["errore_connessione"])
        st.stop()
    st.success("Connesso a Neo4j")
    meccanismo = st.radio("Meccanismo", ["A", "B", "C"], key="meccanismo",
                          format_func={"A": "A · Ricerca guidata", "B": "B · Domanda libera",
                                       "C": "C · Query Cypher"}.get)
    tipo = st.radio("Tipo di domanda", list(TIPI), format_func=lambda t: f"{t} · {TIPI[t]}", key="tipo",
                    disabled=meccanismo != "A")
    if meccanismo == "B" and not (os.environ.get("GEMINI_API_KEY") or st.session_state.get("chiave_gemini")):
        chiave = st.text_input("Chiave API di Gemini", type="password")
        if chiave:                                     # copiata in una variabile della sessione (non di un widget),
            st.session_state["chiave_gemini"] = chiave  # così resta anche passando da A a B
            st.rerun()

g = st.session_state["grafo"]
g.nuova_traccia()                                  # la traccia contiene solo le query di questa risposta
try:
    if meccanismo == "B":
        st.header("Domanda libera")
        pagina_b(g)
    elif meccanismo == "C":
        st.header("Query Cypher")
        pagina_cypher(g)
    else:
        st.header(f"{tipo} · {TIPI[tipo]}")
        MODULI[tipo](g)
except Exception as e:                             # un errore in una scheda non deve bloccare l'app
    st.error(f"Errore: {type(e).__name__}: {e}")
mostra_traccia(g)
