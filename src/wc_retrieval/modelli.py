"""Modelli Cypher: un modello per ogni tipo di domanda del catalogo dell'app.

Ogni modello riceve parametri già risolti (URI dei nodi, anno, genere, metrica) e restituisce un dizionario
di valori e DataFrame. Gli stessi modelli servono alla ricerca guidata (A) e alla domanda libera (B):
B si limita a trovare i parametri a partire dalla frase.

Tipi implementati: S1 scheda giocatore, S2 squadra in un torneo, S3 scheda partita, S4 scheda torneo,
C1 classifica per metrica, F1 testa a testa. R1 e R2 usano gli embedding (ricerca.py).
"""
import pandas as pd

# Nome della nazionale da un'etichetta di partecipazione: "Argentina at the 2022 FIFA Men's World Cup" → "Argentina"
SQUADRA = "split({}.label, ' at the ')[0]"


def _squadra(var):
    return SQUADRA.format(var)


def _riga(df):
    # Prima riga di un DataFrame come dizionario (None se il DataFrame è vuoto)
    return None if df.empty else df.iloc[0].to_dict()


# =====================================================================================================
# Supporto: federazioni con i predecessori
# =====================================================================================================
def federazioni(grafo, uri):
    """URI della federazione e di tutti i suoi predecessori (Germany → Germany + West Germany).

    Serve alle classifiche e ai confronti tra nazionali: i titoli e le partite della Germania Ovest
    appartengono alla storia della Germania.
    """
    df = grafo.leggi("""
        MATCH (f:Federation {uri: $uri})
        OPTIONAL MATCH (p:Federation)-[:predecessorOf*]->(f)
        RETURN f.uri AS federazione, collect(p.uri) AS predecessori""", uri=uri)
    if df.empty:
        raise ValueError(f"Federazione non trovata: {uri}")
    return [df["federazione"][0]] + list(df["predecessori"][0])


