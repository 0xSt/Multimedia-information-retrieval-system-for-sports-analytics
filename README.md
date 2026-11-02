# Knowledge graph dei Mondiali FIFA per il Multimedia Information Retrieval

Progetto del corso di Multimedia Information Retrieval (Sports Analytics). Quattro fonti eterogenee (dati relazionali, tabelle annuali, statistiche e immagini dei giocatori) vengono integrate in un knowledge graph RDF basato su un'ontologia propria, caricato in Neo4j e interrogato con una ricerca che combina query Cypher, ricerca full-text sui nomi e ricerca semantica su testo (MiniLM) e immagini (CLIP).

- **Grafo:** 126.744 nodi, 273.516 archi, 24 classi, 27 tipi di relazione; tutti i Mondiali maschili e femminili dal 1930 al 2022, con immagini, club e statistiche dei giocatori del 2022.
- **Ricerca:** ricerca guidata con modelli Cypher (meccanismo A) e domande libere tradotte in Cypher da un LLM (meccanismo B, Gemini), con indici full-text e vettoriali dentro la stessa query.
- **App:** demo in Streamlit.

Il report del progetto è in `docs/`.

## Struttura

```
ontology/            ontologia (spec.py → wc-ontology.ttl) e figure dello schema
notebooks/           la pipeline, da eseguire in ordine (tabella sotto)
src/wc_retrieval/    codice della ricerca, usato da notebook e app
app/app.py           app Streamlit
data/processed/      tabelle pulite e integrate (Parquet), prodotte dai notebook 01 e 02
data/kg/             il grafo in triple RDF (27 file Turtle), prodotto dal notebook 02
data/valutazione/    casi della valutazione e risultati
docs/                report
```

| Notebook | Cosa fa | Operazioni |
|---|---|---|
| `01_preprocessing` | pulizia delle fonti, indice delle immagini, entity resolution dei giocatori | Op. 5, 7, 9–11, 14 |
| `02_costruzione_grafo` | tabelle integrate → triple RDF → import in Neo4j con n10s | Op. 15–24 |
| `03_indici_fulltext` | indici full-text dei nomi | Op. 27, 32 |
| `04_embedding_immagini` | embedding CLIP, `labelConfidence`, indice vettoriale delle immagini | Op. 29 |
| `05_embedding_descrizioni` | descrizioni dei nodi, embedding MiniLM, indici vettoriali | Op. 30 |
| `06_valutazione_retrieval` | valutazione del retrieval (E2 descrizioni, E3 immagini) | Op. 33 |
| `07_grafo_vs_fonti` | il grafo rispetto ai singoli dataset | Op. 34 |

## Requisiti

- Python 3.12 e i pacchetti di `requirements.txt` (`pip install -r requirements.txt`).
- Neo4j 5.26 (LTS) con il plugin [neosemantics (n10s) 5.26.0](https://github.com/neo4j-labs/neosemantics): n10s funziona solo con la versione di Neo4j per cui è compilato.
- Per il meccanismo B, una chiave API di Gemini: copiare `.env.example` in `.env` e inserirla. Il file `.env` non va mai caricato nella repository.
- La password di Neo4j non è salvata da nessuna parte: notebook e app la chiedono all'avvio (oppure si legge dalla variabile `NEO4J_PASSWORD`).

## Dati

I dataset originali non sono inclusi (licenze di terzi e oltre 400 MB). Vanno scaricati in `data/raw/` (al posto di `INSERIRE_LINK` va il link della pagina del dataset):

| Cartella | Dataset |
|---|---|
| `data/raw/dataset_1/worldcup.db` | Fjelstul World Cup Database, file SQLite del repository [jfjelstul/worldcup](https://github.com/jfjelstul/worldcup) |
| `data/raw/dataset_2/` | Kaggle, "FIFA World Cup 1930–2022" (Sourav Banerjee), [link](INSERIRE_LINK): file `FIFA - <anno>.csv` e `FIFA - World Cup Summary.csv` |
| `data/raw/dataset_3/` | Kaggle, "FIFA WC 2022 Players Stats" (Rhugved Bhojane), [link](INSERIRE_LINK): file `FIFA WC 2022 Players Stats.csv` |
| `data/raw/dataset_4/Images/Images/` | Kaggle, immagini dei giocatori del Mondiale 2022 (Soumendra Prasad), [link](INSERIRE_LINK): cartelle `Group X/<Squadra> Players/Images_<giocatore>/` |

`data/processed/` e `data/kg/` sono inclusi: con questi file il grafo si importa in Neo4j senza rifare il preprocessing. Gli embedding (`data/embeddings/`, circa 200 MB) non sono inclusi e si rigenerano con i notebook 04 e 05.

## Esecuzione

1. Notebook da `01` a `05` in ordine (il `02` svuota il database Neo4j prima dell'import).
2. App: dalla radice del progetto, `streamlit run app/app.py` (su Windows con l'ambiente virtuale: `.venv\Scripts\streamlit.exe run app/app.py`), poi `http://localhost:8501`.
3. Valutazione: notebook `06` e `07`.
