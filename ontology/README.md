# Ontologia del knowledge graph dei Mondiali (v0.3)

`spec.py` è l'unica fonte: classi, proprietà, fonti e regole URI sono definite lì.
`gen_ttl.py` ne ricava l'ontologia OWL in Turtle.

Requisiti: `pip install rdflib`.

Da questa cartella:

    python gen_ttl.py . wc-ontology.ttl      # genera l'ontologia

| File | Contenuto |
|---|---|
| `spec.py` | specifica dell'ontologia: classi, proprietà, fonte di ogni elemento, regole degli URI |
| `gen_ttl.py` | genera `wc-ontology.ttl` dalla specifica |
| `wc-ontology.ttl` | l'ontologia OWL, usata dal notebook 02 per costruire le triple |
| `wc-example.ttl` | alcune istanze d'esempio scritte con l'ontologia |
| `schema_core.svg` | schema dell'ontologia: classi, relazioni e fonte di ogni elemento |
| `schema_full.svg` | lo stesso schema con le proprietà dato di ogni classe |

Versione 0.3 (17/10/2026): i ruoli (Position) contengono solo i codici e i nomi del dataset 1
(skos:notation, skos:prefLabel@en); rimosse le etichette italiane, la gerarchia skos:broader
e lo schema SKOS, che non erano nella fonte.
