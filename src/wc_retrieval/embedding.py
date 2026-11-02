"""Embedding delle immagini con CLIP (Op. 29) e delle descrizioni dei nodi (Op. 30).

CLIP (Contrastive Language-Image Pre-training) trasforma immagini e testi in vettori dello stesso spazio:
un'immagine e una frase che la descrive hanno vettori vicini. Si usa il modello `clip-ViT-B-32` di
sentence-transformers (512 dimensioni), su CPU.

Le descrizioni dei nodi (descrizioni.py) si trasformano in vettori con `all-MiniLM-L6-v2` (384 dimensioni),
un modello di frasi piccolo e veloce: due frasi con lo stesso significato hanno vettori vicini.

Gli embedding sono dati derivati (decisione R6 di architettura-retrieval.md): si salvano in Parquet in
data/embeddings/ e si caricano in Neo4j come proprietà dei nodi, con un indice vettoriale. Non entrano nelle
triple RDF. Se il grafo viene ricostruito (la cella "ATTENZIONE" del notebook di costruzione svuota il
database), basta ricaricarli dal Parquet con carica_embedding_immagini().
"""
import time

import numpy as np
import pandas as pd

MODELLO_CLIP = "clip-ViT-B-32"
DIMENSIONI_CLIP = 512
INDICE_IMMAGINI = "image_clip"
MODELLO_TESTO = "all-MiniLM-L6-v2"
DIMENSIONI_TESTO = 384


def carica_clip():
    """Modello CLIP su CPU. Al primo uso sentence-transformers lo scarica (circa 600 MB) e lo tiene in cache."""
    from sentence_transformers import SentenceTransformer     # import qui: libreria pesante, serve solo ora
    return SentenceTransformer(MODELLO_CLIP, device="cpu")


