# Specifica dell'ontologia: unica fonte da cui si generano il Turtle e le illustrazioni.
# Fonti: 1–4 = dataset 1–4, D = derivata / regola manuale

NS = "http://example.org/worldcup/ontology#"
RES = "http://example.org/worldcup/resource/"

FONTI = {
    "1": "Dataset 1 (database dei Mondiali FIFA, SQLite)",
    "2": "Dataset 2 (classifiche finali 1930-2022)",
    "3": "Dataset 3 (statistiche dei giocatori 2022)",
    "4": "Dataset 4 (immagini dei giocatori 2022)",
    "D": "Derivata o regola di integrazione",
}

# (nome, superclassi esterne, fonte, gruppo, etichetta it, commento, pattern URI)
CLASSI = [
    ("Tournament", ["schema:SportsEvent"], "1", "struttura", "Torneo",
     "Un'edizione della Coppa del Mondo FIFA, maschile o femminile.", "tournament/{tournament_id}"),
    ("Stage", [], "1", "struttura", "Fase",
     "Una fase di un torneo (girone, ottavi, quarti, ...).", "stage/{tournament_id}/{stage_number}"),
    ("Group", [], "1", "struttura", "Girone",
     "Un girone all'interno di una fase a gironi.", "group/{tournament_id}/{stage_number}/{group_letter}"),
    ("Match", ["schema:SportsEvent"], "1", "struttura", "Partita",
     "Una partita del torneo.", "match/{match_id}"),
    ("Stadium", ["schema:StadiumOrArena"], "1", "struttura", "Stadio",
     "Uno stadio che ha ospitato almeno una partita.", "stadium/{stadium_id}"),

    ("Confederation", ["schema:SportsOrganization"], "1", "squadre", "Confederazione",
     "Una confederazione continentale FIFA (UEFA, CONMEBOL, ...).", "confederation/{confederation_id}"),
    ("Federation", ["schema:SportsOrganization"], "1", "squadre", "Federazione",
     "Una federazione calcistica nazionale (il team_id del dataset 1): comune alle nazionali maschile e femminile.",
     "federation/{team_id}"),
    ("NationalTeam", ["schema:SportsTeam"], "D", "squadre", "Nazionale",
     "La nazionale maschile o femminile di una federazione.", "nationalteam/{team_id}/{gender}"),
    ("Participation", [], "1", "squadre", "Partecipazione",
     "La partecipazione di una nazionale a un torneo (es. Italia al Mondiale 2006). Nodo pivot del grafo.",
     "participation/{tournament_id}/{team_id}"),
    ("GroupStanding", [], "1", "squadre", "Classifica nel girone",
     "La posizione finale di una partecipazione in un girone.",
     "groupstanding/{tournament_id}/{stage_number}/{group_letter}/{team_id}"),

    ("Person", ["schema:Person", "foaf:Person"], "1", "persone", "Persona",
     "Una persona coinvolta nei tornei.", "-"),
    ("Player", ["wc:Person"], "1", "persone", "Giocatore", "Un calciatore convocato ad almeno un Mondiale.",
     "player/{player_id}"),
    ("Manager", ["wc:Person"], "1", "persone", "Allenatore", "Un commissario tecnico.", "manager/{manager_id}"),
    ("Referee", ["wc:Person"], "1", "persone", "Arbitro", "Un arbitro principale.", "referee/{referee_id}"),
    ("SquadMembership", [], "1", "persone", "Convocazione",
     "La convocazione di un giocatore nella rosa di una partecipazione. Porta gli attributi che dipendono dal torneo.",
     "membership/{tournament_id}/{team_id}/{player_id}"),
    ("Appearance", [], "1", "persone", "Presenza",
     "La presenza di un giocatore in una partita (dal 1970).", "appearance/{match_id}/{player_id}"),
    ("Position", ["skos:Concept"], "1", "persone", "Ruolo",
     "Ruolo di gioco come scritto nel dataset 1 (codice e nome): 4 ruoli generali nelle rose, 21 codici nelle presenze (i 4 generali e 17 specifici). Nessuna gerarchia tra i ruoli.", "wc:position_{codice}"),
    ("Award", [], "1", "persone", "Premio", "Un premio individuale (Pallone d'oro, Scarpa d'oro, ...).",
     "award/{award_id}"),

    ("MatchEvent", [], "1", "eventi", "Evento di partita", "Un evento avvenuto durante una partita.", "-"),
    ("Goal", ["wc:MatchEvent"], "1", "eventi", "Gol", "Un gol (esclusi i rigori delle serie finali).",
     "goal/{goal_id}"),
    ("Booking", ["wc:MatchEvent"], "1", "eventi", "Ammonizione o espulsione", "Un cartellino (dal 1970).",
     "booking/{booking_id}"),
    ("Substitution", ["wc:MatchEvent"], "1", "eventi", "Sostituzione",
     "Un giocatore che entra o esce per sostituzione (una riga del dataset 1 per giocatore, dal 1970).",
     "substitution/{substitution_id}"),
    ("PenaltyKick", ["wc:MatchEvent"], "1", "eventi", "Rigore della serie finale",
     "Un tiro di rigore in una serie di rigori.", "penaltykick/{penalty_kick_id}"),

    ("Club", ["schema:SportsTeam"], "3", "esterni", "Club",
     "Il club di appartenenza dichiarato dal dataset 3 (aggiornato a fine 2022).", "club/{slug_nome}"),
    ("Brand", ["schema:Brand"], "3", "esterni", "Marca",
     "Una marca di abbigliamento sportivo (sponsor tecnico o scarpe).", "brand/{slug_nome}"),
    ("Image", ["schema:ImageObject"], "4", "esterni", "Immagine",
     "Una fotografia del dataset immagini, con etichetta di giocatore non verificata.",
     "image/{player_id}/{numero_file}"),
]