# =====================================================================================================
# S1 — Scheda giocatore
# =====================================================================================================
def scheda_giocatore(grafo, uri):
    """Anagrafica, Mondiali giocati con le statistiche di ciascuno, totali, dati 2022 del dataset 3, immagine."""
    anagrafica = _riga(grafo.leggi("""
        MATCH (p:Player {uri: $uri})
        RETURN p.label AS nome, p.givenName AS nome_proprio, p.familyName AS cognome,
               p.birthDate AS nascita, p.isFemale AS donna,
               head([(p)-[:sameAs]->(d) | d.uri]) AS dbpedia""", uri=uri))
    if anagrafica is None:
        raise ValueError(f"Giocatore non trovato: {uri}")

    # Una riga per Mondiale. Presenze e cartellini esistono solo per i tornei in cui il dataset 1 li registra
    # (dal 1970, non per il Mondiale femminile 1999): altrove il valore è vuoto (non noto), non 0.
    mondiali = grafo.leggi(f"""
        MATCH (p:Player {{uri: $uri}})<-[:player]-(s:SquadMembership)-[:participation]->(pa:Participation)
              -[:tournament]->(t:Tournament)
        WITH p, s, pa, t,
             EXISTS {{ (:Appearance)-[:participation]->(:Participation)-[:tournament]->(t) }} AS con_presenze,
             EXISTS {{ (:Booking)-[:participation]->(:Participation)-[:tournament]->(t) }} AS con_cartellini
        RETURN t.year AS anno, {_squadra('pa')} AS squadra, s.shirtNumber AS maglia,
               head([(s)-[:position]->(r) | r.notation]) AS ruolo,
               CASE WHEN con_presenze THEN COUNT {{ (p)<-[:player]-(:Appearance)-[:participation]->(pa) }} END AS presenze,
               CASE WHEN con_presenze THEN COUNT {{ (p)<-[:player]-(:Appearance {{isStarter: true}})-[:participation]->(pa) }} END AS titolare,
               COUNT {{ (p)<-[:player]-(:Goal {{isOwnGoal: false}})-[:participation]->(pa) }} AS gol,
               COUNT {{ (p)<-[:player]-(:Goal {{isOwnGoal: false, isPenalty: true}})-[:participation]->(pa) }} AS gol_su_rigore,
               COUNT {{ (p)<-[:player]-(:Goal {{isOwnGoal: true}})-[:participation]->(pa) }} AS autogol,
               CASE WHEN con_cartellini THEN COUNT {{ (p)<-[:player]-(:Booking {{isYellowCard: true}})-[:participation]->(pa) }} END AS gialli,
               CASE WHEN con_cartellini THEN COUNT {{ (p)<-[:player]-(:Booking {{isSendingOff: true}})-[:participation]->(pa) }} END AS espulsioni,
               [(s)-[:wonAward]->(a) | a.label] AS premi,
               s.isCaptain AS capitano,
               head([(s)-[:club]->(c) | c.label]) AS club,
               head([(s)-[:bootBrand]->(b) | b.label]) AS scarpe,
               pa.performance AS risultato_squadra
        ORDER BY anno""", uri=uri)
    mondiali["premi"] = mondiali["premi"].map(sorted)

    numeri = ["presenze", "titolare", "gol", "gol_su_rigore", "autogol", "gialli", "espulsioni"]
    totali = {c: int(pd.to_numeric(mondiali[c]).sum()) for c in numeri}
    totali["mondiali"] = len(mondiali)
    totali["premi"] = sum(len(x) for x in mondiali["premi"])

    # Statistiche del Mondiale 2022 (dataset 3): presenti solo per 814 convocati del 2022
    stat_2022 = _riga(grafo.leggi("""
        MATCH (:Player {uri: $uri})<-[:player]-(s:SquadMembership)-[:participation]->(:Participation)
              -[:tournament]->(:Tournament {year: 2022})
        RETURN s.reportedAppearances AS presenze, s.reportedGoals AS gol, s.assists AS assist,
               s.dribblesPer90 AS dribbling_per_90, s.interceptionsPer90 AS intercetti_per_90,
               s.tacklesPer90 AS contrasti_per_90, s.duelsWonPer90 AS duelli_vinti_per_90,
               s.savePercentage AS parate, s.cleanSheetRate AS porta_inviolata""", uri=uri))

    # Immagine: prima le non duplicate, poi la confidenza più alta (calcolata con CLIP nel notebook 04)
    immagine = _riga(grafo.leggi("""
        MATCH (:Player {uri: $uri})<-[:depicts]-(i:Image)
        WITH i ORDER BY i.hasDuplicateContent, coalesce(i.labelConfidence, -1.0) DESC, i.filePath
        WITH count(i) AS immagini, collect({percorso: i.filePath, confidenza: i.labelConfidence})[0] AS migliore
        RETURN immagini, migliore.percorso AS percorso, migliore.confidenza AS confidenza""", uri=uri))

    return {"tipo": "S1", "anagrafica": anagrafica, "mondiali": mondiali, "totali": totali,
            "statistiche_2022": stat_2022, "immagine": immagine}


