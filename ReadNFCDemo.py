import nfc


def read_tag(tag):
    # Überprüfe, ob der Tag NDEF-Nachrichten enthält
    if tag.ndef:
        print("NDEF Tag gefunden")
        for record in tag.ndef.records:
            print("Record gefunden:")
            print("  Typ:", record.type)
            print("  Daten:", record.data)
            try:
                print("  Text:", record.text)
            except AttributeError:
                # Dieser Fehler tritt auf, wenn der Record keinen Text enthält
                print("  Kein Text verfügbar in diesem Record.")
    else:
        print("Dieser Tag ist kein NDEF Tag.")


def main():
    with nfc.ContactlessFrontend("usb") as clf:
        # Startet die Schleife, die auf das Auflegen eines Tags wartet
        print("Warte auf einen NFC-Tag...")
        clf.connect(rdwr={"on-connect": read_tag})


if __name__ == "__main__":
    main()
