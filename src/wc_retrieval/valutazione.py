"""Valutazione del retrieval a partire dalla query Cypher (Op. 33); i casi sono in data/valutazione/suite_valutazione.json.

Contiene due cose:
- le STRATEGIE di ricerca confrontate in E2 (solo semantica, indice prima, grafo prima) e le ricerche di immagini
  di E3, scritte come query Cypher che ricevono il vettore della domanda come parametro;
- le METRICHE di ranking: precisione@k, richiamo@k, nDCG@k, reciprocal rank.
Il documento claude/valutazione-retrieval.md spiega perché ogni caso è nella suite.
"""
import math

from .ricerca import INDICI_DESCRIZIONI

CANDIDATI = 100        # candidati chiesti all'indice nella ricerca semantica pura (decisione R10)


# =====================================================================================================
# Metriche: lista = URI nell'ordine restituito; pertinenti = insieme degli URI giusti
# =====================================================================================================
def precisione(lista, pertinenti, k):
    """Quota dei primi k risultati che sono pertinenti (si divide per k anche se la lista è più corta)."""
    return sum(u in pertinenti for u in lista[:k]) / k


def richiamo(lista, pertinenti, k):
    """Quota dei pertinenti che compaiono tra i primi k risultati."""
    return sum(u in pertinenti for u in lista[:k]) / len(pertinenti)


def ndcg(lista, pertinenti, k):
    """nDCG@k con pertinenza sì/no: un pertinente in posizione i vale 1/log2(i+1); si divide per il caso ideale
    (tutti i pertinenti in cima), quindi 1 = ordine perfetto, 0 = nessun pertinente tra i primi k."""
    dcg = sum(1 / math.log2(i + 2) for i, u in enumerate(lista[:k]) if u in pertinenti)
    ideale = sum(1 / math.log2(i + 2) for i in range(min(len(pertinenti), k)))
    return dcg / ideale


def reciproco(lista, pertinenti):
    """1 / posizione del primo pertinente (0 se non ce n'è nessuno); la media sulle domande è l'MRR."""
    return next((1 / (i + 1) for i, u in enumerate(lista) if u in pertinenti), 0.0)


def metriche(lista, pertinenti):
    """Le metriche di E2 per una classifica di 10 risultati."""
    return {"P@5": precisione(lista, pertinenti, 5), "R@10": richiamo(lista, pertinenti, 10),
            "nDCG@10": ndcg(lista, pertinenti, 10), "RR": reciproco(lista, pertinenti), "vuota": len(lista) == 0}


# =====================================================================================================
# Strategie di E2 sulle descrizioni dei nodi. filtro = condizione Cypher su n (la parte data al grafo);
# escludi = URI da togliere (il nodo usato come domanda in "simili a…")
# =====================================================================================================
def solo_semantica(grafo, classe, vettore, k=10, escludi=""):
    """Indice vettoriale della classe su tutti i nodi, nessun filtro."""
    return grafo.leggi("""
        CALL db.index.vector.queryNodes($indice, $candidati, $v) YIELD node AS n, score
        WHERE n.uri <> $escludi
        RETURN n.uri AS uri, n.label AS nome, score ORDER BY score DESC LIMIT $k""",
                       indice=INDICI_DESCRIZIONI[classe], candidati=CANDIDATI, v=vettore, k=k, escludi=escludi)


def indice_prima(grafo, classe, vettore, filtro, candidati, k=10, escludi=""):
    """Indice prima: i `candidati` più vicini su tutti i nodi, poi il filtro del grafo (può scartarli tutti)."""
    return grafo.leggi(f"""
        CALL db.index.vector.queryNodes($indice, $candidati, $v) YIELD node AS n, score
        WHERE ({filtro}) AND n.uri <> $escludi
        RETURN n.uri AS uri, n.label AS nome, score ORDER BY score DESC LIMIT $k""",
                       indice=INDICI_DESCRIZIONI[classe], candidati=candidati, v=vettore, k=k, escludi=escludi)


def grafo_prima(grafo, classe, vettore, filtro, k=10, escludi=""):
    """Grafo prima: il filtro restringe i nodi, poi il coseno esatto con ciascuno (senza indice)."""
    return grafo.leggi(f"""
        MATCH (n:{classe}) WHERE ({filtro}) AND n.uri <> $escludi
        WITH n, vector.similarity.cosine(n.embedding, $v) AS score
        RETURN n.uri AS uri, n.label AS nome, score ORDER BY score DESC LIMIT $k""",
                       v=vettore, k=k, escludi=escludi)


# =====================================================================================================
# Immagini (E3): il vettore è un testo passato in CLIP
# =====================================================================================================
def immagini_indice(grafo, vettore, k=10):
    """Le k immagini più vicine al testo su tutte le 41.460 (indice image_clip, 100 candidati)."""
    return grafo.leggi("""
        CALL db.index.vector.queryNodes('image_clip', $candidati, $v) YIELD node AS i, score
        MATCH (i)-[:depicts]->(p:Player)
        RETURN i.uri AS uri, i.filePath AS percorso, p.uri AS giocatore_uri, p.label AS giocatore, score
        ORDER BY score DESC LIMIT $k""", candidati=max(CANDIDATI, k), v=vettore, k=k)


def immagini_squadra(grafo, vettore, paese, k=10):
    """Grafo prima: solo le immagini dei convocati di `paese` al Mondiale 2022, ordinate per coseno con il testo."""
    return grafo.leggi("""
        MATCH (i:Image)-[:depicts]->(p:Player)<-[:player]-(:SquadMembership)-[:participation]->(pa:Participation)
              -[:tournament]->(:Tournament {year: 2022})
        MATCH (pa)-[:team]->(:NationalTeam)-[:representsFederation]->(:Federation {label: $paese})
        WITH DISTINCT i, p
        RETURN i.uri AS uri, i.filePath AS percorso, p.uri AS giocatore_uri, p.label AS giocatore,
               vector.similarity.cosine(i.embedding, $v) AS score ORDER BY score DESC LIMIT $k""",
                       v=vettore, paese=paese, k=k)


# Insiemi di immagini pertinenti ricavati dal grafo (E3b)
PERTINENTI_IMMAGINI = {
    "portieri": """MATCH (i:Image)-[:depicts]->(:Player)<-[:player]-(:SquadMembership)-[:position]->(:Position {notation: 'GK'})
                   RETURN DISTINCT i.uri AS uri""",
    "squadra": """MATCH (i:Image)-[:depicts]->(:Player)<-[:player]-(:SquadMembership)-[:participation]->(pa:Participation)
                        -[:tournament]->(:Tournament {year: 2022})
                  MATCH (pa)-[:team]->(:NationalTeam)-[:representsFederation]->(:Federation {label: $paese})
                  RETURN DISTINCT i.uri AS uri""",
}


def immagini_pertinenti(grafo, etichetta, filtro=None):
    """Insieme pertinente e insieme di partenza (per la base casuale) di un concetto di E3b.

    etichetta: "portieri" oppure "squadra:<paese>"; filtro: None (tutte le immagini) oppure "squadra:<paese>".
    """
    def insieme(e):
        if e == "portieri":
            return set(grafo.leggi(PERTINENTI_IMMAGINI["portieri"])["uri"])
        return set(grafo.leggi(PERTINENTI_IMMAGINI["squadra"], paese=e.split(":", 1)[1])["uri"])
    tutte = set(grafo.leggi("MATCH (i:Image) RETURN i.uri AS uri")["uri"]) if filtro is None else insieme(filtro)
    return insieme(etichetta) & tutte, tutte