# =====================================================================================================
# S2 — Squadra in un torneo
# =====================================================================================================
def scheda_partecipazione(grafo, federazione_uri, anno, genere="men"):
    """Allenatore, risultato, partite, gironi, marcatori e rosa di una nazionale in un Mondiale."""
    info = _riga(grafo.leggi("""
        MATCH (:Federation {uri: $f})<-[:representsFederation]-(:NationalTeam {gender: $genere})
              <-[:team]-(pa:Participation)-[:tournament]->(t:Tournament {year: $anno})
        RETURN pa.uri AS uri, pa.label AS partecipazione, pa.performance AS risultato,
               pa.finalPosition AS posizione, pa.finalRank AS classifica_finale, pa.isHost AS ospitante,
               pa.fifaRanking AS ranking_fifa, head([(pa)-[:kitSponsor]->(b) | b.label]) AS sponsor_tecnico,
               [(pa)-[:hasManager]->(m) | m.label] AS allenatori""", f=federazione_uri, anno=anno, genere=genere))
    if info is None:
        return None                                     # la nazionale non ha giocato quel Mondiale
    pa = info["uri"]

    # Due MATCH separate: dentro una stessa MATCH un arco si usa una volta sola (unicità delle relazioni),
    # e l'arco partita → squadra della prima riga è anche uno dei due archi homeTeam/awayTeam della seconda
    partite = grafo.leggi(f"""
        MATCH (pa:Participation {{uri: $pa}})<-[:homeTeam|awayTeam]-(m:Match)
        MATCH (m)-[:inStage]->(s:Stage), (m)-[:homeTeam]->(h:Participation), (m)-[:awayTeam]->(a:Participation)
        RETURN m.uri AS uri, m.matchDate AS data, s.stageName AS fase,
               head([(m)-[:inGroup]->(gr) | gr.groupLetter]) AS girone,
               {_squadra('h')} AS casa, m.homeScore AS gol_casa, m.awayScore AS gol_trasferta,
               {_squadra('a')} AS trasferta, m.extraTime AS supplementari,
               m.homePenalties AS rigori_casa, m.awayPenalties AS rigori_trasferta
        ORDER BY data""", pa=pa)

    # Classifiche dei gironi in cui ha giocato (alcuni tornei hanno due fasi a gironi);
    # anche qui due MATCH, altrimenti la riga della squadra stessa sparirebbe (unicità delle relazioni)
    gironi = grafo.leggi(f"""
        MATCH (pa:Participation {{uri: $pa}})<-[:participation]-(:GroupStanding)-[:inGroupStanding]->(gr:Group)
              -[:groupOf]->(s:Stage)
        MATCH (gr)<-[:inGroupStanding]-(gs:GroupStanding)-[:participation]->(x:Participation)
        RETURN s.stageName AS fase, gr.label AS girone, gs.groupPosition AS posizione,
               {_squadra('x')} AS squadra, gs.points AS punti, gs.advanced AS qualificata
        ORDER BY s.stageNumber, gr.label, posizione""", pa=pa)

    marcatori = grafo.leggi("""
        MATCH (:Participation {uri: $pa})<-[:participation]-(g:Goal {isOwnGoal: false})-[:player]->(p:Player)
        RETURN p.label AS giocatore, count(g) AS gol, sum(CASE WHEN g.isPenalty THEN 1 ELSE 0 END) AS su_rigore
        ORDER BY gol DESC, giocatore""", pa=pa)

    rosa = grafo.leggi("""
        MATCH (pa:Participation {uri: $pa})<-[:participation]-(s:SquadMembership)-[:player]->(p:Player)
        RETURN s.shirtNumber AS maglia, p.label AS giocatore, p.uri AS uri,
               head([(s)-[:position]->(r) | r.notation]) AS ruolo,
               head([(s)-[:club]->(c) | c.label]) AS club, s.isCaptain AS capitano,
               COUNT { (p)<-[:player]-(:Appearance)-[:participation]->(pa) } AS presenze,
               COUNT { (p)<-[:player]-(:Goal {isOwnGoal: false})-[:participation]->(pa) } AS gol
        ORDER BY maglia, giocatore""", pa=pa)

    return {"tipo": "S2", "info": info, "partite": partite, "gironi": gironi,
            "marcatori": marcatori, "rosa": rosa}


