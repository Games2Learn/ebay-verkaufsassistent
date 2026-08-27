# eBay Verkaufsassistent

Browserbasierter Verkaufsassistent für schnelles Einstellen von eBay-Artikeln.

## Aktueller Stand

- Artikel per Handy/Browser fotografieren
- mehrere Fotos pro Artikel
- KI analysiert Fotos und schlägt Titel, Beschreibung, Zustand und Preis vor
- lokale Artikelverwaltung mit SQLite
- eBay OAuth für Sandbox/Production vorbereitet
- Sandbox-Bereitschaftscheck für Inventar-Standort sowie Zahlungs-, Versand- und Rückgaberichtlinien
- LIVE-Veröffentlichung bleibt bis zur vollständigen Einrichtung bewusst gesperrt

## Lokal starten

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python app.py
```

Danach im Browser öffnen:

`http://localhost:5055`

## OpenAI einrichten

In `.env` eintragen:

```env
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5-mini
```

API-Schlüssel niemals in GitHub committen.

## eBay Sandbox einrichten

1. Im eBay Developer Program Sandbox-Keyset anlegen.
2. OAuth Redirect URI / RuName konfigurieren. Der hinterlegte Redirect muss auf `/ebay/callback` der laufenden App zeigen.
3. Die Werte lokal in `.env` eintragen:

```env
EBAY_ENV=sandbox
EBAY_CLIENT_ID=...
EBAY_CLIENT_SECRET=...
EBAY_RUNAME=...
```

4. App starten und unter **eBay Einrichtung** auf **Mit eBay Sandbox verbinden** klicken.
5. Die App prüft anschließend, ob mindestens ein Inventar-Standort sowie Zahlungs-, Versand- und Rückgaberichtlinien vorhanden sind.

## Sicherheit

`.env`, Datenbank und Uploads gehören nicht ins öffentliche Repository. Produktionszugangsdaten nur als Secret/Environment Variable des Hostings hinterlegen.

## Nächster Schritt

Nach erfolgreichem Sandbox-Setup: Kategorieermittlung, Bild-Upload zu eBay, `Inventory Item` + `Offer` erzeugen und erst danach den separaten `Publish`-Schritt freischalten.
