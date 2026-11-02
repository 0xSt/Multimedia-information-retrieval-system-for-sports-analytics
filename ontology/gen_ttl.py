import sys
sys.path.insert(0, sys.argv[1])
from spec import *

def lit(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

def dominio(nome, base):
    doms = DOMINI_MULTIPLI.get(nome)
    if not doms:
        return f"wc:{base}"
    return "[ a owl:Class ; owl:unionOf ( " + " ".join(f"wc:{d}" for d in doms) + " ) ]"

out = []
w = out.append
w("""@prefix wc:      <http://example.org/worldcup/ontology#> .
@prefix owl:     <http://www.w3.org/2002/07/owl#> .
@prefix rdf:     <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs:    <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:     <http://www.w3.org/2001/XMLSchema#> .
@prefix schema:  <https://schema.org/> .
@prefix foaf:    <http://xmlns.com/foaf/0.1/> .
@prefix skos:    <http://www.w3.org/2004/02/skos/core#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

# =====================================================================
#  Ontologia del Knowledge Graph dei Mondiali FIFA
#  Generata da spec.py: modificare la specifica, non questo file.
# =====================================================================

<http://example.org/worldcup/ontology>
    a owl:Ontology ;
    dcterms:title "World Cup Knowledge Graph Ontology"@en , "Ontologia del knowledge graph dei Mondiali"@it ;
    dcterms:description "Schema globale che integra quattro dataset: il database dei Mondiali FIFA (dataset 1) e tre dataset Kaggle (dataset 2: classifiche 1930-2022; dataset 3: statistiche dei giocatori 2022; dataset 4: immagini dei giocatori 2022)."@it ;
    dcterms:creator "Stef" ;
    dcterms:source <https://github.com/jfjelstul/worldcup> ;
    owl:versionInfo "0.3" .

# Annotazione: dataset da cui provengono le istanze o i valori
wc:sourceDataset a owl:AnnotationProperty ;
    rdfs:label "dataset di origine"@it ;
    rdfs:comment "1, 2, 3, 4 = dataset 1, 2, 3, 4; D = derivata o regola di integrazione."@it .

wc:uriPattern a owl:AnnotationProperty ;
    rdfs:label "schema dell'URI"@it ;
    rdfs:comment "Modello con cui si costruisce l'URI delle istanze, relativo a http://example.org/worldcup/resource/"@it .
""")

w("\n# ---------------------------------------------------------------------\n#  Classi\n# ---------------------------------------------------------------------\n")
for nome, sup, fonte, gruppo, it, comm, uri in CLASSI:
    righe = [f"wc:{nome} a owl:Class"]
    for s in sup:
        righe.append(f"rdfs:subClassOf {s}")
    righe.append(f"rdfs:label {lit(nome)}@en , {lit(it)}@it")
    righe.append(f"rdfs:comment {lit(comm)}@it")
    righe.append(f"wc:sourceDataset {lit(fonte)}")
    righe.append(f"wc:uriPattern {lit(uri)}")
    w(" ;\n    ".join(righe) + " .\n")

w("""[] a owl:AllDisjointClasses ;
    owl:members ( wc:Tournament wc:Stage wc:Group wc:Match wc:Stadium wc:Confederation
                  wc:NationalTeam wc:Participation wc:Person wc:SquadMembership wc:Appearance
                  wc:MatchEvent wc:Club wc:Brand wc:Image ) .
""")

w("\n# ---------------------------------------------------------------------\n#  Proprietà oggetto\n# ---------------------------------------------------------------------\n")
for nome, dom, rng, fonte, orig, comm in OGGETTO:
    righe = [f"wc:{nome} a owl:ObjectProperty",
             f"rdfs:domain {dominio(nome, dom)}",
             f"rdfs:range wc:{rng}",
             f"rdfs:comment {lit(comm)}@it",
             f"wc:sourceDataset {lit(fonte)}",
             f"dcterms:source {lit(orig)}"]
    if nome == "predecessorOf":
        righe.insert(1, "owl:inverseOf wc:successorOf")
    if nome == "depicts":
        righe.insert(1, "rdfs:subPropertyOf foaf:depicts")
    if nome in ("tournament", "team", "stageOf", "groupOf", "inStage", "playedAt", "homeTeam", "awayTeam"):
        righe.insert(1, "a owl:FunctionalProperty")
    w(" ;\n    ".join(righe) + " .\n")
w("wc:successorOf a owl:ObjectProperty ;\n    rdfs:comment \"Inversa di predecessorOf.\"@it ;\n    wc:sourceDataset \"D\" .\n")

w("\n# ---------------------------------------------------------------------\n#  Proprietà dato\n# ---------------------------------------------------------------------\n")
for nome, dom, tipo, fonte, orig, comm in DATI:
    righe = [f"wc:{nome} a owl:DatatypeProperty",
             f"rdfs:domain {dominio(nome, dom)}",
             f"rdfs:range xsd:{tipo}",
             f"rdfs:comment {lit(comm)}@it",
             f"wc:sourceDataset {lit(fonte)}",
             f"dcterms:source {lit(orig)}"]
    w(" ;\n    ".join(righe) + " .\n")

w("\n# ---------------------------------------------------------------------\n#  Ruoli di gioco (codici e nomi del dataset 1)\n# ---------------------------------------------------------------------\n")
for code, nome in POSIZIONI:
    righe = [f"wc:position_{code} a wc:Position , skos:Concept",
             f"skos:notation {lit(code)}",
             f"skos:prefLabel {lit(nome)}@en"]
    w(" ;\n    ".join(righe) + " .\n")

open(sys.argv[2], "w", encoding="utf-8").write("\n".join(out))