# =====================================================================================================
# S3 — Scheda partita (e ricerca delle partite tra due nazionali)
# =====================================================================================================
def cerca_partite(grafo, federazione_uri, avversario_uri=None, anno=None, fase=None, genere=None):
    """Partite di una nazionale (con i predecessori), eventualmente contro un avversario, in un anno, in una fase."""
    f1 = federazioni(grafo, federazione_uri)
    f2 = federazioni(grafo, avversario_uri) if avversario_uri else None
    return grafo.leggi(f"""
        MATCH (m:Match)-[:homeTeam|awayTeam]->(:Participation)-[:team]->(:NationalTeam)
              -[:representsFederation]->(x1:Federation)
        WHERE x1.uri IN $f1
          AND ($f2 IS NULL OR EXISTS {{
                MATCH (m)-[:homeTeam|awayTeam]->(:Participation)-[:team]->(:NationalTeam)
                      -[:representsFederation]->(x2:Federation)
                WHERE x2.uri IN $f2 }})
        MATCH (m)-[:inStage]->(s:Stage)-[:stageOf]->(t:Tournament),
              (m)-[:homeTeam]->(h:Participation), (m)-[:awayTeam]->(a:Participation)
        WHERE ($anno IS NULL OR t.year = $anno) AND ($fase IS NULL OR s.stageName = $fase)
          AND ($genere IS NULL OR t.gender = $genere)
        RETURN m.uri AS uri, t.year AS anno, t.gender AS genere, s.stageName AS fase, m.matchDate AS data,
               {_squadra('h')} AS casa, m.homeScore AS gol_casa, m.awayScore AS gol_trasferta, {_squadra('a')} AS trasferta,
               m.extraTime AS supplementari, m.homePenalties AS rigori_casa, m.awayPenalties AS rigori_trasferta,
               head([(h)-[:team]->(:NationalTeam)-[:representsFederation]->(y) | y.uri]) AS federazione_casa
        ORDER BY data""", f1=f1, f2=f2, anno=anno, fase=fase, genere=genere)


def scheda_partita(grafo, uri):
    """Risultato, stadio, arbitro e tutti gli eventi di una partita."""
    info = _riga(grafo.leggi(f"""
        MATCH (m:Match {{uri: $uri}})-[:inStage]->(s:Stage)-[:stageOf]->(t:Tournament),
              (m)-[:homeTeam]->(h:Participation), (m)-[:awayTeam]->(a:Participation)
        OPTIONAL MATCH (m)-[:playedAt]->(st:Stadium)
        OPTIONAL MATCH (m)-[:refereedBy]->(r:Referee)
        RETURN m.label AS partita, t.label AS torneo, t.year AS anno, s.stageName AS fase,
               head([(m)-[:inGroup]->(gr) | gr.label]) AS girone, m.matchDate AS data,
               {_squadra('h')} AS casa, {_squadra('a')} AS trasferta, m.homeScore AS gol_casa, m.awayScore AS gol_trasferta,
               m.extraTime AS supplementari, m.penaltyShootout AS serie_di_rigori,
               m.homePenalties AS rigori_casa, m.awayPenalties AS rigori_trasferta, m.isReplay AS ripetizione,
               st.label AS stadio, st.cityName AS citta, r.label AS arbitro""", uri=uri))
    if info is None:
        raise ValueError(f"Partita non trovata: {uri}")

    gol = grafo.leggi(f"""
        MATCH (:Match {{uri: $uri}})<-[:inMatch]-(e:Goal)-[:player]->(p:Player), (e)-[:creditedTo]->(c:Participation)
        RETURN e.minuteRegulation AS minuto, e.minuteStoppage AS recupero, p.label AS giocatore,
               {_squadra('c')} AS squadra, e.isPenalty AS rigore, e.isOwnGoal AS autogol
        ORDER BY minuto, recupero, giocatore""", uri=uri)
    cartellini = grafo.leggi(f"""
        MATCH (:Match {{uri: $uri}})<-[:inMatch]-(e:Booking)-[:player]->(p:Player), (e)-[:participation]->(c:Participation)
        RETURN e.minuteRegulation AS minuto, e.minuteStoppage AS recupero, p.label AS giocatore,
               {_squadra('c')} AS squadra, e.isYellowCard AS giallo, e.isSecondYellow AS secondo_giallo,
               e.isRedCard AS rosso, e.isSendingOff AS espulsione
        ORDER BY minuto, recupero, giocatore""", uri=uri)
    sostituzioni = grafo.leggi(f"""
        MATCH (:Match {{uri: $uri}})<-[:inMatch]-(e:Substitution)-[:player]->(p:Player), (e)-[:participation]->(c:Participation)
        RETURN e.minuteRegulation AS minuto, e.minuteStoppage AS recupero, {_squadra('c')} AS squadra,
               CASE WHEN e.isComingOn THEN 'entra' ELSE 'esce' END AS movimento, p.label AS giocatore
        ORDER BY minuto, recupero, squadra, movimento""", uri=uri)
    rigori = grafo.leggi(f"""
        MATCH (:Match {{uri: $uri}})<-[:inMatch]-(e:PenaltyKick)-[:player]->(p:Player), (e)-[:participation]->(c:Participation)
        RETURN {_squadra('c')} AS squadra, p.label AS tiratore, e.isConverted AS segnato
        ORDER BY e.uri""", uri=uri)

    return {"tipo": "S3", "info": info, "gol": gol, "cartellini": cartellini,
            "sostituzioni": sostituzioni, "rigori": rigori}


