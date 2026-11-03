"""Ricerca delle entità: per nome (indici full-text di Neo4j, Lucene) e per significato (indici vettoriali).

Gli embedding di frasi sono deboli sui nomi propri ("Ronaldo" e "Cristiano Ronaldo" sono stringhe simili ma
persone diverse); il full-text cerca le parole, tollera gli errori di battitura (ricerca fuzzy) e ordina i
risultati in modo prevedibile. La ricerca vettoriale sulle descrizioni dei nodi
trova invece le entità descritte senza nome; quella sulle immagini le foto descritte a parole.
Le due ricerche restano funzioni separate, così la valutazione può confrontarle.
"""
import re

import pandas as pd
from unidecode import unidecode

# Un indice per classe: nome dell'indice e proprietà indicizzate
INDICI_NOMI = {
    "Player": ("nomi_giocatori", ["label"]),
    "Federation": ("nomi_federazioni", ["label", "altLabel"]),
    "Club": ("nomi_club", ["label"]),
    "Stadium": ("nomi_stadi", ["label", "cityName"]),
    "Manager": ("nomi_allenatori", ["label"]),          # nomi usati dalla modalità B
    "Referee": ("nomi_arbitri", ["label"]),
}

# Informazione breve per distinguere omonimi nei suggerimenti (es. i Mondiali giocati)
DETTAGLIO = {
    "Player": """[(node)<-[:player]-(:SquadMembership)-[:participation]->(pa:Participation)-[:tournament]->(t:Tournament)
                  | split(pa.label, ' at the ')[0] + ' ' + toString(t.year)]""",
    "Federation": "[node.altLabel]",
    "Club": "[]",
    "Stadium": "[node.cityName]",
    "Manager": """[(node)<-[:hasManager]-(pa:Participation)-[:tournament]->(t:Tournament)
                   | split(pa.label, ' at the ')[0] + ' ' + toString(t.year)]""",
    "Referee": "[node.countryName]",
}


# Un indice vettoriale per classe sulle descrizioni dei nodi: nome dell'indice
INDICI_DESCRIZIONI = {
    "Player": "player_text",
    "Participation": "participation_text",
    "Match": "match_text",
    "Federation": "federation_text",
    "Club": "club_text",
    "Stadium": "stadium_text",
}

# A parità di punteggio Lucene (es. "mbape" dista una lettera da Mbappé, Mbane e Mwape) vince il nodo con più
# archi nel grafo: per un giocatore convocazioni, presenze ed eventi; per una nazionale le partecipazioni
RILEVANZA = {
    "Player": "COUNT { (node)<-[:player]-() }",
    "Federation": "COUNT { (node)<-[:representsFederation]-()<-[:team]-() }",
    "Club": "COUNT { (node)<-[:club]-() }",
    "Stadium": "COUNT { (node)<-[:playedAt]-() }",
    "Manager": "COUNT { (node)<-[:hasManager]-() }",
    "Referee": "COUNT { (node)<-[:refereedBy]-() }",
}


def crea_indici_fulltext(grafo):
    """Crea (se mancano) gli indici full-text dei nomi.

    Analizzatore 'standard-folding': divide in parole, minuscole e senza accenti ("Mbappé" → "mbappe"),
    così "Mbappe" e "Mbappé" coincidono. Gli indici sopravvivono allo svuotamento del database
    (cella "ATTENZIONE" del notebook di costruzione), che cancella i dati ma non lo schema.
    """
    for classe, (nome, proprieta) in INDICI_NOMI.items():
        campi = ", ".join(f"n.{p}" for p in proprieta)
        grafo.scrivi(f"""
            CREATE FULLTEXT INDEX {nome} IF NOT EXISTS FOR (n:{classe}) ON EACH [{campi}]
            OPTIONS {{indexConfig: {{`fulltext.analyzer`: 'standard-folding'}}}}""")
    grafo.scrivi("CALL db.awaitIndexes(300)")      # attende che gli indici siano popolati


