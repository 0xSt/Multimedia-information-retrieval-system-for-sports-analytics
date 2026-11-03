"""Descrizioni dei nodi in linguaggio naturale (verbalizzazione del knowledge graph).

Per ognuna delle sei classi principali (Player, Participation, Match, Federation, Club, Stadium) ogni nodo
riceve una frase in inglese, costruita con una frase-modello riempita con i dati del grafo. Le frasi si
trasformano poi in vettori (embedding.py) e servono a trovare un'entità descritta senza il suo nome
(tipo R1: "Croatian midfielder who won the Golden Ball in 2018" → Luka Modrić).

Il lavoro è diviso in due parti:
1. leggi_dati(): poche query Cypher "in blocco" (una per tipo di dato, non una per nodo), in sola lettura;
2. descrizioni(): le frasi, costruite in Python dalle tabelle lette. 
"""
from collections import Counter

import pandas as pd

from .modelli import _squadra                         # nome della nazionale dall'etichetta della partecipazione

# Query in blocco: ognuna restituisce una tabella; le frasi si compongono in Python
QUERY = {
    "tornei": """
        MATCH (t:Tournament)
        RETURN t.uri AS uri, t.label AS torneo, t.year AS anno, t.gender AS genere,
               EXISTS { (:Appearance)-[:participation]->(:Participation)-[:tournament]->(t) } AS con_presenze""",

    "giocatori": """
        MATCH (p:Player)
        RETURN p.uri AS uri, p.label AS nome, p.isFemale AS donna, p.birthDate AS nascita""",

    # una riga per convocazione: squadra, ruolo, premi, capitano, club e scarpe (2022), presenze e gol
    "convocazioni": f"""
        MATCH (p:Player)<-[:player]-(s:SquadMembership)-[:participation]->(pa:Participation)-[:tournament]->(t:Tournament)
        RETURN p.uri AS uri, t.year AS anno, t.gender AS genere, {_squadra('pa')} AS squadra,
               pa.finalPosition AS posizione_squadra, head([(s)-[:position]->(r) | r.notation]) AS ruolo,
               s.isCaptain AS capitano, [(s)-[:wonAward]->(a) | a.label] AS premi,
               head([(s)-[:club]->(c) | c.label]) AS club, head([(s)-[:bootBrand]->(b) | b.label]) AS scarpe,
               COUNT {{ (p)<-[:player]-(:Appearance)-[:participation]->(pa) }} AS presenze,
               COUNT {{ (p)<-[:player]-(:Goal {{isOwnGoal: false}})-[:participation]->(pa) }} AS gol,
               COUNT {{ (p)<-[:player]-(:Goal {{isOwnGoal: false, isPenalty: true}})-[:participation]->(pa) }} AS rigori""",

    "partecipazioni": f"""
        MATCH (pa:Participation)-[:tournament]->(t:Tournament),
              (pa)-[:team]->(:NationalTeam)-[:representsFederation]->(f:Federation)
        RETURN pa.uri AS uri, {_squadra('pa')} AS squadra, f.uri AS federazione, t.label AS torneo,
               t.year AS anno, t.gender AS genere, pa.performance AS fase, pa.finalPosition AS posizione,
               pa.isHost AS ospitante, pa.fifaRanking AS ranking_fifa,
               [(pa)-[:hasManager]->(m) | m.label] AS allenatori,
               head([(pa)-[:kitSponsor]->(b) | b.label]) AS sponsor,
               [(pa)<-[:participation]-(s:SquadMembership {{isCaptain: true}})-[:player]->(c) | c.label] AS capitani""",

    # head([...]): stadio e arbitro con un'espressione di pattern, così una partita senza arbitro resta
    "partite": f"""
        MATCH (m:Match)-[:inStage]->(s:Stage)-[:stageOf]->(t:Tournament),
              (m)-[:homeTeam]->(h:Participation), (m)-[:awayTeam]->(a:Participation)
        RETURN m.uri AS uri, t.label AS torneo, t.year AS anno, t.gender AS genere, s.stageName AS fase,
               head([(m)-[:inGroup]->(g) | g.groupLetter]) AS girone, m.matchDate AS data,
               h.uri AS casa_uri, {_squadra('h')} AS casa, a.uri AS trasferta_uri, {_squadra('a')} AS trasferta,
               m.homeScore AS gol_casa, m.awayScore AS gol_trasferta, m.extraTime AS supplementari,
               m.homePenalties AS rigori_casa, m.awayPenalties AS rigori_trasferta, m.isReplay AS ripetizione,
               head([(m)-[:playedAt]->(st) | st.uri]) AS stadio_uri, head([(m)-[:playedAt]->(st) | st.label]) AS stadio,
               head([(m)-[:playedAt]->(st) | st.cityName]) AS citta, head([(m)-[:refereedBy]->(r) | r.label]) AS arbitro""",

    # a_favore = squadra a cui va il gol (creditedTo): diversa da quella del giocatore solo negli autogol
    "gol": """
        MATCH (g:Goal)-[:inMatch]->(m:Match), (g)-[:player]->(p:Player), (g)-[:creditedTo]->(c:Participation)
        RETURN m.uri AS partita, c.uri AS a_favore, p.label AS giocatore, g.minuteRegulation AS minuto,
               g.minuteStoppage AS recupero, g.isPenalty AS rigore, g.isOwnGoal AS autogol""",

    "espulsioni": """
        MATCH (b:Booking {isSendingOff: true})-[:inMatch]->(m:Match), (b)-[:player]->(p:Player)
        RETURN m.uri AS partita, p.label AS giocatore, b.minuteRegulation AS minuto, b.minuteStoppage AS recupero""",

    "federazioni": """
        MATCH (f:Federation)
        RETURN f.uri AS uri, f.label AS nome, f.altLabel AS nome_ufficiale, f.regionName AS regione,
               head([(f)-[:memberOf]->(c) | c.label]) AS confederazione,
               head([(f)-[:memberOf]->(c) | c.confederationCode]) AS sigla,
               [(x)-[:predecessorOf]->(f) | x.label] AS predecessori,
               [(f)-[:predecessorOf]->(x) | x.label] AS successori""",

    "club": """
        MATCH (c:Club)
        RETURN c.uri AS uri, c.label AS nome""",

    "giocatori_club": f"""
        MATCH (c:Club)<-[:club]-(s:SquadMembership)-[:player]->(p:Player),
              (s)-[:participation]->(pa:Participation)-[:tournament]->(t:Tournament)
        RETURN c.uri AS uri, t.year AS anno, p.label AS giocatore, {_squadra('pa')} AS squadra,
               COUNT {{ (p)<-[:player]-(:Goal {{isOwnGoal: false}})-[:participation]->(pa) }} AS gol""",

    "stadi": """
        MATCH (st:Stadium)
        RETURN st.uri AS uri, st.label AS nome, st.cityName AS citta, st.countryName AS paese,
               st.capacity AS capienza""",
}