# Proprieta' oggetto: (nome, dominio, range, fonte, origine nei dati, commento)
OGGETTO = [
    ("stageOf", "Stage", "Tournament", "1", "tournament_stages.tournament_id", "Il torneo a cui appartiene la fase."),
    ("groupOf", "Group", "Stage", "1", "groups.stage_number", "La fase a cui appartiene il girone."),
    ("inStage", "Match", "Stage", "D", "fase del girone ricavato (partite a gironi); matches.stage_name normalizzato al plurale (eliminazione diretta)",
     "La fase in cui si gioca la partita. Per le partite a gironi è la fase del girone ricavato dalle squadre; per quelle a eliminazione si confronta il nome della fase (quarter-final -> quarter-finals, semi-final -> semi-finals nei tornei femminili)."),
    ("inGroup", "Match", "Group", "D", "group_standings: girone che contiene entrambe le squadre nello stesso torneo",
     "Il girone della partita, ricavato dalle due squadre e non dal nome del girone (922/922 partite risolte, nessuna ambigua)."),
    ("playedAt", "Match", "Stadium", "1", "matches.stadium_id", "Lo stadio della partita."),
    ("homeTeam", "Match", "Participation", "1", "matches.home_team_id", "La squadra di casa."),
    ("awayTeam", "Match", "Participation", "1", "matches.away_team_id", "La squadra in trasferta."),
    ("refereedBy", "Match", "Referee", "1", "referee_appearances", "L'arbitro principale della partita."),

    ("memberOf", "Federation", "Confederation", "1", "teams.confederation_id / referees.confederation_id",
     "La confederazione di appartenenza (usata anche per gli arbitri)."),
    ("predecessorOf", "Federation", "Federation", "D", "regola manuale",
     "Successione riconosciuta dalla FIFA (es. West Germany -> Germany, Soviet Union -> Russia)."),
    ("representsFederation", "NationalTeam", "Federation", "D", "teams.team_id", "La federazione della nazionale."),
    ("team", "Participation", "NationalTeam", "1", "qualified_teams.team_id", "La nazionale che partecipa."),
    ("tournament", "Participation", "Tournament", "1", "qualified_teams.tournament_id", "Il torneo."),
    ("hasManager", "Participation", "Manager", "1", "manager_appointments", "Il commissario tecnico (anche più d'uno)."),
    ("kitSponsor", "Participation", "Brand", "3", "National Team Kit Sponsor", "Lo sponsor tecnico della maglia (solo 2022)."),

    ("player", "SquadMembership", "Player", "1", "squads.player_id / player_appearances / goals / ...",
     "Il giocatore a cui si riferisce il nodo (convocazione, presenza, evento)."),
    ("participation", "SquadMembership", "Participation", "1", "squads.team_id + tournament_id",
     "La partecipazione (squadra al torneo) a cui si riferisce il nodo."),
    ("position", "SquadMembership", "Position", "1", "squads.position_code", "Il ruolo nella rosa."),
    ("club", "SquadMembership", "Club", "3", "Club", "Il club dichiarato dal dataset 3 (può essere successivo al torneo)."),
    ("bootBrand", "SquadMembership", "Brand", "3", "Brand Sponsor/Brand Used", "La marca di scarpe del giocatore."),
    ("inMatch", "MatchEvent", "Match", "1", "match_id", "La partita in cui avviene l'evento o la presenza."),
    ("creditedTo", "Goal", "Participation", "1", "goals.team_id",
     "La squadra a cui è accreditato il gol (diversa da quella del giocatore negli autogol)."),
    ("inGroupStanding", "GroupStanding", "Group", "1", "group_standings", "Il girone della classifica."),
    ("wonAward", "SquadMembership", "Award", "1", "award_winners (torneo, squadra, giocatore) -> squads",
     "Premio vinto dal giocatore in quel torneo. Il premio è condiviso se nello stesso torneo è assegnato a più convocazioni."),
    ("depicts", "Image", "Player", "4", "cartella Images_<giocatore> + match_images.csv",
     "Il giocatore raffigurato secondo l'etichetta del dataset (rumorosa)."),
]

