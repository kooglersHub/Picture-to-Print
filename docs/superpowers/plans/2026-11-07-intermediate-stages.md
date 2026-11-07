# Sichtbare Zwischenstände

Der Nutzer fordert alle Zwischenstände in der bestehenden token-geschützten Website,
um Generierungs- und Reparaturschäden unterscheiden zu können. Keine Änderung des
Reparaturverfahrens oder zusätzliche Texturgenerierung. Vorhandene Rohmeshes nutzen.

## Entwurf

Eine Schritt-Auswahl im Ergebnis zeigt Originalfoto, tatsächliche Freistellung und
TRELLIS-Vorverarbeitung (für neue Fotojobs), unveränderte Rohgeometrie sowie jede
topologieverändernde Reparaturphase. 3D-Zwischenstände bekommen dieselbe Ausrichtung,
Bezugsgröße und Kameraposition; Bilder und Meshes können einzeln heruntergeladen
werden. Roh-/Zwischenmeshes sind explizit Diagnoseartefakte, keine freigegebenen
Druckdateien. Messwerte: Dreiecke, Punkte, offene/nicht-manifold Kanten, Teilezahl.

MeshLib: Vorbereitet, Import, Sichtbarkeitsfilter, Voxel-Rekonstruktion, Randlöcher
geschlossen, Innenhüllen entfernt, Orientierung korrigiert, exportierte STL.
Blender: Vorbereitet, Innenhüllen vorab entfernt, Import, Löcher gefüllt,
Voxel-Rekonstruktion, Innenhüllen entfernt, Orientierung, exportierte STL.

Alte Jobs können vorhandenes Foto und Rohmesh verwenden. Nicht gespeicherte
Freistellungen werden ehrlich als fehlend markiert. Reparaturzwischenstände lassen
sich mit einem CPU-only-Retry nachträglich erzeugen. Für den vorhandenen Dino diesen
Pfad tatsächlich prüfen. Neue Jobs speichern auch beide tatsächlichen GPU-Bilder.

## Schnittstelle

GET /api/jobs/{id}/stages liefert {stages:[{id,label,kind,status,description,
preview_url,download_url,metrics,bytes}], size_mm, alignment, legacy}.
GET /api/jobs/{id}/stage-files/{name} liefert ausschließlich registrierte,
fertig geschriebene Artefakte nach derselben Eigentümerprüfung wie Druckdownloads.
Auch fehlgeschlagene/laufende Jobs dürfen bereits fertige Diagnosestufen zeigen.
Foto und Rohmesh gelangen weiterhin nicht in das normale Druck-ZIP.

## Schritte

1. Backend-Tests für Stufenaufzeichnung, Dateifreigabe/Eigentümer, fehlgeschlagene
   Jobs und Legacy-Daten schreiben; rot/grün prüfen.
2. Atomare Stufenablage, gemeinsame Vorschauausrichtung, native Worker-Snapshots
   und HTTP-Routen umsetzen. Reale GPU-Bilder erfassen, bestehende Aufrufe kompatibel halten.
3. Frontend-Schrittauswahl, Kennzahlen und Downloads gegen obigen Vertrag parallel
   zur Backend-Implementierung umsetzen (getrennte Dateien).
4. Dino mit gespeicherter Rohgeometrie CPU-only erneut aufbereiten, alle Phasen
   prüfen; neuen Fotojob zum tatsächlichen GPU-Bilder-Nachweis testen.
5. Tests/Review, bestehende Website veröffentlichen, PR und main aktualisieren.