RUOLI = {"GK": "goalkeeper", "DF": "defender", "MF": "midfielder", "FW": "forward"}
PODIO = {1: "world champion", 2: "runner-up", 3: "third place", 4: "fourth place"}


# helper functions
def _vuoto(x):
    """True se il valore manca (None, NaN, NA di pandas)."""
    try:
        return x is None or bool(pd.isna(x))
    except (TypeError, ValueError):            # liste e simili: non sono "mancanti"
        return False


def _vero(x):
    """True solo per un valore booleano vero (anche numpy.bool_); False per falso o mancante."""
    return not _vuoto(x) and bool(x)


def elenco(voci):
    """["a", "b", "c"] → "a, b and c"."""
    voci = [str(v) for v in voci]
    return voci[0] if len(voci) == 1 else ", ".join(voci[:-1]) + " and " + voci[-1]


def plurale(n, parola, plurale_=None):
    """1 goal, 2 goals; 1 match, 2 matches."""
    return f"{n} {parola if n == 1 else (plurale_ or parola + 's')}"


def minuto(m, recupero):
    """23 → "23'"; 90 e 3 di recupero → "90+3'"."""
    if _vuoto(m):
        return ""
    m = int(m)
    return f"{m}+{int(recupero)}'" if not _vuoto(recupero) and int(recupero) > 0 else f"{m}'"


def _testo(x):
    """Un valore di testo che può arrivare da n10s come stringa o come lista di stringhe."""
    if _vuoto(x):
        return None
    if isinstance(x, (list, tuple)):
        return x[0] if x else None
    return str(x)


