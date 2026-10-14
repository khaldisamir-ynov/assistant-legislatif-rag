"""Couche 3, STOCKER : base SQLite pour les données STRUCTURÉES (agenda aujourd'hui).

Pourquoi pas ChromaDB ? "Les textes examinés du 19/10 au 25/10" est une question
EXACTE (date comprise entre deux bornes) : un filtre SQL y répond sans erreur
possible, une recherche par similarité de vecteurs non. SQLite est inclus dans Python.

Test :  python -m app.stockage.sqlite 2026-10-19 2026-10-25
"""
import sqlite3

from app import config

SCHEMA = """
CREATE TABLE agenda_points (
    uid          TEXT PRIMARY KEY,
    reunion_uid  TEXT NOT NULL,
    date         TEXT NOT NULL,     -- AAAA-MM-JJ : l'ordre alphabétique est l'ordre chronologique
    heure        TEXT NOT NULL,     -- HH:MM, heure de Paris
    type_reunion TEXT NOT NULL,     -- seance | commission | autre
    chambre      TEXT,              -- "Assemblée nationale", "Sénat" ou NULL (commission)
    organe_ref   TEXT,
    eventuel     INTEGER NOT NULL,  -- 1 = inscrit sous réserve
    type_point   TEXT,
    objet        TEXT NOT NULL
);
-- Table de liaison : un point peut citer plusieurs dossiers, un dossier revient dans plusieurs points
CREATE TABLE agenda_dossiers (
    point_uid   TEXT NOT NULL REFERENCES agenda_points(uid),
    dossier_uid TEXT NOT NULL
);
CREATE INDEX idx_points_date ON agenda_points(date);
CREATE INDEX idx_dossiers_uid ON agenda_dossiers(dossier_uid);
"""


def connexion() -> sqlite3.Connection:
    con = sqlite3.connect(config.SQLITE_PATH)
    con.row_factory = sqlite3.Row  # lignes accessibles par nom de colonne
    return con


def ecrire_agenda(points: list[dict]) -> int:
    """Reconstruit les tables de l'agenda dans UNE transaction : tant qu'elle n'est pas
    validée, les lecteurs (API) voient l'ancienne version. Pas de base vide, contrairement à Chroma."""
    con = connexion()
    with con:  # BEGIN ... COMMIT (ou ROLLBACK si erreur)
        con.execute("DROP TABLE IF EXISTS agenda_dossiers")
        con.execute("DROP TABLE IF EXISTS agenda_points")
        for instruction in SCHEMA.split(";"):
            if instruction.strip():
                con.execute(instruction)
        con.executemany(
            "INSERT INTO agenda_points VALUES (:uid, :reunion_uid, :date, :heure, :type_reunion,"
            " :chambre, :organe_ref, :eventuel, :type_point, :objet)", points)
        con.executemany(
            "INSERT INTO agenda_dossiers VALUES (?, ?)",
            [(p["uid"], d) for p in points for d in p["dossiers"]])
    nb = con.execute("SELECT COUNT(*) FROM agenda_points").fetchone()[0]
    con.close()
    return nb


def points_agenda(debut: str, fin: str, chambre: str | None = None,
                  type_reunion: str | None = None, dossier: str | None = None) -> list[dict]:
    """Points de l'ordre du jour entre deux dates INCLUSES (AAAA-MM-JJ), triés chronologiquement."""
    conditions, parametres = ["p.date BETWEEN ? AND ?"], [debut, fin]
    if chambre:
        conditions.append("p.chambre = ?")
        parametres.append(chambre)
    if type_reunion:
        conditions.append("p.type_reunion = ?")
        parametres.append(type_reunion)
    if dossier:
        conditions.append("p.uid IN (SELECT point_uid FROM agenda_dossiers WHERE dossier_uid = ?)")
        parametres.append(dossier)
    # Paramètres "?" : jamais de valeur collée dans le SQL (protection contre l'injection SQL)
    sql = f"""
        SELECT p.*, GROUP_CONCAT(d.dossier_uid) AS dossiers
        FROM agenda_points p LEFT JOIN agenda_dossiers d ON d.point_uid = p.uid
        WHERE {' AND '.join(conditions)}
        GROUP BY p.uid
        ORDER BY p.date, p.heure
    """
    con = connexion()
    lignes = con.execute(sql, parametres).fetchall()
    con.close()
    return [{**dict(ligne), "eventuel": bool(ligne["eventuel"]),
             "dossiers": ligne["dossiers"].split(",") if ligne["dossiers"] else []} for ligne in lignes]


if __name__ == "__main__":
    import sys

    for p in points_agenda(sys.argv[1], sys.argv[2], chambre="Assemblée nationale"):
        reserve = " (sous réserve)" if p["eventuel"] else ""
        print(f"{p['date']} {p['heure']}  {p['objet'][:70]}{reserve}  {p['dossiers']}")