def query_lucene(testo, fuzzy=True):
    """Testo libero → query Lucene in cui tutte le parole devono comparire (AND).

    Con fuzzy=True ogni parola tollera errori: 1 lettera diversa fino a 6 lettere, 2 oltre
    ("mbape~1" trova "mbappe"). Le parole di 2–3 lettere restano esatte, altrimenti troverebbero di tutto;
    una lettera sola è un'iniziale ("J. Rodriguez" → "j* AND rodriguez~2").
    """
    parole = re.split(r"[\s\-]+", unidecode(testo).lower())
    termini = []
    for p in parole:
        p = re.sub(r"[^a-z0-9']", "", p).strip("'")       # toglie punteggiatura e caratteri speciali di Lucene
        if not p:
            continue
        if len(p) == 1:
            p += "*"                                       # iniziale: "j" → tutte le parole che iniziano per j
        elif fuzzy and len(p) >= 4:
            p += "~1" if len(p) <= 6 else "~2"
        termini.append(p)
    return " AND ".join(termini)


def cerca_immagini(grafo, vettore, k=10, indice="image_clip", candidati=100):
    """Immagini più vicine a un vettore CLIP (da un testo o da un'altra immagine), con il giocatore raffigurato.

    È la base del tipo R2 (immagini da testo). score = similarità coseno trasformata da Neo4j in [0, 1]:
    score = (1 + coseno) / 2.
    candidati: l'indice vettoriale (HNSW) è approssimato e, con punteggi CLIP vicinissimi tra loro, può saltare
    alcuni dei veri primi k. Si chiedono quindi `candidati` risultati (più se ne chiedono, più a fondo l'indice
    esplora il grafo dei vettori) e si tengono i primi k: costa pochi millisecondi in più (sovracampionamento).
    """
    return grafo.leggi("""
        CALL db.index.vector.queryNodes($indice, $candidati, $vettore) YIELD node, score
        WITH node, score ORDER BY score DESC LIMIT $k
        MATCH (node)-[:depicts]->(p:Player)
        RETURN node.uri AS uri, node.filePath AS percorso, p.label AS giocatore, p.uri AS giocatore_uri,
               node.labelConfidence AS confidenza, node.hasDuplicateContent AS duplicata, score AS punteggio
        ORDER BY punteggio DESC""", indice=indice, k=k, candidati=max(candidati, k), vettore=[float(x) for x in vettore])


def cerca_nome(grafo, classe, testo, k=10, fuzzy=True):
    """Nodi della classe il cui nome corrisponde al testo: per punteggio Lucene, poi per rilevanza nel grafo."""
    indice = INDICI_NOMI[classe][0]
    q = query_lucene(testo, fuzzy)
    if not q:
        return pd.DataFrame(columns=["uri", "nome", "dettaglio", "punteggio", "rilevanza"])
    # round(..., 3): punteggi uguali fino alla terza cifra contano come pari merito
    return grafo.leggi(f"""
        CALL db.index.fulltext.queryNodes($indice, $q) YIELD node, score
        RETURN node.uri AS uri, node.label AS nome, {DETTAGLIO[classe]} AS dettaglio, score AS punteggio,
               {RILEVANZA[classe]} AS rilevanza
        ORDER BY round(punteggio, 3) DESC, rilevanza DESC, nome LIMIT $k""", indice=indice, q=q, k=k)


def cerca_descrizioni(grafo, vettore, classi=None, k=10, candidati=100):
    """Nodi la cui descrizione è più vicina a un vettore di frase (tipo R1: entità descritta senza nome).

    classi: elenco di classi in cui cercare (default: tutte e sei). Si interroga l'indice di ogni classe e si
    uniscono i risultati per punteggio: il modello è lo stesso, quindi i punteggi sono confrontabili.
    candidati: sovracampionamento, come in cerca_immagini.
    """
    risultati = []
    for classe in classi or INDICI_DESCRIZIONI:
        risultati.append(grafo.leggi("""
            CALL db.index.vector.queryNodes($indice, $candidati, $vettore) YIELD node, score
            WITH node, score ORDER BY score DESC LIMIT $k
            RETURN node.uri AS uri, $classe AS classe, node.label AS nome, node.description AS descrizione,
                   score AS punteggio""", indice=INDICI_DESCRIZIONI[classe], classe=classe, k=k,
            candidati=max(candidati, k), vettore=[float(x) for x in vettore]))
    pieni = [r for r in risultati if len(r)] or risultati[:1]     # si tolgono le tabelle vuote prima di unire
    tutti = pd.concat(pieni, ignore_index=True)
    return tutti.sort_values("punteggio", ascending=False).head(k).reset_index(drop=True)