# =====================================================================================================
# Player
# =====================================================================================================
def testo_giocatore(g, conv, con_presenze):
    """g: riga di "giocatori" (dizionario); conv: sue convocazioni (lista di dizionari, righe di "convocazioni");
    con_presenze: {(anno, genere): bool}, se il dataset 1 registra le presenze di quel torneo.

    Si lavora con liste di dizionari e non con DataFrame: le funzioni si chiamano 10.401 volte e i DataFrame
    piccoli sono lenti da filtrare (circa 60 s contro pochi secondi).
    """
    lui = "She" if _vero(g["donna"]) else "He"
    conv = sorted(conv, key=lambda c: c["anno"])
    squadre = list(dict.fromkeys(c["squadra"] for c in conv))      # nell'ordine dei tornei, senza ripetizioni
    ruoli = Counter(c["ruolo"] for c in conv if not _vuoto(c["ruolo"]))
    frase = g["nome"] + ", " + (RUOLI.get(ruoli.most_common(1)[0][0], "player") if ruoli else "football player")
    if squadre:
        frase += " for " + elenco(squadre)
    # le date al 1° gennaio 1900 sono segnaposto della fonte
    if not _vuoto(g["nascita"]) and g["nascita"].year != 1900:
        frase += f", born in {g['nascita'].year}"
    frasi = [frase + "."]
    if not conv:
        return frasi[0]

    anni = [int(c["anno"]) for c in conv]
    mondiale = "women's World Cup" if _vero(g["donna"]) else "World Cup"
    frasi.append(f"{lui} played {plurale(len(anni), mondiale)}: {elenco(anni)}.")

    # presenze solo se tutti i suoi tornei le registrano; i gol esistono per tutti i tornei
    gol, rigori = sum(int(c["gol"]) for c in conv), sum(int(c["rigori"]) for c in conv)
    numeri = []
    if all(con_presenze.get((int(c["anno"]), c["genere"]), False) for c in conv):
        numeri.append(plurale(sum(int(c["presenze"]) for c in conv), "appearance"))
    numeri.append("no goals" if gol == 0 else
                  plurale(gol, "goal") + (f" ({plurale(rigori, 'penalty', 'penalties')})" if rigori else ""))
    frase = elenco(numeri)
    if len(anni) > 1 and gol:
        frase += ": " + ", ".join(f"{int(c['gol'])} in {int(c['anno'])}" for c in conv if c["gol"] > 0)
    frasi.append(frase[0].upper() + frase[1:] + ".")

    for pos, parola in PODIO.items():
        anni_pos = [int(c["anno"]) for c in conv if not _vuoto(c["posizione_squadra"]) and int(c["posizione_squadra"]) == pos]
        if anni_pos:
            frasi.append(f"{parola[0].upper() + parola[1:]} in {elenco(anni_pos)}.")
    premi = [f"{p} {int(c['anno'])}" for c in conv for p in sorted(c["premi"])]
    if premi:
        frasi.append(f"Awards: {elenco(premi)}.")
    for c in conv:
        if _vero(c["capitano"]):
            frasi.append(f"Captain of {c['squadra']} in {int(c['anno'])}.")
    for c in conv:
        if not _vuoto(c["club"]):
            frasi.append(f"Club at the {int(c['anno'])} World Cup: {c['club']}.")
        if not _vuoto(c["scarpe"]):
            frasi.append(f"Boots: {c['scarpe']}.")
    return " ".join(frasi)


# =====================================================================================================
# Match
# =====================================================================================================
def _marcatori(gol):
    """Gol di una squadra, raggruppati per giocatore nell'ordine del primo gol:
    "Kylian Mbappé 3 (80' penalty, 81', 118' penalty)"; un autogol è "Manuel Rosas (52' own goal)"."""
    gruppi = {}
    for r in gol.sort_values(["minuto", "recupero"]).itertuples():
        nota = " own goal" if _vero(r.autogol) else (" penalty" if _vero(r.rigore) else "")
        gruppi.setdefault(r.giocatore, []).append(minuto(r.minuto, r.recupero) + nota)
    voci = []
    for nome, minuti in gruppi.items():
        conteggio = f" {len(minuti)}" if len(minuti) > 1 else ""
        voci.append(f"{nome}{conteggio} ({', '.join(minuti)})")
    return ", ".join(voci)