# Proprieta' dato: (nome, dominio, tipo xsd, fonte, origine, commento)
DATI = [
    ("year", "Tournament", "gYear", "1", "tournaments.year", "Anno del torneo."),
    ("gender", "Tournament", "string", "D", "tournaments.tournament_name", "\"men\" o \"women\" (anche per NationalTeam)."),
    ("startDate", "Tournament", "date", "1", "tournaments.start_date", "Data di inizio (anche per Stage)."),
    ("endDate", "Tournament", "date", "1", "tournaments.end_date", "Data di fine (anche per Stage)."),
    ("countTeams", "Tournament", "integer", "1", "tournaments.count_teams", "Numero di squadre (anche per Group)."),

    ("stageNumber", "Stage", "integer", "1", "tournament_stages.stage_number", "Numero d'ordine della fase."),
    ("stageName", "Stage", "string", "1", "tournament_stages.stage_name", "Nome della fase."),
    ("isGroupStage", "Stage", "boolean", "1", "tournament_stages.group_stage", "Vero per le fasi a gironi."),
    ("isKnockoutStage", "Stage", "boolean", "1", "tournament_stages.knockout_stage", "Vero per le fasi a eliminazione."),
    ("groupLetter", "Group", "string", "1", "groups.group_name", "Lettera o numero del girone (\"A\", \"1\")."),

    ("matchDate", "Match", "date", "1", "matches.match_date", "Data della partita."),
    ("homeScore", "Match", "integer", "1", "matches.home_team_score", "Gol della squadra di casa."),
    ("awayScore", "Match", "integer", "1", "matches.away_team_score", "Gol della squadra in trasferta."),
    ("extraTime", "Match", "boolean", "1", "matches.extra_time", "Vero se si sono giocati i supplementari."),
    ("penaltyShootout", "Match", "boolean", "1", "matches.penalty_shootout", "Vero se decisa ai rigori."),
    ("homePenalties", "Match", "integer", "1", "matches.home_team_score_penalties", "Rigori segnati dalla squadra di casa."),
    ("awayPenalties", "Match", "integer", "1", "matches.away_team_score_penalties", "Rigori segnati dalla squadra in trasferta."),
    ("isReplay", "Match", "boolean", "1", "matches.replay", "Vero se la partita è una ripetizione."),

    ("cityName", "Stadium", "string", "1", "stadiums.city_name", "Città dello stadio."),
    ("countryName", "Stadium", "string", "1", "stadiums.country_name / managers / referees", "Paese (testo)."),
    ("capacity", "Stadium", "integer", "1", "stadiums.stadium_capacity", "Capienza approssimativa."),

    ("confederationCode", "Confederation", "string", "1", "confederations.confederation_code", "Sigla (UEFA, CAF, ...)."),
    ("teamCode", "Federation", "string", "1", "teams.team_code", "Codice ISO alpha-3 (non univoco: DEU per Germania e Germania Ovest)."),
    ("regionName", "Federation", "string", "1", "teams.region_name", "Regione geografica."),

    ("performance", "Participation", "string", "1", "qualified_teams.performance", "Fase più avanzata raggiunta."),
    ("isHost", "Participation", "boolean", "1", "host_countries", "Vero se la nazionale ospitava il torneo."),
    ("finalPosition", "Participation", "integer", "1", "tournament_standings.position", "Posizione finale (solo prime 4)."),
    ("finalRank", "Participation", "integer", "2", "FIFA - <anno>.csv: Position", "Posizione nella classifica finale completa (ammette pari merito)."),
    ("fifaRanking", "Participation", "integer", "3", "FIFA Ranking", "Posizione nel ranking FIFA (solo 2022)."),

    ("isFemale", "Person", "boolean", "1", "players.female / managers / referees", "Vero per le donne."),

    ("shirtNumber", "SquadMembership", "integer", "1", "squads.shirt_number", "Numero di maglia (0 prima del 1954 = sconosciuto)."),
    ("isCaptain", "SquadMembership", "boolean", "4", "suffisso \"(captain)\" del nome cartella", "Vero per il capitano (solo 2022)."),
    ("reportedAppearances", "SquadMembership", "integer", "3", "Appearances", "Presenze secondo il dataset 3 (incomplete)."),
    ("reportedGoals", "SquadMembership", "integer", "3", "Goals Scored", "Gol secondo il dataset 3 (incompleti)."),
    ("assists", "SquadMembership", "integer", "3", "Assists Provided", "Assist (solo il dataset 3)."),
    ("dribblesPer90", "SquadMembership", "decimal", "3", "Dribbles per 90", "Dribbling ogni 90 minuti."),
    ("interceptionsPer90", "SquadMembership", "decimal", "3", "Interceptions per 90", "Intercetti ogni 90 minuti."),
    ("tacklesPer90", "SquadMembership", "decimal", "3", "Tackles per 90", "Contrasti ogni 90 minuti."),
    ("duelsWonPer90", "SquadMembership", "decimal", "3", "Total Duels Won per 90", "Duelli vinti ogni 90 minuti."),
    ("savePercentage", "SquadMembership", "decimal", "3", "Save Percentage", "Percentuale di parate (frazione 0-1)."),
    ("cleanSheetRate", "SquadMembership", "decimal", "3", "Clean Sheets", "Quota di partite senza gol subiti (frazione 0-1)."),

    ("isStarter", "Appearance", "boolean", "1", "player_appearances.starter", "Vero se titolare."),
    ("isSubstitute", "Appearance", "boolean", "1", "player_appearances.substitute", "Vero se entrato dalla panchina."),

    ("minuteRegulation", "MatchEvent", "integer", "1", "minute_regulation", "Minuto regolamentare (45, 90, 105, 120 nei recuperi)."),
    ("minuteStoppage", "MatchEvent", "integer", "1", "minute_stoppage", "Minuto di recupero (0 se nel tempo regolamentare)."),
    ("matchPeriod", "MatchEvent", "string", "1", "match_period", "Periodo (primo tempo, secondo tempo, ...)."),
    ("isOwnGoal", "Goal", "boolean", "1", "goals.own_goal", "Vero per gli autogol."),
    ("isPenalty", "Goal", "boolean", "1", "goals.penalty", "Vero per i gol su rigore in partita."),
    ("isYellowCard", "Booking", "boolean", "1", "bookings.yellow_card", "Cartellino giallo."),
    ("isRedCard", "Booking", "boolean", "1", "bookings.red_card", "Cartellino rosso."),
    ("isSecondYellow", "Booking", "boolean", "1", "bookings.second_yellow_card", "Secondo giallo."),
    ("isSendingOff", "Booking", "boolean", "1", "bookings.sending_off", "Espulsione."),
    ("isGoingOff", "Substitution", "boolean", "1", "substitutions.going_off", "Vero per il giocatore che esce."),
    ("isComingOn", "Substitution", "boolean", "1", "substitutions.coming_on", "Vero per il giocatore che entra."),
    ("isConverted", "PenaltyKick", "boolean", "1", "penalty_kicks.converted", "Vero se il rigore è segnato."),

    ("groupPosition", "GroupStanding", "integer", "1", "group_standings.position", "Posizione finale nel girone."),
    ("points", "GroupStanding", "integer", "1", "group_standings.points", "Punti nel girone (sistema dell'epoca)."),
    ("advanced", "GroupStanding", "boolean", "1", "group_standings.advanced", "Vero se qualificata alla fase successiva."),

    ("awardDescription", "Award", "string", "1", "awards.award_description", "Descrizione del premio."),
    ("yearIntroduced", "Award", "gYear", "1", "awards.year_introduced", "Anno di introduzione."),

    ("filePath", "Image", "string", "4", "images_index.path", "Percorso relativo del file."),
    ("md5", "Image", "string", "4", "images_index.md5", "Impronta del contenuto (rileva i duplicati)."),
    ("fileFormat", "Image", "string", "4", "images_index.format", "Formato reale (JPEG o PNG)."),
    ("fileSize", "Image", "integer", "4", "images_index.bytes", "Dimensione in byte."),
    ("hasDuplicateContent", "Image", "boolean", "D", "md5 ripetuto in più cartelle", "Vero se lo stesso contenuto compare per giocatori diversi."),
    ("labelConfidence", "Image", "decimal", "D", "similarità CLIP (da calcolare)", "Affidabilità dell'etichetta depicts (0-1)."),
    ("isVerified", "Image", "boolean", "D", "revisione manuale", "Vero se l'etichetta è stata controllata a mano."),
]