def carica_modello_testo():
    """Modello di frasi su CPU (circa 90 MB, scaricato da sentence-transformers al primo uso)."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODELLO_TESTO, device="cpu")


def apri_immagine(percorso):
    """Immagine in RGB (CLIP vuole 3 canali: i PNG con trasparenza o in scala di grigi vengono convertiti)."""
    from PIL import Image
    with Image.open(percorso) as im:
        return im.convert("RGB")


def vettori_testo(modello, testi):
    """Testi → vettori CLIP normalizzati (lunghezza 1): il prodotto scalare è la similarità coseno."""
    return modello.encode(list(testi), convert_to_numpy=True, normalize_embeddings=True)


def calcola_embedding_immagini(tabella, radice, cartella_lotti, modello, lotto=1000, batch=32):
    """Calcola gli embedding a lotti, salvando ogni lotto in un file Parquet.

    Se il calcolo si interrompe (kernel riavviato, PC spento), rieseguendo la funzione i lotti già salvati
    si saltano e si riparte dal primo mancante. tabella: colonne uri e filePath (relativo a radice).
    Restituisce (embedding, errori): DataFrame uri + embedding, e i file che non si sono potuti aprire.
    """
    cartella_lotti.mkdir(parents=True, exist_ok=True)
    n_lotti = (len(tabella) + lotto - 1) // lotto
    inizio_tempo, fatti = time.time(), 0
    for k in range(n_lotti):
        file = cartella_lotti / f"lotto_{k:03d}.parquet"
        if file.exists():
            continue                                         # lotto già calcolato
        parte = tabella.iloc[k * lotto:(k + 1) * lotto]
        immagini, uri, errori = [], [], []
        for u, p in zip(parte["uri"], parte["filePath"]):
            try:
                immagini.append(apri_immagine(radice / p))
                uri.append(u)
            except Exception as e:                           # file illeggibile: si annota e si prosegue
                errori.append({"uri": u, "filePath": p, "errore": f"{type(e).__name__}: {e}"})
        vettori = (modello.encode(immagini, batch_size=batch, convert_to_numpy=True, normalize_embeddings=True)
                   if immagini else np.zeros((0, DIMENSIONI_CLIP), dtype="float32"))
        pd.DataFrame({"uri": uri, "embedding": list(vettori.astype("float32"))}).to_parquet(file, index=False)
        pd.DataFrame(errori, columns=["uri", "filePath", "errore"]).to_parquet(file.with_suffix(".errori.parquet"), index=False)
        fatti += len(parte)
        trascorso = time.time() - inizio_tempo
        mancanti = len(tabella) - (k + 1) * lotto
        print(f"lotto {k + 1}/{n_lotti}: {len(uri)} immagini, {len(errori)} errori | "
              f"{trascorso / 60:.1f} min, stima per finire {max(mancanti, 0) * trascorso / fatti / 60:.1f} min", flush=True)
    embedding = pd.concat([pd.read_parquet(f) for f in sorted(cartella_lotti.glob("lotto_???.parquet"))], ignore_index=True)
    errori = pd.concat([pd.read_parquet(f) for f in sorted(cartella_lotti.glob("lotto_???.errori.parquet"))], ignore_index=True)
    return embedding, errori


def confidenza_etichette(tabella):
    """labelConfidence: similarità coseno tra un'immagine e il centro delle ALTRE immagini dello stesso giocatore.

    Il centro si calcola escludendo l'immagine stessa (leave-one-out), così un'immagine non "vota" per sé.
    Le immagini di un giocatore che lo ritraggono davvero si somigliano tra loro; un'immagine sbagliata
    (un altro giocatore, una foto di squadra, un segnaposto) è lontana dal centro e riceve un valore basso.
    tabella: colonne player_id ed embedding (vettori normalizzati). Restituisce un array, NaN se il giocatore
    ha una sola immagine.
    """
    X = np.vstack(tabella["embedding"].to_numpy()).astype("float64")
    gruppi = tabella["player_id"].to_numpy()
    somme = pd.DataFrame(X).groupby(gruppi).transform("sum").to_numpy()   # somma dei vettori del giocatore
    n = pd.Series(gruppi).map(pd.Series(gruppi).value_counts()).to_numpy()
    altri = somme - X                                                      # tutte le altre immagini
    norme = np.linalg.norm(altri, axis=1)
    coseno = (X * altri).sum(axis=1) / np.where(norme == 0, 1, norme)
    return np.where(n > 1, coseno, np.nan)


def auc(punteggi_alti, punteggi_bassi):
    """Probabilità che un elemento del primo gruppo abbia un punteggio più alto di uno del secondo (AUC).

    0,5 = la misura non distingue i due gruppi; 1 = li separa perfettamente. Calcolata con i ranghi
    (statistica di Mann-Whitney), senza librerie aggiuntive.
    """
    a, b = np.asarray(punteggi_alti, dtype=float), np.asarray(punteggi_bassi, dtype=float)
    ranghi = pd.Series(np.concatenate([a, b])).rank().to_numpy()
    return (ranghi[:len(a)].sum() - len(a) * (len(a) + 1) / 2) / (len(a) * len(b))


def carica_embedding_immagini(grafo, tabella, lotto=1000):
    """Scrive embedding e labelConfidence sui nodi Image, a lotti di `lotto` immagini per transazione."""
    scritti = 0
    for inizio in range(0, len(tabella), lotto):
        parte = tabella.iloc[inizio:inizio + lotto]
        righe = [{"uri": u, "vettore": [float(x) for x in v],
                  "confidenza": None if pd.isna(c) else float(c)}
                 for u, v, c in zip(parte["uri"], parte["embedding"], parte["labelConfidence"])]
        # MATCH su :Resource e non su :Image: è :Resource(uri) ad avere l'indice di unicità (vincolo di n10s),
        # quindi ogni nodo si trova subito invece di scorrere tutte le 41.460 immagini
        grafo.scrivi("""
            UNWIND $righe AS r
            MATCH (i:Resource {uri: r.uri})
            SET i.labelConfidence = r.confidenza
            WITH i, r
            CALL db.create.setNodeVectorProperty(i, 'embedding', r.vettore)""", righe=righe)
        scritti += len(righe)
    return scritti


def carica_descrizioni(grafo, tabella, lotto=1000):
    """Scrive `description` (la frase) ed `embedding` (il suo vettore) sui nodi, a lotti per transazione.

    tabella: colonne uri, descrizione, embedding. Come per le immagini, MATCH su :Resource (indice di unicità).
    """
    scritti = 0
    for inizio in range(0, len(tabella), lotto):
        parte = tabella.iloc[inizio:inizio + lotto]
        righe = [{"uri": u, "descrizione": d, "vettore": [float(x) for x in v]}
                 for u, d, v in zip(parte["uri"], parte["descrizione"], parte["embedding"])]
        grafo.scrivi("""
            UNWIND $righe AS r
            MATCH (n:Resource {uri: r.uri})
            SET n.description = r.descrizione
            WITH n, r
            CALL db.create.setNodeVectorProperty(n, 'embedding', r.vettore)""", righe=righe)
        scritti += len(righe)
    return scritti


def crea_indice_vettoriale(grafo, nome, etichetta, proprieta, dimensioni, quantizzazione=False, ricrea=True):
    """Indice vettoriale di Neo4j (similarità coseno) sulla proprietà `proprieta` dei nodi `etichetta`.

    quantizzazione=False: dalla versione 5.23 Neo4j comprime di default i vettori dell'indice (quantizzazione
    a 8 bit) per risparmiare memoria; con punteggi CLIP molto vicini tra loro la compressione altera punteggi e
    ordine dei risultati, e con 41.460 vettori la memoria non è un problema. ricrea=True: cancella e ricrea
    l'indice, perché le opzioni di un indice esistente non si possono cambiare.
    """
    if ricrea:
        grafo.scrivi(f"DROP INDEX {nome} IF EXISTS")
    grafo.scrivi(f"""
        CREATE VECTOR INDEX {nome} IF NOT EXISTS FOR (n:{etichetta}) ON (n.{proprieta})
        OPTIONS {{indexConfig: {{`vector.dimensions`: {dimensioni}, `vector.similarity_function`: 'cosine',
                                 `vector.quantization.enabled`: {str(quantizzazione).lower()}}}}}""")
    grafo.scrivi("CALL db.awaitIndexes(600)")