def testo_partita(m, gol, espulsioni):
    """m: riga di "partite"; gol ed espulsioni: righe della partita."""
    if m["fase"] == "group stage" and not _vuoto(m["girone"]):
        fase = f"group stage (Group {m['girone']})"
    else:
        fase = m["fase"]
    frase = f"{m['casa']} vs {m['trasferta']}, {fase} of the {m['torneo']}"
    if not _vuoto(m["data"]):
        frase += f", played on {m['data'].day} {m['data']:%B %Y}"
    if not _vuoto(m["stadio"]):
        frase += f" at {m['stadio']}" + (f", {m['citta']}" if not _vuoto(m["citta"]) else "")
    frasi = [frase + "."]

    gc, gt = int(m["gol_casa"]), int(m["gol_trasferta"])
    frase = f"Result: {m['casa']} {gc}-{gt} {m['trasferta']}" + (" after extra time" if _vero(m["supplementari"]) else "")
    if gc != gt:
        frase += f"; {m['casa'] if gc > gt else m['trasferta']} won."
    elif not _vuoto(m["rigori_casa"]):
        rc, rt = int(m["rigori_casa"]), int(m["rigori_trasferta"])
        frase += f"; {m['casa'] if rc > rt else m['trasferta']} won {max(rc, rt)}-{min(rc, rt)} on penalties."
    else:
        frase += "; draw."
    frasi.append(frase)
    if _vero(m["ripetizione"]):
        frasi.append("Replay of a drawn match.")

    for uri, squadra in [(m["casa_uri"], m["casa"]), (m["trasferta_uri"], m["trasferta"])]:
        g = gol[gol["a_favore"] == uri]
        if len(g):
            frasi.append(f"Goals for {squadra}: {_marcatori(g)}.")
    tripletta = gol[~gol["autogol"].map(_vero).astype(bool)].groupby("giocatore").size()
    if (tripletta >= 3).any():
        frasi.append(f"Hat-trick by {elenco(sorted(tripletta[tripletta >= 3].index))}.")
    if len(espulsioni):
        frasi.append("Sent off: " + ", ".join(f"{r.giocatore} ({minuto(r.minuto, r.recupero)})"
                                               for r in espulsioni.sort_values("minuto").itertuples()) + ".")
    if not _vuoto(m["arbitro"]):
        frasi.append(f"Referee: {m['arbitro']}.")
    return " ".join(frasi)


# =====================================================================================================
# Participation
# =====================================================================================================
def bilancio(partite, uri):
    """Vittorie, pareggi, sconfitte, gol fatti e subiti di una partecipazione (rigori = pareggio, come in F1)."""
    casa, fuori = partite[partite["casa_uri"] == uri], partite[partite["trasferta_uri"] == uri]
    fatti = pd.concat([casa["gol_casa"], fuori["gol_trasferta"]]).astype(int).to_numpy()
    subiti = pd.concat([casa["gol_trasferta"], fuori["gol_casa"]]).astype(int).to_numpy()
    return {"partite": len(fatti), "vittorie": int((fatti > subiti).sum()), "pareggi": int((fatti == subiti).sum()),
            "sconfitte": int((fatti < subiti).sum()), "fatti": int(fatti.sum()), "subiti": int(subiti.sum())}


def testo_partecipazione(pa, partite, gol):
    """pa: riga di "partecipazioni"; partite: le sue partite (in casa o in trasferta); gol: i gol a suo favore."""
    pos = None if _vuoto(pa["posizione"]) else int(pa["posizione"])
    if pos == 1:
        esito = "world champions, won the final"
    elif pos == 2:
        esito = "runners-up, lost the final"
    elif pos in (3, 4):
        esito = PODIO[pos]
    else:
        esito = f"eliminated in the {pa['fase']}"
    frasi = [f"{pa['squadra']} at the {pa['torneo']}: {esito}."]
    if _vero(pa["ospitante"]):
        frasi.append("Host nation.")
    allenatori = list(pa["allenatori"])
    if allenatori:
        frasi.append(f"{'Manager' if len(allenatori) == 1 else 'Managers'}: {elenco(sorted(allenatori))}.")
    b = bilancio(partite, pa["uri"])
    if b["partite"]:
        frasi.append(f"{plurale(b['partite'], 'match', 'matches')}: {plurale(b['vittorie'], 'win')}, "
                     f"{plurale(b['pareggi'], 'draw')}, {plurale(b['sconfitte'], 'loss', 'losses')}; "
                     f"{plurale(b['fatti'], 'goal')} scored, {b['subiti']} conceded.")
    propri = gol[(gol["a_favore"] == pa["uri"]) & (~gol["autogol"].map(_vero).astype(bool))]
    if len(propri):
        conteggi = propri.groupby("giocatore").size().reset_index(name="n").sort_values(["n", "giocatore"],
                                                                                        ascending=[False, True])
        frasi.append("Top scorers: " + ", ".join(f"{r.giocatore} {r.n}" for r in conteggi.head(3).itertuples()) + ".")
    capitani = list(pa["capitani"])
    if capitani:
        frasi.append(f"Captain: {elenco(sorted(capitani))}.")
    if not _vuoto(pa["ranking_fifa"]):
        frasi.append(f"FIFA ranking: {int(pa['ranking_fifa'])}.")
    if not _vuoto(pa["sponsor"]):
        frasi.append(f"Kit sponsor: {pa['sponsor']}.")
    return " ".join(frasi)