# Proprieta' riusate da vocabolari esterni (non ridefinite): (proprieta', usata su, commento)
RIUSATE = [
    ("rdfs:label", "tutte le classi con un nome", "Nome leggibile (torneo, squadra, persona, stadio, club, marca)."),
    ("schema:givenName", "Person", "Nome (assente per chi è noto con un solo nome)."),
    ("schema:familyName", "Person", "Cognome o nome sportivo unico."),
    ("schema:birthDate", "Person", "Data di nascita (fonte autorevole: dataset 1)."),
    ("owl:sameAs", "Player, Manager, Referee, Stadium, Federation, NationalTeam, Confederation",
     "Risorsa DBpedia corrispondente, ricavata dal link Wikipedia del dataset 1."),
    ("foaf:isPrimaryTopicOf", "come sopra", "Pagina Wikipedia della risorsa."),
    ("skos:notation", "Position", "Codice del ruolo (position_code del dataset 1)."),
    ("skos:prefLabel", "Position", "Nome del ruolo (position_name del dataset 1)."),
]

# Ruoli: (codice, nome) esattamente come nel dataset 1 (player_appearances.position_code / position_name;
# le rose usano solo i primi quattro). Nessuna etichetta o gerarchia aggiunta.
POSIZIONI = [
    ("GK", "goal keeper"), ("DF", "defender"), ("MF", "midfielder"), ("FW", "forward"),
    ("CB", "center back"), ("LB", "left back"), ("RB", "right back"),
    ("LWB", "left wing back"), ("RWB", "right wing back"), ("SW", "sweeper"),
    ("DM", "defensive midfielder"), ("CM", "center midfielder"), ("AM", "attacking midfielder"),
    ("LM", "left midfielder"), ("RM", "right midfielder"), ("CF", "center forward"),
    ("LF", "left forward"), ("RF", "right forward"), ("LW", "left winger"), ("RW", "right winger"),
    ("SS", "second striker"),
]

# Domini aggiuntivi (proprieta' usate su piu' classi): rappresentati nel Turtle con owl:unionOf
DOMINI_MULTIPLI = {
    "player": ["SquadMembership", "Appearance", "MatchEvent"],
    "participation": ["SquadMembership", "Appearance", "MatchEvent", "GroupStanding"],
    "position": ["SquadMembership", "Appearance"],
    "inMatch": ["MatchEvent", "Appearance"],
    "memberOf": ["Federation", "Referee"],
    "gender": ["Tournament", "NationalTeam"],
    "startDate": ["Tournament", "Stage"],
    "endDate": ["Tournament", "Stage"],
    "countTeams": ["Tournament", "Group"],
    "countryName": ["Stadium", "Manager", "Referee"],
    "shirtNumber": ["SquadMembership", "Appearance"],
}
