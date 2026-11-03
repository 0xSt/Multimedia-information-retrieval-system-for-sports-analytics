"""Modalità B: un LLM (Gemini) scrive la query Cypher a partire dalla domanda e dallo schema del grafo.

Come funziona:
1. il prompt contiene lo schema del grafo (SCHEMA) e le regole (REGOLE): l'LLM risponde con un JSON che contiene
   la query Cypher, i nomi da cercare con il full-text e i testi da cercare per significato (ricerca semantica);
2. i nomi diventano query Lucene (ricerca.query_lucene, con tolleranza agli errori di battitura) e i testi
   diventano vettori (MiniLM per le descrizioni dei nodi, CLIP per le immagini): sono i parametri della query;
3. la query gira in sola lettura (grafo.leggi); se fallisce o non trova nulla, l'LLM riceve il problema e
   riprova una volta.
L'LLM non vede i dati del grafo: riceve solo lo schema e la domanda.
"""
import json
import os
import re

from . import embedding as emb
from . import ricerca

MODELLO_LLM = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
TENTATIVI = 2

SCHEMA = """
NODES (label: properties). Every node also has `uri`. Names are in `label`.
- Tournament: label ("2014 FIFA Men's World Cup"), year (int), gender ('men'|'women'), startDate, endDate, countTeams
- Stage: label, stageName ('group stage','second group stage','round of 16','quarter-finals','semi-finals',
  'third-place match','final','final round'), stageNumber, isGroupStage, isKnockoutStage
- Group: label, groupLetter ('A','B',... or '1','2',...), countTeams
- Match: label ("Argentina vs France"), matchDate, homeScore, awayScore, extraTime, penaltyShootout,
  homePenalties, awayPenalties, isReplay, description, embedding
- Stadium: label, cityName, countryName, capacity, description, embedding
- Confederation: label, confederationCode ('UEFA','CONMEBOL','CAF','AFC','CONCACAF','OFC')
- Federation (a country's football association): label (country name, e.g. 'Germany', 'United States'),
  altLabel (official name), teamCode, regionName, description, embedding
- NationalTeam: label ("Italy (men)"), gender
- Participation (a national team at one tournament): label ("Italy at the 2006 FIFA Men's World Cup"),
  performance ('group stage','round of 16','quarter-finals','third-place match','final',...),
  finalPosition (1..4 only, 1 = champion), finalRank, isHost, fifaRanking (2022 only), description, embedding
- GroupStanding: groupPosition, points, advanced
- Player: label, givenName, familyName, birthDate, isFemale, description, embedding
- Manager, Referee: label, givenName, familyName, countryName, isFemale
- SquadMembership (a player in a squad): shirtNumber, isCaptain (2022 only), and 2022-only statistics:
  reportedAppearances, reportedGoals, assists, dribblesPer90, interceptionsPer90, tacklesPer90, duelsWonPer90,
  savePercentage, cleanSheetRate
- Appearance (a player in a match): isStarter, isSubstitute, shirtNumber
- Goal: minuteRegulation, minuteStoppage, matchPeriod, isOwnGoal, isPenalty
- Booking: minuteRegulation, minuteStoppage, isYellowCard, isRedCard, isSecondYellow, isSendingOff
- Substitution: minuteRegulation, minuteStoppage, isGoingOff, isComingOn
- PenaltyKick (penalty shoot-out kick): isConverted
- Award: label ('Golden Ball','Silver Ball','Bronze Ball','Golden Boot','Silver Boot','Bronze Boot',
  'Golden Glove','Best Young Player')
- Position: notation ('GK','DF','MF','FW', ...), prefLabel
- Club: label (only for 2022 squads)   - Brand: label (kit sponsors and boot brands, 2022 only)
- Image: filePath, labelConfidence, hasDuplicateContent, embedding (CLIP)

RELATIONSHIPS
(Stage)-[:stageOf]->(Tournament)            (Group)-[:groupOf]->(Stage)
(Match)-[:inStage]->(Stage)                 (Match)-[:inGroup]->(Group)
(Match)-[:playedAt]->(Stadium)              (Match)-[:refereedBy]->(Referee)
(Match)-[:homeTeam]->(Participation)        (Match)-[:awayTeam]->(Participation)
(Participation)-[:team]->(NationalTeam)-[:representsFederation]->(Federation)
(Participation)-[:tournament]->(Tournament) (Participation)-[:hasManager]->(Manager)
(Participation)-[:kitSponsor]->(Brand)      (Federation)-[:memberOf]->(Confederation)
(Federation)-[:predecessorOf]->(Federation)   e.g. West Germany -> Germany, Soviet Union -> Russia
(SquadMembership)-[:player]->(Player)       (SquadMembership)-[:participation]->(Participation)
(SquadMembership)-[:position]->(Position)   (SquadMembership)-[:wonAward]->(Award)
(SquadMembership)-[:club]->(Club)           (SquadMembership)-[:bootBrand]->(Brand)
(Appearance)-[:player]->(Player)            (Appearance)-[:participation]->(Participation)
(Appearance)-[:inMatch]->(Match)            (Appearance)-[:position]->(Position)
(Goal|Booking|Substitution|PenaltyKick)-[:player]->(Player)
(Goal|Booking|Substitution|PenaltyKick)-[:participation]->(Participation)   the player's team
(Goal|Booking|Substitution|PenaltyKick)-[:inMatch]->(Match)
(Goal)-[:creditedTo]->(Participation)       the team the goal counts for (differs only for own goals)
(GroupStanding)-[:participation]->(Participation)  (GroupStanding)-[:inGroupStanding]->(Group)
(Image)-[:depicts]->(Player)

FULL-TEXT INDEXES (names): nomi_giocatori (Player), nomi_federazioni (Federation), nomi_club (Club),
nomi_stadi (Stadium, also city), nomi_allenatori (Manager), nomi_arbitri (Referee)

VECTOR INDEXES (cosine): player_text, participation_text, match_text, federation_text, club_text,
stadium_text on the `embedding` of the node `description` (an English sentence with the main facts:
role, team, tournaments, goals, awards; result, scorers, stadium; ...) -> vectors of kind "text";
image_clip on Image.embedding -> vectors of kind "image" (CLIP: describe what is visible in the photo).

DATA NOTES
- Appearances and bookings exist only from 1970 and not for the 1999 women's World Cup.
- Images, clubs, boots, captains, FIFA ranking and the statistics of SquadMembership exist only for 2022.
- A penalty shoot-out counts as a draw; the score (homeScore, awayScore) includes extra time.
- For goals scored by a player use Goal {isOwnGoal: false}.
- "Germany" all time includes West Germany (use predecessorOf when the question is about history).
"""

