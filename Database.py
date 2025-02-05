import sqlite3
import Console


def read(tag_id, db_file="NFC-Tags.db"):
    sql = sqlite3.connect(db_file)
    db = sql.cursor()

    # Console.info(tag_id)
    suche = ("1",)
    db.execute("SELECT command FROM nfc_tags WHERE id=?", suche)

    result = db.fetchone()  # Ergebnis abrufen
    Console.info(result)

    sql.close()  # Verbindung schließen

    if result:  # Prüfen, ob ein Ergebnis existiert
        return result[0]
    else:
        Console.info(f"Kein Eintrag für ID {tag_id} gefunden.")
        return None  # Falls kein Eintrag existiert, None zurückgeben oder eine Fehlermeldung ausgeben