# =====================================================================================================
# Federation
# =====================================================================================================
# Ordine delle fasi, per il miglior risultato di una nazionale che non è mai arrivata tra le prime 4
ORDINE_FASI = {"group stage": 1, "second group stage": 2, "round of 16": 3, "quarter-finals": 4,
               "semi-finals": 5, "final round": 5, "third-place match": 5, "final": 6}


def testo_federazione(f, partecipazioni):
    """f: riga di "federazioni"; partecipazioni: le sue righe di "partecipazioni"."""
    frase = f["nome"]
    ufficiale = _testo(f["nome_ufficiale"])
    if ufficiale and ufficiale != f["nome"]:
        frase += f" ({ufficiale})"
    frase += ", national football federation"
    if not _vuoto(f["regione"]):
        frase += f" from {f['regione']}"
    if not _vuoto(f["confederazione"]):
        frase += f", member of {f['sigla']} ({f['confederazione']})"
    frasi = [frase + "."]
    if list(f["predecessori"]):
        frasi.append(f"Successor of {elenco(sorted(f['predecessori']))}.")
    if list(f["successori"]):
        frasi.append(f"Predecessor of {elenco(sorted(f['successori']))}.")

    for genere, squadra in [("men", "Men's national team"), ("women", "Women's national team")]:
        p = partecipazioni[partecipazioni["genere"] == genere].sort_values("anno")
        if p.empty:
            continue
        anni = p["anno"].astype(int)
        parti = [f"{plurale(len(p), 'World Cup')} between {anni.min()} and {anni.max()}"
                 if len(p) > 1 else f"1 World Cup, in {anni.min()}"]
        posizioni = p["posizione"].map(lambda x: None if _vuoto(x) else int(x))
        for pos, parola in [(1, "world champions"), (2, "runners-up"), (3, "third place"), (4, "fourth place")]:
            a = anni[posizioni == pos]
            if len(a):
                parti.append(f"{parola} in {elenco(a)}")
        if posizioni.isna().all():
            migliore = max(p["fase"], key=lambda x: ORDINE_FASI.get(x, 0))
            parti.append(f"best result: {migliore}")
        ospite = anni[p["ospitante"].map(_vero).astype(bool)]
        if len(ospite):
            parti.append(f"hosted the World Cup in {elenco(ospite)}")
        frasi.append(f"{squadra}: {'; '.join(parti)}.")
    return " ".join(frasi)


# =====================================================================================================
# Club e Stadium
# =====================================================================================================
def testo_club(c, giocatori, massimo=12):
    """c: riga di "club"; giocatori: sue righe di "giocatori_club" (solo Mondiale 2022, dataset 3)."""
    frasi = [f"{c['nome']}, football club."]
    for anno, g in giocatori.groupby("anno"):
        g = g.sort_values(["gol", "giocatore"], ascending=[False, True])
        voci = [f"{r.giocatore} ({r.squadra}{', ' + plurale(int(r.gol), 'goal') if r.gol else ''})"
                for r in g.head(massimo).itertuples()]
        altri = f" and {len(g) - massimo} more" if len(g) > massimo else ""
        frasi.append(f"{plurale(len(g), 'player')} at the {int(anno)} World Cup: {', '.join(voci)}{altri}.")
        if g["gol"].sum():
            frasi.append(f"Goals by its players at the {int(anno)} World Cup: {int(g['gol'].sum())}.")
    return " ".join(frasi)


