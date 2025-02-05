import sqlite3
import Console


def read(db_file):
    # Pfad übergeben lassen
    sql = sqlite3.connect(db_file)
    db = sql.cursor()

    suche = ("1",)
    db.execute("SELECT command FROM nfc_tags WHERE id=?", suche)
    # Console.info(db.fetchone()[0])
    returnvalue = db.fetchone()[0]
    sql.close()

    return returnvalue
    # print(db.fetchall())

    # Verbindung Schließen
