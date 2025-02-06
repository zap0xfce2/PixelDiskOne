import sqlite3
import Notification


def read(tag_id, db_file="NFC-Tags.db"):
    sql = sqlite3.connect(db_file)
    db = sql.cursor()

    suche = (tag_id,)
    db.execute("SELECT command FROM nfc_tags WHERE id=?", suche)

    result = db.fetchone()
    sql.close()

    if result:
        return result[0]
    else:
        Notification.send(
            "Datensatz nicht gefunden",
            f"Es existiert kein Datenbankeintrag für die ID {tag_id}!",
            "dialog-warning",
        )
        return None
