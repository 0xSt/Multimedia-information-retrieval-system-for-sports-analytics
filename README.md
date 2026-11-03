# Knowledge graph dei Mondiali FIFA per il Multimedia Information Retrieval

Progetto del corso di Information Retrieval. Quattro fonti eterogenee (dati relazionali, tabelle annuali, statistiche e immagini dei giocatori) vengono integrate in un knowledge graph RDF basato su un'ontologia propria, caricato in Neo4j e interrogato con una ricerca che combina query Cypher, ricerca full-text sui nomi e ricerca semantica su testo (MiniLM) e immagini (CLIP).

- **Grafo:** 126.744 nodi, 273.516 archi, 24 classi, 27 tipi di relazione; tutti i Mondiali maschili e femminili dal 1930 al 2022, con immagini, club e statistiche dei giocatori del 2022.
- **Ricerca:** ricerca guidata con modelli Cypher e domande libere tradotte in Cypher da un LLM, con indici full-text e vettoriali dentro la stessa query.
- **App:** demo in Streamlit.


## Struttura

```
ontology/            ontologia (spec.py → wc-ontology.ttl) e figure dello schema
notebooks/           la pipeline di operazioni fatte sui dati, da eseguire in ordine
src/wc_retrieval/    codice della ricerca, usato da notebook e app
app/app.py           app Streamlit
data/processed/      tabelle pulite e integrate (Parquet), prodotte dai notebook 01 e 02
data/kg/             il grafo in triple RDF (27 file Turtle), prodotto dal notebook 02
data/valutazione/    casi della valutazione e risultati
```

| Notebook | Cosa fa |
|---|---|
| `01_preprocessing` | pulizia delle fonti, indice delle immagini, entity resolution dei giocatori |
| `02_costruzione_grafo` | tabelle integrate → triple RDF → import in Neo4j con n10s |
| `03_indici_fulltext` | indici full-text dei nomi |
| `04_embedding_immagini` | embedding CLIP, `labelConfidence`, indice vettoriale delle immagini |
| `05_embedding_descrizioni` | descrizioni dei nodi, embedding MiniLM, indici vettoriali |
| `06_valutazione_retrieval` | valutazione del retrieval (E1 descrizioni, E2 immagini) |
| `07_grafo_vs_fonti` | Confronto tra grafo e i singoli dataset |

## Requisiti

