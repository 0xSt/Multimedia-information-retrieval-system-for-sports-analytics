"""Connessione a Neo4j per il retrieval.

Tutte le query dei modelli girano in transazioni di sola lettura (come in verifica_grafo.ipynb):
il retrieval non può modificare il grafo. Le sole scritture ammesse sono la creazione degli indici.
"""
import pandas as pd
from neo4j import GraphDatabase, RoutingControl

# Prefisso degli URI dei nodi (uguale a quello del notebook di costruzione)
BASE = "http://example.org/worldcup/resource/"


def _nativo(valore):
    # Le date di Neo4j (neo4j.time.Date) diventano datetime.date di Python
    return valore.to_native() if hasattr(valore, "to_native") else valore


class Grafo:
    def __init__(self, password, uri="neo4j://localhost:7687", utente="neo4j", database="neo4j"):
        # notifications_min_severity="OFF": il server non manda avvisi (es. "proprietà inesistente" per
        # labelConfidence prima dell'Op. 29), che riempirebbero l'output del notebook e dell'app
        self.driver = GraphDatabase.driver(uri, auth=(utente, password), notifications_min_severity="OFF")
        self.driver.verify_connectivity()
        self.database = database
        # Query eseguite dall'ultima nuova_traccia(): l'app le mostra in "come ho interpretato la domanda"
        self.traccia = []

    def leggi(self, query, **parametri):
        """Esegue una query in sola lettura e restituisce un DataFrame (con le colonne anche se è vuoto)."""
        risultato = self.driver.execute_query(query, parametri, database_=self.database,
                                              routing_=RoutingControl.READ)
        self.traccia.append({"query": " ".join(query.split()), "parametri": parametri})
        righe = [[_nativo(v) for v in r.values()] for r in risultato.records]
        return pd.DataFrame(righe, columns=risultato.keys)

    def scrivi(self, query, **parametri):
        """Scrittura: usata solo per creare gli indici."""
        self.driver.execute_query(query, parametri, database_=self.database, routing_=RoutingControl.WRITE)

    def nuova_traccia(self):
        self.traccia = []

    def chiudi(self):
        self.driver.close()