# =====================================================================================================
# S4 — Scheda torneo
# =====================================================================================================
def scheda_torneo(grafo, anno, genere="men", n_marcatori=5):
    """Date, ospitanti, podio, numeri del torneo, marcatori e premi."""
    info = _riga(grafo.leggi(f"""
        MATCH (t:Tournament {{year: $anno, gender: $genere}})
        OPTIONAL MATCH (m:Match)-[:inStage]->(:Stage)-[:stageOf]->(t)
        WITH t, count(m) AS partite, sum(m.homeScore + m.awayScore) AS gol
        RETURN t.uri AS uri, t.label AS torneo, t.startDate AS inizio, t.endDate AS fine, t.countTeams AS squadre,
               [(t)<-[:tournament]-(p:Participation {{isHost: true}}) | {_squadra('p')}] AS ospitanti,
               partite, gol, round(toFloat(gol) / partite, 2) AS media_gol""", anno=anno, genere=genere))
    if info is None:
        return None
    t = info["uri"]

    podio = grafo.leggi(f"""
        MATCH (:Tournament {{uri: $t}})<-[:tournament]-(p:Participation)
        WHERE p.finalPosition IS NOT NULL
        RETURN p.finalPosition AS posizione, {_squadra('p')} AS squadra ORDER BY posizione""", t=t)
    marcatori = grafo.leggi(f"""
        MATCH (:Tournament {{uri: $t}})<-[:tournament]-(pa:Participation)<-[:participation]-(g:Goal {{isOwnGoal: false}})
              -[:player]->(p:Player)
        RETURN p.label AS giocatore, {_squadra('pa')} AS squadra, count(g) AS gol
        ORDER BY gol DESC, giocatore LIMIT $n""", t=t, n=n_marcatori)
    premi = grafo.leggi(f"""
        MATCH (:Tournament {{uri: $t}})<-[:tournament]-(pa:Participation)<-[:participation]-(s:SquadMembership)
              -[:wonAward]->(a:Award), (s)-[:player]->(p:Player)
        RETURN a.label AS premio, p.label AS giocatore, {_squadra('pa')} AS squadra
        ORDER BY a.uri, giocatore""", t=t)

    return {"tipo": "S4", "info": info, "podio": podio, "marcatori": marcatori, "premi": premi}


# =====================================================================================================
# C1 — Classifica per metrica
# =====================================================================================================
# Per ogni metrica: il pattern che lega l'elemento contato (e) al giocatore (p) e alla partecipazione (pa).
# Le etichette non si possono passare come parametri Cypher, per questo il pattern si sceglie da questo
# elenco chiuso (nessun testo dell'utente entra nella query).
METRICHE = {
    "gol": "(e:Goal {isOwnGoal: false})-[:player]->(p:Player), (e)-[:participation]->(pa:Participation)",
    "gol_su_rigore": "(e:Goal {isOwnGoal: false, isPenalty: true})-[:player]->(p:Player), (e)-[:participation]->(pa:Participation)",
    "presenze": "(e:Appearance)-[:player]->(p:Player), (e)-[:participation]->(pa:Participation)",
    "presenze_da_titolare": "(e:Appearance {isStarter: true})-[:player]->(p:Player), (e)-[:participation]->(pa:Participation)",
    "gialli": "(e:Booking {isYellowCard: true})-[:player]->(p:Player), (e)-[:participation]->(pa:Participation)",
    "espulsioni": "(e:Booking {isSendingOff: true})-[:player]->(p:Player), (e)-[:participation]->(pa:Participation)",
    "premi": "(s:SquadMembership)-[e:wonAward]->(:Award), (s)-[:player]->(p:Player), (s)-[:participation]->(pa:Participation)",
    "mondiali": "(e:SquadMembership)-[:player]->(p:Player), (e)-[:participation]->(pa:Participation)",
}


