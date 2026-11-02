"""Retrieval sul knowledge graph dei Mondiali (architettura: claude/architettura-retrieval.md).

Moduli:
    grafo     connessione a Neo4j (letture in sola lettura) e registro delle query eseguite
    ricerca   ricerca delle entità per nome (full-text, Op. 27), delle immagini (Op. 29) e delle descrizioni (Op. 30)
    modelli   un modello Cypher per ogni tipo di domanda del catalogo (Op. 27)
    descrizioni descrizioni dei nodi in linguaggio naturale, dai dati del grafo (Op. 30)
    embedding embedding CLIP delle immagini, labelConfidence, embedding delle descrizioni, indici vettoriali (Op. 29–30)
    llm       meccanismo B: Gemini scrive la query Cypher dallo schema, con full-text e ricerca semantica (Op. 32)
    valutazione strategie di ricerca e metriche della valutazione del retrieval (Op. 33)
"""
import os
from pathlib import Path


def carica_env(file=Path(__file__).resolve().parents[2] / ".env"):
    """Legge il file .env nella radice del progetto (chiave API di Gemini e simili), se esiste.

    Formato: una riga NOME=valore; righe vuote, commenti (#) e valori vuoti si ignorano. Le variabili già
    impostate nel sistema hanno la precedenza. Si esegue all'import del pacchetto, quindi vale per app e notebook.
    """
    if file.is_file():
        for riga in file.read_text(encoding="utf-8").splitlines():
            nome, _, valore = riga.strip().partition("=")
            valore = valore.strip().strip("\"'")
            if nome and not nome.startswith("#") and valore:
                os.environ.setdefault(nome.strip(), valore)


carica_env()
