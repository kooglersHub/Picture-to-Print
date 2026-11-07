# Reparaturwerkzeuge vergleichen

Der Nutzer möchte den begonnenen Foto-Workflow fortsetzen und Reparaturwerkzeuge
auswählen können. Bestehende Schnittstellen unterstützen MeshLib und Blender.

## Entwurf

Eine Auswahl am Eingabeformular steuert beide Uploadarten und Reparaturwiederholungen.
Der Ergebnisbereich zeigt Werkzeug und Messwerte. Ein eigener Vergleichsbereich
übernimmt Größe und Voxelauflösung des gewählten Auftrags und erzeugt einen neuen
Auftrag aus seiner gespeicherten Rohgeometrie. Der Originalauftrag bleibt erhalten,
TRELLIS wird beim Vergleich nicht erneut aufgerufen. Vergleichseinträge verlinken
ihre Ergebnisse, zeigen Laufzeit, offene Kanten, Teilezahl und Oberflächenabweichung.

Entscheidung des Implementierers: Die vorhandenen zwei Backends nutzen; keine neue
Reparaturbibliothek einführen. MeshLib als Standard, Blender als Alternative.
Beide Werkzeuge müssen vor Auftragsannahme verfügbar sein. Cloud-Blender wird als
offizielles Linux-Paket installiert. Keine automatische Bewertung allein anhand
der Laufzeit; die geometrischen Messwerte und Sichtprüfung entscheiden.

## Umsetzung und Nachweise

1. Tests für gültige/ungültige Auswahl, Tool-Verfügbarkeit und Vergleich ohne
   erneute GPU-Erzeugung schreiben und scheitern sehen.
2. Tool-Einstellungen durch HTTP und Worker reichen; Laufzeit und Herkunft
   speichern; Blender im CPU-Image bereitstellen.
3. Formular und Vergleichsbereich erweitern, UI synchronisieren und veröffentlichen.
4. Crash-Lücke bei nicht gespeicherter Modal-Aufruf-ID absichern; Regression testen.
5. Vollständigen echten Fotoauftrag und beide Reparaturwege in der Cloud prüfen.
6. Tests, unabhängiges Review und PR abschließen; verbleibende Grenzen dokumentieren.