def testo_stadio(s, partite):
    """s: riga di "stadi"; partite: le partite giocate nello stadio."""
    frase = f"{s['nome']}, football stadium"
    luogo = [x for x in (s["citta"], s["paese"]) if not _vuoto(x)]
    if luogo:
        frase += " in " + ", ".join(luogo)
    if not _vuoto(s["capienza"]):
        frase += f", capacity {int(s['capienza']):,}"
    frasi = [frase + "."]
    if len(partite):
        tornei = []
        for genere, nome in [("men", "men's"), ("women", "women's")]:
            anni = sorted(partite.loc[partite["genere"] == genere, "anno"].astype(int).unique())
            if anni:
                tornei.append(f"{nome} {elenco(anni)}")
        frasi.append(f"Hosted {plurale(len(partite), 'World Cup match', 'World Cup matches')} ({'; '.join(tornei)}).")
        finali = sorted(partite.loc[partite["fase"] == "final", "anno"].astype(int))
        if finali:
            frasi.append(f"Venue of the {'final' if len(finali) == 1 else 'finals'} of {elenco(finali)}.")
        # 1950: nessuna finale, il titolo si decise in un girone finale ("final round")
        girone_finale = sorted(partite.loc[partite["fase"] == "final round", "anno"].astype(int).unique())
        if girone_finale:
            frasi.append(f"Venue of final round matches in {elenco(girone_finale)}.")
    return " ".join(frasi)


# =====================================================================================================
# Tutte le descrizioni
# =====================================================================================================
def leggi_dati(grafo):
    """Esegue le query in blocco (sola lettura) e restituisce un dizionario nome → DataFrame."""
    return {nome: grafo.leggi(q) for nome, q in QUERY.items()}


def descrizioni(dati):
    """Dalle tabelle di leggi_dati() a un DataFrame con colonne uri, classe, nome, descrizione."""
    righe = []
    con_presenze = {(int(a), g): bool(c) for a, g, c in
                    zip(dati["tornei"]["anno"], dati["tornei"]["genere"], dati["tornei"]["con_presenze"])}
    conv = {}
    for c in dati["convocazioni"].to_dict("records"):
        conv.setdefault(c["uri"], []).append(c)
    for g in dati["giocatori"].to_dict("records"):
        righe.append(("Player", g["uri"], g["nome"], testo_giocatore(g, conv.get(g["uri"], []), con_presenze)))

    partite, gol, esp = dati["partite"], dati["gol"], dati["espulsioni"]
    gol_per_partita, esp_per_partita = dict(tuple(gol.groupby("partita"))), dict(tuple(esp.groupby("partita")))
    for m in partite.to_dict("records"):
        nome = f"{m['casa']} vs {m['trasferta']} ({m['anno']}, {m['fase']})"
        righe.append(("Match", m["uri"], nome,
                      testo_partita(m, gol_per_partita.get(m["uri"], gol.iloc[0:0]),
                                    esp_per_partita.get(m["uri"], esp.iloc[0:0]))))

    # partite e gol già divisi per partecipazione: filtrare le tabelle intere 625 volte sarebbe lento
    per_pa = {}
    for colonna in ("casa_uri", "trasferta_uri"):
        for uri, parte in partite.groupby(colonna):
            per_pa.setdefault(uri, []).append(parte)
    gol_per_pa = dict(tuple(gol.groupby("a_favore")))
    for pa in dati["partecipazioni"].to_dict("records"):
        sue = pd.concat(per_pa[pa["uri"]]) if pa["uri"] in per_pa else partite.iloc[0:0]
        righe.append(("Participation", pa["uri"], f"{pa['squadra']} at the {pa['torneo']}",
                      testo_partecipazione(pa, sue, gol_per_pa.get(pa["uri"], gol.iloc[0:0]))))

    per_fed = dict(tuple(dati["partecipazioni"].groupby("federazione")))
    for f in dati["federazioni"].to_dict("records"):
        righe.append(("Federation", f["uri"], f["nome"],
                      testo_federazione(f, per_fed.get(f["uri"], dati["partecipazioni"].iloc[0:0]))))

    per_club = dict(tuple(dati["giocatori_club"].groupby("uri")))
    for c in dati["club"].to_dict("records"):
        righe.append(("Club", c["uri"], c["nome"], testo_club(c, per_club.get(c["uri"], dati["giocatori_club"].iloc[0:0]))))

    per_stadio = dict(tuple(partite.groupby("stadio_uri")))
    for s in dati["stadi"].to_dict("records"):
        righe.append(("Stadium", s["uri"], s["nome"], testo_stadio(s, per_stadio.get(s["uri"], partite.iloc[0:0]))))

    return pd.DataFrame(righe, columns=["classe", "uri", "nome", "descrizione"])


def crea_descrizioni(grafo):
    """Descrizioni di tutti i nodi delle sei classi, lette dal grafo."""
    return descrizioni(leggi_dati(grafo))
