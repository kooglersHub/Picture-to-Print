# Entwicklungszwischenstand – 7. November 2026

Auf ausdrücklichen Wunsch des Nutzers endet die Arbeit an diesem Zwischenstand.

## Bereitgestellt

- Website: https://picture-to-print-karl.timring5002.chatgpt.site/
- Modal CPU: App `picture-to-print-web`, Funktion `web`.
- Modal GPU: App `picture-to-print`, Funktion `generate_geometry`, A100 80 GB.
- Der GPU-Build ist fertig; es wurde noch kein echter Fotoauftrag ausgeführt.
- Realer Cloud-STL-Test: `8e048b4600e64fe69c7a7c845c9f33db`, Status ready,
  ZIP-Download mit 273257 Bytes erfolgreich.
- Sites-Version: `appgver_1151878ce91481918a6f5f16d146a1db`;
  separate Quellrevision `49e8c67544d6700bb232e74b3d64c4ed5830fb9d`.
- Token-Login mit begrenztem Request-Body; serverseitige Eigentümerprüfung;
  gespeicherte Modal-Aufruf-ID zur Erkennung abgebrochener Cloud-Aufträge.

## Nächste Schritte

Prüfstand vor dem Sichern: Python-Suite 34 bestanden, 1 übersprungen;
Ruff-Prüfung und Formatprüfung bestanden; Sites-Authentifizierung 6 Tests
bestanden. Die übersprungene Prüfung gehört zum optionalen Blender-Pfad.

1. Einen echten Fotoauftrag mit 512er Auflösung starten, Status, Roh-PLY,
   texturfreie Vorschau und STL/3MF-Download bis zum Ende prüfen.
   Das offizielle TRELLIS-Beispielfoto liegt lokal unter `.tools/trellis-example.png`
   im übergeordneten Workspace. Ein Hundefoto wurde noch nicht geliefert.
2. Crash-Lücke zwischen Auftragsspeicherung und Speicherung der Modal-Aufruf-ID
   behandeln: Ohne `dispatch.json` kann ein Cloud-Auftrag hängenbleiben.
   Geeignete Altersgrenzen und Schutz vor verspätet startenden Workern testen.
3. Doppelte ältere CPU-Funktionen `run_job` und `web` aus `modal_app.py`
   entfernen; produktiver CPU-Einstieg ist bereits `modal_backend.py`.
4. Tokenrotation mit stabiler Eigentümerkennung planen: Aktuell ist die Kennung
   der Token-Hash; ein anderer Token blendet die alten Aufträge aus.
5. Unabhängiges Review der Recovery-Korrekturen und GPU-Ergebnisse abschließen.
6. Erst nach dem echten Foto-End-to-End-Test die Funktion als vollständig geprüft
   bezeichnen und den Entwicklungs-PR integrieren.

Keine geheimen Token in dieses Dokument eintragen. Modal-Zugang liegt im
Benutzerprofil; Sites- und Modal-Secrets sind bereits im Cloud-Konto eingerichtet.
Ein tokenbesitzender Besucher kann kostenpflichtige GPU-Aufträge starten;
maximal drei aktive Aufträge pro Eigentümer, kein automatischer GPU-Retry.
Vor einem Shopbetrieb fehlen unter anderem kundenbezogene Zugänge, Abrechnung
und verbindliche Prüfung der tatsächlichen Druckbarkeit.
