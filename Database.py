import sqlite3
import Console


def read(tag_id, db_file="NFC-Tags.db"):
    sql = sqlite3.connect(db_file)
    db = sql.cursor()

    Console.info(tag_id)
    suche = (tag_id,)
    db.execute("SELECT command FROM nfc_tags WHERE id=?", suche)
    # Console.info(db.fetchone()[0])
    returnvalue = db.fetchone()[0]
    # Verbindung Schließen
    sql.close()

    return returnvalue
