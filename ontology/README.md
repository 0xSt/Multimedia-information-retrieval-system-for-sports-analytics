# Ontologia del knowledge graph dei Mondiali (v0.3)

`spec.py` è l'unica fonte: classi, proprietà, fonti e regole URI sono definite lì.
Tutto il resto si rigenera dalla specifica.

Requisiti: `pip install rdflib` e Graphviz (comando `dot`) per le illustrazioni.

Da questa cartella:

    python gen_ttl.py . wc-ontology.ttl                      # genera l'ontologia
    python gen_dot.py . core schema_core.dot                 # illustrazione sintetica
    python gen_dot.py . full schema_full.dot                 # illustrazione con le proprietà dato
    dot -Tsvg schema_full.dot -o schema_full.svg
    dot -Tpng -Gdpi=150 schema_full.dot -o schema_full.png

Versione 0.3 (17/10/2026): i ruoli (Position) contengono solo i codici e i nomi del dataset 1
(skos:notation, skos:prefLabel@en); rimosse le etichette italiane, la gerarchia skos:broader
e lo schema SKOS, che non erano nella fonte.