REGOLE = """
You translate a question about the FIFA World Cup knowledge graph into ONE read-only Cypher query for Neo4j 5.
Answer only with the JSON object requested. Rules:
1. Read-only: MATCH, OPTIONAL MATCH, WITH, WHERE, RETURN, ORDER BY, LIMIT, UNWIND, CALL of the search procedures,
   COUNT {}, EXISTS {}. Always end with LIMIT (at most 50).
2. NAMES of players, countries, clubs, stadiums, cities, managers, referees: never compare `label` with a string.
   Find the node with the full-text index and a parameter, for example
     CALL db.index.fulltext.queryNodes('nomi_giocatori', $n1) YIELD node AS p, score
     WITH p ORDER BY score DESC LIMIT 1
   and put {"param": "n1", "testo": "Kylian Mbappe"} in "nomi" (write the name as most likely stored, in English).
3. MEANING (semantic search): when the question describes something without naming it, or asks about the
   content of photos, or asks for similar things, compare vectors. Put the English text to embed in "vettori"
   with its kind: "text" for the *_text indexes and for node.embedding of described nodes, "image" for
   image_clip and Image.embedding. Never compare a text vector with images or an image vector with descriptions.
   Two ways, choose case by case (they can also be combined in one query):
   a) index first, when the description is what narrows the search:
        CALL db.index.vector.queryNodes('player_text', 50, $v1) YIELD node AS p, score   (then filter with MATCH/WHERE)
   b) graph first, when MATCH/WHERE already narrows to few nodes:
        ... vector.similarity.cosine(i.embedding, $v1) AS score ORDER BY score DESC
   A node's own embedding can be the query vector (similar nodes): queryNodes('player_text', 20, p.embedding).
4. EXACT facts (years, stages, gender, counts, results, awards): use MATCH/WHERE/aggregations, not vectors.
5. Return readable column names. For players also return p.uri AS giocatore_uri and p.label AS giocatore;
   for images return i.filePath AS immagine. Never return embeddings or descriptions.
6. If the question cannot be answered with this schema, return an empty "cypher" and explain why.
7. "spiegazione": one short sentence in Italian on the strategy (which searches and why).
"""

