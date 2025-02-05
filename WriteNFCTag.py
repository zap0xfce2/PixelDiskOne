import nfc
from nfc.ndef import Message, TextRecord  # Korrekte Art, um NDEF-Records zu erstellen


def format_tag(tag):
    """Löscht den NFC-Tag (setzt ihn zurück)"""
    if tag.ndef:
        try:
            tag.ndef.records = []  # Löscht alle bestehenden NDEF-Daten
            print("Tag erfolgreich formatiert (alle Daten gelöscht).")
        except Exception as e:
            print("Fehler beim Formatieren des Tags:", e)
    else:
        print("Dieser Tag unterstützt kein NDEF.")


def write_text_to_tag(tag, text="demo-test"):
    """Schreibt einen Text in den NFC-Tag"""
    if tag.ndef:
        record = TextRecord(text)  # Erstellt eine neue NDEF-Textnachricht
        tag.ndef.records = Message([record])  # Schreibt die Nachricht auf den Tag
        print(f'Text "{text}" erfolgreich auf den Tag geschrieben.')
    else:
        print("Dieser Tag unterstützt kein NDEF.")


def on_connect(tag):
    """Wird aufgerufen, wenn ein NFC-Tag erkannt wird"""
    print("Tag erkannt!")
    format_tag(tag)  # Zuerst den Tag löschen
    write_text_to_tag(tag)  # Dann neuen Text schreiben


def main():
    with nfc.ContactlessFrontend("usb") as clf:
        print("Warte auf einen NFC-Tag...")
        clf.connect(rdwr={"on-connect": on_connect})


if __name__ == "__main__":
    main()
