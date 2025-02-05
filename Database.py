import sqlite3
import Console


def read(tag_id, db_file="NFC-Tags.db"):
    # Pfad übergeben lassen
    sql = sqlite3.connect(db_file)
    db = sql.cursor()

    db.execute("SELECT command FROM nfc_tags WHERE id=?", tag_id)
    # Console.info(db.fetchone()[0])
    returnvalue = db.fetchone()[0]
    sql.close()

    return returnvalue
    # print(db.fetchall())

    # Verbindung Schließen