- Python 3.12 e i pacchetti di `requirements.txt`.
- Neo4j 5.26 (LTS) con il plugin [neosemantics (n10s) 5.26.0](https://github.com/neo4j-labs/neosemantics): n10s funziona solo con la versione di Neo4j per cui è compilato.
- Un ambiente per i notebook: VS Code con l'estensione Jupyter, oppure Jupyter (`pip install notebook`). Il kernel è quello dell'ambiente virtuale (`ipykernel` è in `requirements.txt`).
- Una connessione a internet al primo avvio: i modelli CLIP (circa 600 MB) e MiniLM (circa 90 MB) si scaricano da Hugging Face e restano in cache.
- Per la modalità B, una chiave API di Gemini (vedi il passo 5 sotto).
- La password di Neo4j non è salvata da nessuna parte: notebook e app la chiedono all'avvio (oppure si legge dalla variabile `NEO4J_PASSWORD`).


### I quattro dataset originali

Vanno scaricati e messi in `data/raw/` con questi nomi di cartella. I notebook leggono i file in sola lettura e non li modificano.

| Cartella | Dataset | File usati |
|---|---|---|
| `data/raw/dataset_1/` | Fjelstul World Cup Database, repository [jfjelstul/worldcup](https://github.com/jfjelstul/worldcup) | `worldcup.db` (database SQLite) |
| `data/raw/dataset_2/` | Kaggle, "FIFA World Cup 1930–2022" (Sourav Banerjee), [link](INSERIRE_LINK) | i 22 file annuali `FIFA - <anno>.csv` (`FIFA - World Cup Summary.csv` è nel dataset ma non si usa) |
| `data/raw/dataset_3/` | Kaggle, "FIFA WC 2022 Players Stats" (Rhugved Bhojane), [link](INSERIRE_LINK) | `FIFA WC 2022 Players Stats.csv` |
| `data/raw/dataset_4/` | Kaggle, immagini dei giocatori del Mondiale 2022 (Soumendra Prasad), [link](INSERIRE_LINK) | le cartelle delle immagini sotto `Images/Images/` |

Struttura attesa dopo l'estrazione degli archivi (i nomi dei file non vanno cambiati):

```
data/raw/
├── dataset_1/
│   └── worldcup.db
├── dataset_2/
│   ├── FIFA - 1930.csv
│   ├── ...
│   └── FIFA - 2022.csv
├── dataset_3/
│   └── FIFA WC 2022 Players Stats.csv
└── dataset_4/
    └── Images/
        └── Images/
            ├── Group A/
            │   ├── Ecuador Players/
            │   │   ├── Images_Alan Franco/   (le immagini del giocatore)
            │   │   └── ...
            │   └── ...
            └── Group H/
```

Per il dataset 4, l'archivio di Kaggle va estratto dentro `data/raw/dataset_4/` in modo che le cartelle `Group A` … `Group H` finiscano in `data/raw/dataset_4/Images/Images/`. I file dei dataset 2 e 3 vanno direttamente nella loro cartella, senza sottocartelle.

### Quali dati servono a ogni passo

| Passo | Dataset originali | Neo4j | Scrive | Note |
|---|---|---|---|---|
| `01` | tutti e quattro | no | `data/processed/` | i file prodotti sono già nella repo: rieseguirlo li riscrive |
| `02` | dataset 1 | sì, con n10s | `data/processed/`, `data/kg/`, il grafo | **svuota il database** prima dell'import |
| `03` | nessuno | sì | indici full-text | |
| `04` | dataset 4 | sì | `data/embeddings/immagini_clip.parquet`, embedding nel grafo | lungo: circa 3,5 ore su CPU per 41.460 immagini; salva a lotti e, se si interrompe, riparte dal primo lotto mancante |
| `05` | nessuno | sì | `data/embeddings/descrizioni_minilm.parquet`, embedding nel grafo | pochi minuti |
| `06` | nessuno | sì (dopo 02–05) | `data/valutazione/risultati/` | |
| `07` | nessuno | sì (dopo 02 e 04) | `data/valutazione/risultati/` | |
| app | dataset 4 (solo per mostrare le foto) | sì (dopo 02–05) | niente | senza il dataset 4 funziona e scrive "(immagine non disponibile)"; la modalità B richiede la chiave Gemini |

## Esecuzione passo per passo

Comandi per Windows (prompt dei comandi); su Linux e macOS `.venv\Scripts\` diventa `.venv/bin/`.

1. **Repository e ambiente Python**
   ```
   git clone <url della repository>
   cd <cartella della repository>
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```
2. **Neo4j:** in Neo4j Desktop creare un'istanza Neo4j 5.26, installare il plugin n10s dal pannello *Plugins* dell'istanza, scegliere la password e avviarla. Notebook e app si collegano a `neo4j://localhost:7687`, utente `neo4j`, database `neo4j`.
3. **Dataset:** scaricare i quattro dataset in `data/raw/` come descritto sopra.
4. **Notebook da `01` a `05`, in ordine:** aprire ogni notebook con il kernel di `.venv` ed eseguire tutte le celle dall'alto in basso. I notebook si possono avviare sia dalla cartella `notebooks/` sia dalla radice della repository. Ogni notebook che usa Neo4j chiede la password all'inizio.
5. **Chiave Gemini (facoltativa, solo per la modalità B):** copiare `.env.example` in `.env` e scrivere la chiave dopo `GEMINI_API_KEY=`. In alternativa si incolla nella barra laterale dell'app.
   ```
   copy .env.example .env
   ```
6. **App:** dalla radice della repository
   ```
   .venv\Scripts\streamlit run app\app.py
   ```
   poi aprire `http://localhost:8501` e inserire la password di Neo4j nella barra laterale.
7. **Valutazione:** notebook `06` e `07`.