def classifica(grafo, metrica, anno=None, federazione_uri=None, genere=None, n=10):
    """Primi n giocatori per la metrica, con filtri facoltativi su torneo, nazionale (con predecessori) e genere."""
    if metrica not in METRICHE:
        raise ValueError(f"Metrica sconosciuta: {metrica}. Disponibili: {list(METRICHE)}")
    feds = federazioni(grafo, federazione_uri) if federazione_uri else None
    tabella = grafo.leggi(f"""
        MATCH {METRICHE[metrica]},
              (pa)-[:tournament]->(t:Tournament), (pa)-[:team]->(:NationalTeam)-[:representsFederation]->(f:Federation)
        WHERE ($anno IS NULL OR t.year = $anno) AND ($genere IS NULL OR t.gender = $genere)
          AND ($feds IS NULL OR f.uri IN $feds)
        WITH p, count(e) AS valore, collect(DISTINCT f.label) AS squadre, min(t.year) AS dal, max(t.year) AS al
        RETURN p.uri AS uri, p.label AS giocatore, squadre, valore, dal, al
        ORDER BY valore DESC, giocatore LIMIT $n""", anno=anno, genere=genere, feds=feds, n=n)
    return {"tipo": "C1", "metrica": metrica, "filtri": {"anno": anno, "federazione": federazione_uri, "genere": genere},
            "classifica": tabella}


# =====================================================================================================
# F1 — Testa a testa tra due nazionali
# =====================================================================================================
def testa_a_testa(grafo, federazione_uri, avversario_uri, genere=None):
    """Tutte le partite tra due nazionali (predecessori compresi) e il bilancio dal punto di vista della prima.

    Il risultato è quello al 90' o dopo i supplementari; una partita decisa ai rigori conta come pareggio
    (convenzione FIFA), e i rigori si riportano a parte.
    """
    partite = cerca_partite(grafo, federazione_uri, avversario_uri, genere=genere)
    f1 = set(federazioni(grafo, federazione_uri))
    in_casa = partite["federazione_casa"].isin(f1)
    fatti = partite["gol_casa"].where(in_casa, partite["gol_trasferta"])
    subiti = partite["gol_trasferta"].where(in_casa, partite["gol_casa"])
    rig_casa, rig_trasferta = pd.to_numeric(partite["rigori_casa"]), pd.to_numeric(partite["rigori_trasferta"])
    rig_fatti = rig_casa.where(in_casa, rig_trasferta)          # vuoto se la partita non è andata ai rigori
    rig_subiti = rig_trasferta.where(in_casa, rig_casa)
    ai_rigori = partite["rigori_casa"].notna()
    bilancio = {
        "partite": len(partite),
        "vittorie": int((fatti > subiti).sum()),
        "pareggi": int((fatti == subiti).sum()),
        "sconfitte": int((fatti < subiti).sum()),
        "gol_fatti": int(fatti.sum()),
        "gol_subiti": int(subiti.sum()),
        "serie_di_rigori_vinte": int((ai_rigori & (rig_fatti > rig_subiti)).sum()),
        "serie_di_rigori_perse": int((ai_rigori & (rig_fatti < rig_subiti)).sum()),
    }
    return {"tipo": "F1", "partite": partite.drop(columns="federazione_casa"), "bilancio": bilancio}