# Formato della risposta dell'LLM (JSON Schema): Gemini lo rispetta (response_json_schema)
FORMATO = {
    "type": "object",
    "properties": {
        "spiegazione": {"type": "string"},
        "cypher": {"type": "string"},
        "nomi": {"type": "array", "items": {"type": "object", "properties": {
            "param": {"type": "string"}, "testo": {"type": "string"}}, "required": ["param", "testo"]}},
        "vettori": {"type": "array", "items": {"type": "object", "properties": {
            "param": {"type": "string"}, "testo": {"type": "string"},
            "tipo": {"type": "string", "enum": ["text", "image"]}}, "required": ["param", "testo", "tipo"]}},
    },
    "required": ["spiegazione", "cypher", "nomi", "vettori"],
}

# Controllo prima dell'esecuzione: nessuna scrittura. È una seconda barriera: grafo.leggi usa comunque una
# transazione di sola lettura, in cui Neo4j rifiuta qualsiasi modifica.
VIETATE = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|LOAD\s+CSV)\b|\bCALL\s+(apoc|dbms|db\.create)",
                     re.IGNORECASE)


class AssistenteCypher:
    """Domanda → JSON di Gemini → parametri (nomi e vettori) → query in sola lettura, con un nuovo tentativo."""

    def __init__(self, chiave, modelli):
        """chiave: API key di Gemini; modelli: {"text": funzione che dà MiniLM, "image": funzione che dà CLIP}.

        I modelli si passano come funzioni, così si caricano solo se una domanda li usa davvero.
        """
        from google import genai                     # import qui: serve solo alla modalità B
        from google.genai import types
        self.client = genai.Client(api_key=chiave)
        self.config = types.GenerateContentConfig(system_instruction=SCHEMA + REGOLE,
                                                  response_mime_type="application/json",
                                                  response_json_schema=FORMATO)
        self.modelli = modelli

    def piano(self, domanda, problema=None):
        """Chiede a Gemini il JSON con query, nomi e testi da vettorizzare."""
        testo = f"Question: {domanda}" + (f"\n\n{problema}" if problema else "")
        risposta = self.client.models.generate_content(model=MODELLO_LLM, contents=testo, config=self.config)
        return json.loads(risposta.text)

    def parametri(self, piano):
        """Nomi → query Lucene con tolleranza agli errori; testi → vettori del modello giusto."""
        p = {n["param"]: ricerca.query_lucene(n["testo"]) for n in piano["nomi"]}
        for v in piano["vettori"]:
            p[v["param"]] = [float(x) for x in emb.vettori_testo(self.modelli[v["tipo"]](), [v["testo"]])[0]]
        return p

    def rispondi(self, grafo, domanda):
        """Esegue la domanda; restituisce i tentativi (piano, errore o righe) e le righe finali."""
        tentativi, problema = [], None
        for _ in range(TENTATIVI):
            voce = {"piano": self.piano(domanda, problema), "errore": None, "righe": None}
            tentativi.append(voce)
            cypher = voce["piano"]["cypher"].strip()
            if not cypher:
                voce["errore"] = "nessuna query: " + voce["piano"]["spiegazione"]
                break
            try:
                if VIETATE.search(cypher):
                    raise ValueError("la query contiene istruzioni di scrittura")
                voce["righe"] = grafo.leggi(cypher, **self.parametri(voce["piano"]))
            except Exception as e:                     # sintassi, proprietà inesistenti, parametri mancanti…
                voce["errore"] = f"{type(e).__name__}: {e}"
                problema = f"Your previous query failed.\nQuery:\n{cypher}\nError: {voce['errore']}\nWrite a corrected query."
                continue
            if len(voce["righe"]):
                break
            problema = (f"Your previous query returned no rows.\nQuery:\n{cypher}\nCheck names (full-text), "
                        "filters and the way semantic search is combined with the graph, then try again.")
        return {"domanda": domanda, "tentativi": tentativi, "righe": tentativi[-1]["righe"]}
