"""Connessione a Neo4j per il retrieval.

Tutte le query dei modelli girano in transazioni di sola lettura: il retrieval non può modificare il grafo.
Le sole scritture ammesse sono la creazione degli indici (notebook 03–05).
"""
import textwrap

import pandas as pd
from neo4j import GraphDatabase, Query, RoutingControl

# Prefisso degli URI dei nodi (uguale a quello del notebook di costruzione)
BASE = "http://example.org/worldcup/resource/"


def _nativo(valore):
    # Le date di Neo4j (neo4j.time.Date) diventano datetime.date di Python
    return valore.to_native() if hasattr(valore, "to_native") else valore


class Grafo:
    def __init__(self, password, uri="neo4j://localhost:7687", utente="neo4j", database="neo4j"):
        # notifications_min_severity="OFF": il server non manda avvisi (es. "proprietà inesistente" per
        # labelConfidence prima del notebook 04), che riempirebbero l'output del notebook e dell'app
        self.driver = GraphDatabase.driver(uri, auth=(utente, password), notifications_min_severity="OFF")
        self.driver.verify_connectivity()
        self.database = database
        # Query eseguite dall'ultima nuova_traccia(): l'app le mostra in "come ho interpretato la domanda"
        self.traccia = []

    def leggi(self, query, **parametri):
        """Esegue una query in sola lettura e restituisce un DataFrame (con le colonne anche se è vuoto)."""
        risultato = self.driver.execute_query(query, parametri, database_=self.database,
                                              routing_=RoutingControl.READ)
        # la query si conserva com'è scritta (a capo e rientri), così l'app la mostra su più righe
        self.traccia.append({"query": textwrap.dedent(query).strip(), "parametri": parametri})
        return self._tabella(risultato)

    def leggi_libera(self, query, secondi=30):
        """Query Cypher scritta dall'utente nell'app: sola lettura (Neo4j rifiuta le scritture) e tempo massimo."""
        risultato = self.driver.execute_query(Query(query, timeout=secondi), database_=self.database,
                                              routing_=RoutingControl.READ)
        self.traccia.append({"query": textwrap.dedent(query).strip(), "parametri": {}})
        return self._tabella(risultato)

    @staticmethod
    def _tabella(risultato):
        righe = [[_nativo(v) for v in r.values()] for r in risultato.records]
        return pd.DataFrame(righe, columns=risultato.keys)

    def scrivi(self, query, **parametri):
        """Scrittura: usata solo per creare gli indici."""
        self.driver.execute_query(query, parametri, database_=self.database, routing_=RoutingControl.WRITE)

    def nuova_traccia(self):
        self.traccia = []

    def chiudi(self):
        self.driver.close()
