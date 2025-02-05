import sqlite3
import Console
import re


def read(tag_id, db_file="NFC-Tags.db"):
    sql = sqlite3.connect(db_file)
    db = sql.cursor()

    # Entfernt alle nicht-alphanumerischen Zeichen
    tag_id = re.sub(r"\W+", "", tag_id)
    suche = (tag_id,)
    db.execute("SELECT command FROM nfc_tags WHERE id=?", suche)

    result = db.fetchone()  # Ergebnis abrufen

    sql.close()  # Verbindung schließen

    if result:  # Prüfen, ob ein Ergebnis existiert
        return result[0]
    else:
        Console.info(f"Kein Eintrag für ID {tag_id} gefunden.")
        return None  # Falls kein Eintrag existiert, None zurückgeben oder eine Fehlermeldung ausgeben
