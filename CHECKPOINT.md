# Projektstand – 7. November 2026

## Website und Cloud

- Website: https://picture-to-print-karl.timring5002.chatgpt.site/
- Modal CPU: App `picture-to-print-web`, Funktion `web` und Worker `process_job`.
- Modal GPU: App `picture-to-print`, Funktion `generate_geometry`, A100 80 GB.
- Sites-Quellrevision: `21d1c8594081cf8ce624807fe8d87c684112d516`.
- Veröffentlicht: Sites-Version `appgver_3680eb6832ac8191b628487c42a5c8e5`.
- Token-Login mit begrenztem Request-Body, HttpOnly-Sitzung, serverseitiger
  Eigentümerprüfung und privatem Backend-Bearer. Keine Geheimnisse im Repository.
- Die Website erlaubt MeshLib und Blender; Vergleiche verwenden dieselbe Roh-PLY,
  physische Größe und Voxelauflösung ohne erneuten GPU-Aufruf.
- Die vorher doppelt bereitgestellten CPU-Funktionen in `modal_app.py` sind entfernt.
- Abgebrochene Modal-Aufträge werden anhand der gespeicherten Aufruf-ID erkannt.
  Verlorene IDs haben eine begrenzte Wartezeit; verspätete Worker starten einen
  bereits beendeten Auftrag nicht erneut.

## Nachweise

- Python-Suite: 45 Tests bestanden, einschließlich echtem lokalem Blender.
- Ruff und Formatprüfung bestanden; Sites-Zugang: 6 Tests bestanden;
  ESM-Artefakt gebaut und geprüft. Unabhängiges Code-Review ohne wichtige Befunde.
- Cloud-STL-Vergleich: MeshLib `db57685140c8413c873f643b31b364a4`
  (1,119 s), Blender `27e8443a2f61470f9545240fdc3472ed` (2,864 s).
  Beide mit identischem Rohmodell-Hash, null offenen Kanten und validem ZIP.
- Foto: offizielles TRELLIS-Beispiel `assets/example_image/T.png`.
  Echte GPU-Erzeugung `6c37e6f0d5944df8bcd58c6699c67f16`, 512, Seed 42,
  keine Texturen; Rohmesh mit 3.132.422 Dreiecken.
- Der erste Reparaturversuch überschritt beim Python-Ray-Loop 600 Sekunden.
  Gebündelte native Ray-Abfragen beheben diesen Engpass. Weitere Diagnose:
  drei Restöffnungen bereits im nativen Remesh, kein STL-Exportfehler.
  Diese werden vor Kollisionsprüfung geschlossen; Teilkörper werden nach außen
  orientiert. Echte Durchgänge bleiben erhalten, wie der Torus-Test bestätigt.
- Erneute MeshLib-Aufbereitung ohne weitere GPU-Erzeugung:
  `801f215fd0004fa19eb033d38ddfa7b6`, 79,886 s, null offene/nicht-manifold
  Kanten, alle Teilkörper mit positivem Volumen, ZIP mit 4.378.856 Bytes.
  583 Teile und P95-Oberflächenabweichung 4,890 mm bei 60 mm Länge erfordern
  ausdrücklich Sichtprüfung und gegebenenfalls manuelle Nacharbeit.
- Der Blender-Pfad verwendet für die Einschlussprüfung einen räumlichen Index
  statt quadratischer Paarvergleiche bei über 100.000 Eingabefragmenten.

## Betriebsgrenzen

- Eine geschlossene Geometrie ist keine automatische Druckfreigabe. Dünne Teile,
  getrennte Fragmente, Motivtreue, Stützen und Slicer-Schichten müssen geprüft werden.
- Keine belastbare allgemeine Rangliste aus einem einzelnen Motiv ableiten.
- Ein tokenbesitzender Besucher kann kostenpflichtige GPU-Aufträge starten.
  Maximal drei aktive Aufträge pro Eigentümer; kein automatischer GPU-Retry.
- Vergleich und Verlauf zeigen die letzten 50 Aufträge.
- Tokenrotation ändert derzeit die Eigentümerkennung und blendet alte Aufträge aus.
- Vor einem Shopbetrieb fehlen kundenbezogene Zugänge, Abrechnung und eine
  verbindliche Prüfung der tatsächlichen Druckbarkeit. MeshLib- und Modelllizenzen
  müssen zum kommerziellen Einsatz passen.
- Ein Hundefoto wurde noch nicht geliefert. Beispielmedien und Testexporte liegen
  lokal unter `.tools/` im übergeordneten Workspace und sind nicht eingecheckt.
