# Picture to Print

## Website und Foto-Workflow – Zwischenstand 7. November 2026

Die [Website](https://picture-to-print-karl.timring5002.chatgpt.site/) ist veröffentlicht.
Der persönliche Zugangslink enthält einen Token im URL-Fragment. Die Website
tauscht ihn gegen ein sicheres HttpOnly-Cookie und entfernt ihn aus der Adresszeile.
Wer den Token besitzt, kann die zugehörigen Aufträge und Dateien sehen.
Token und Cloud-Zugangsdaten gehören nicht ins Repository.

Der Ablauf ist: Foto hochladen, längste Ausdehnung und Auflösung wählen,
TRELLIS-Geometrie erzeugen, Oberfläche aufbereiten, Vorschau prüfen und
STL/3MF samt Prüfbericht herunterladen. Vorhandene Meshes überspringen die GPU.
Eine erneute Druckaufbereitung nutzt die gespeicherte Rohgeometrie ohne neue
Bildgenerierung. Texturen werden weder erzeugt noch benötigt.

**Verifiziert:** Ein echter Cloud-Auftrag mit einem STL-Testmodell lief bis zum
ZIP-Download durch. Der GPU-Container wurde erfolgreich gebaut und bereitgestellt.
Der vollständige Foto-Durchlauf mit echter GPU-Inferenz ist noch nicht geprüft.
Das ist ein Entwicklungszwischenstand und keine automatische Druckfreigabe.

Die öffentlichen Website-Dateien und der Token-Proxy liegen im separat verwalteten
Sites-Quellrepository (`site/` im lokalen Checkout). Die kanonische Oberfläche liegt
hier unter `picture_to_print/static/`; `site/scripts/sync-ui.mjs` synchronisiert sie.
Modal trennt den CPU-Webdienst (`picture_to_print.modal_backend`) vom GPU-Dienst
(`picture_to_print.modal_app`). Aufträge liegen im Volume `picture-to-print-jobs`.
Ein privater Backend-Bearer und eine serverseitige Auftragseigentümerkennung
schützen die Verbindung zwischen Website und Modal.

Backend installieren, prüfen und bereitstellen:

```powershell
python -m pip install -e ".[meshlib,web,dev]"
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m modal deploy -m picture_to_print.modal_app
python -m modal deploy -m picture_to_print.modal_backend
```

Modal muss im eigenen Konto angemeldet sein. Das Secret
`picture-to-print-runtime` muss `P2P_BACKEND_TOKEN` enthalten. Sites benötigt
`ACCESS_TOKEN_HASH` (SHA-256), `SESSION_SECRET`, `BACKEND_TOKEN` und `BACKEND_URL`.
Die vorhandene Konfiguration verwendet das Gewichte-Volume
`darkfantasy-trellis2-weights`. Modell- und MeshLib-Lizenzen müssen zum geplanten
kommerziellen Einsatz passen.

Offene Schritte und Wiederaufnahme: [CHECKPOINT.md](CHECKPOINT.md).

Trellis-Geometrie zu geschlossenen, texturfreien Volumenkörpern auf einem
CPU-Worker. Der bevorzugte Reparaturpfad verwendet MeshLibs `HoleWindingRule`,
eine Sichtbarkeitsprüfung und eine erneute Prüfung der exportierten STL.
Blender/OpenVDB ist ein explizit wählbarer Vergleichspfad.

## Installation

Python 3.11 oder neuer:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[meshlib,dev]"
```

**MeshLib verlangt für kommerzielle Entwicklung und Nutzung eine kommerzielle
Lizenz.** Diese Installation beschafft keine Lizenz. Vor dem Einsatz in einem
Shop muss die passende Berechtigung vorliegen. Details beim
[Hersteller](https://meshlib.io/documentation/License.html). `pip install -e .`
enthält MeshLib deshalb nicht; `.[meshlib]` ist eine explizite Auswahl.
Blender lässt sich unabhängig davon verwenden.

## Modell reparieren

```powershell
python -m picture_to_print "C:\Modelle\trellis_raw.ply" --output exports/auftrag-001 --size-mm 100 --voxel-mm 0.4
```

Akzeptiert GLB, STL, OBJ und PLY. Szenentransformationen werden übernommen,
Materialien und Texturen nicht. `--size-mm` bestimmt die **längste Ausdehnung**,
nicht automatisch die Höhe. Das Seitenverhältnis bleibt erhalten. Die Auflösung
beträgt hier 0,4 mm; für kleine Schmuckdetails ist meist eine feinere Auflösung
nötig. Kleinere Voxel kosten mehr RAM und Zeit. Übermäßig große Raster werden
vor dem nativen Reparaturprozess abgelehnt.

Das Zielverzeichnis muss neu sein. Bei Erfolg enthält es:

- `model.stl`: reine Dreiecksgeometrie; im Slicer als Millimeter importieren.
- `model.3mf`: dieselbe Geometrie mit expliziter Millimeter-Einheit.
- `manifest.json`: Eingabe-Hash, Parameter, Vorher-/Nachher-Messwerte,
  entfernte Innengeometrie und Gründe für eine manuelle Prüfung.

Bei fehlgeschlagener Reparatur/Validierung bleibt ein `rejected`-Manifest
zurück; Druckdateien werden nicht veröffentlicht. Ungültige Eingaben/Parameter
werden vor der Anlage des Jobverzeichnisses abgewiesen. Ein nativer Absturz
betrifft nur den isolierten Reparaturprozess.

## Rohgeometrie direkt aus Trellis sichern

Im bestehenden Trellis-/Modal-Worker dieses Paket installieren und direkt nach
`pipeline.run()` einhängen, **vor** `simplify()` und `o_voxel.postprocess.to_glb()`:

```python
from pathlib import Path
from picture_to_print.trellis import export_raw_mesh
from picture_to_print import PrintSettings, prepare_model

mesh = pipeline.run(image)[0]
raw = export_raw_mesh(mesh, Path("exports/job-001-raw.ply"))
result = prepare_model(raw, Path("exports/job-001"), PrintSettings(size_mm=100, voxel_mm=0.4))
```

Der Hook übernimmt nur `vertices` und `faces` und kopiert Torch-Tensoren auf die
CPU. UV-Unwrapping, Textur-Baking, GLB-Remeshing, Rigging und Animation entfallen.
Die Bild-zu-Geometrie-Inferenz bleibt unverändert; dieses Repo installiert weder
Trellis-Gewichte noch eine GPU-Umgebung. Ein vorhandener GLB kann ebenso direkt
verarbeitet werden, ist aber bereits durch dessen Export gegangen.

## Prüfungen und Grenzen

Geschlossene separate Innenhüllen werden vor und nach der Rekonstruktion
entfernt. Zusätzlich testet MeshLib für jede Fläche bis zu 26 Strahlrichtungen:
Vollständig verdeckte Flächen werden unabhängig von ihrer Verbindung zur
Außenwand entfernt. Das adressiert verbundene Doppelwände. Mit
`--keep-hidden-faces` lässt sich die heuristische Sichtbarkeitsprüfung für tiefe
Vertiefungen oder einen Vergleich abschalten.

Anschließend rekonstruiert MeshLib bei Offset 0 über ein Distanzfeld mit
`HoleWindingRule` und Lochabschluss. Der Prozess prüft Selbstüberschneidungen
und die exportierte STL erneut auf offene/nichtmannigfaltige Kanten,
Orientierung, positives Volumen und Komponenten. Eine deterministische
Stichprobe misst die bidirektionale Oberflächenabweichung. Sie ist keine
garantierte maximale Formabweichung.

**`geometry_ready` bedeutet: Die implementierten Geometrieprüfungen wurden
bestanden.** `review_required` bleibt immer `true`. Wandstärken, Ringmaße,
gewollte Öffnungen, Stützen, Belastbarkeit und Slicer-Schichten müssen geprüft
werden. Strahlabtastung kann tiefe Details falsch einordnen; Rekonstruktion kann
feine Durchbrüche schließen. Getrennte Außenteile bleiben erhalten und werden
als `separate_parts` gemeldet. Es wird nie stillschweigend nur das größte Teil
übernommen. Infill und kontrolliertes Aushöhlen mit Resin-Abläufen sind spätere
Slicer-/Produktentscheidungen.

## Blender-Vergleich

Blender 4.5 LTS separat installieren:

```powershell
python -m picture_to_print trellis.glb --output exports/blender-vergleich --backend blender --blender "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
```

Dieser Pfad schließt offene Ränder, rekonstruiert mit OpenVDB und durchläuft
dieselben Exportprüfungen. Er garantiert keine Reparatur komplexer
Trellis-Doppelwände. Seine Innenhüllenprüfung behält mehrdeutige überlappende
Geometrie vorsichtig bei; MeshLib verwendet dafür eine native Kollisionsprüfung.
Fehlgeschlagene Ergebnisse werden verworfen. Die Eingabeachsen werden
übernommen; die gewünschte Druckorientierung im Slicer festlegen.

## Shop-Anbindung

`prepare_model(source, output, settings)` ist die Schnittstelle für einen
späteren Queue-/Bestell-Worker. Jeder Job erhält eigene Eingabe-/Ausgabepfade.
Der Aufrufer übernimmt Authentifizierung, Upload-Limits, Mandantentrennung,
Gesamtzeit-/Speicherlimits, Storage und manuelle Freigabe. Die nativen Prozesse
haben standardmäßig 300 s Timeout; Vor-/Nachprüfung und Export laufen zusätzlich.
Ein Worker-Container braucht daher auch ein Gesamtlimit. Dieses Repo enthält
keinen öffentlichen Uploadserver oder Checkout.

Das versionierte Manifest enthält relative Artefaktnamen und einen SHA-256-Hash
zur Zuordnung zum Auftrag. Interne Fehlerdetails nur intern loggen.
`geometry_ready` allein darf keine automatische Produktionsfreigabe auslösen.

## Tests und Qualität

```powershell
python -m pytest -q
ruff check .
ruff format --check .
```

Mit `BLENDER_BIN` laufen auch Blender-Integrationstests. Die MeshLib-Tests laufen
ohne GPU: offene Flächen, geschlossene und verbundene Innenwände,
Szenentransformationen, mehrere Außenteile, Ringöffnung, Millimeter-Export,
Rohmesh-Hook und Fehlerfälle. CI führt Tests und Ruff aus.

## Quellen und Vergleich

- [Trellis-Originalbeispiel](https://github.com/microsoft/TRELLIS.2/blob/main/example.py):
  Rohmesh vor dem GLB-Postprocessing abgreifen.
- [MeshLib-Reparaturbeispiel](https://pypi.org/project/meshlib/): Winding-Number-Rekonstruktion.
- [Inner Shell Fix](https://github.com/ectomia/trellis2-inner-shell-fix):
  Sichtbarkeit statt nur Zusammenhang bei verbundenen Innenwänden; hier ist die
  Idee unabhängig mit MeshLib-Strahlabfragen umgesetzt.
- [Meshwright](https://github.com/GeekatplayStudio/Meshwright): interaktiver
  Vergleich mit mehreren optionalen Backends; hier nicht eingebunden.
- [Game-Pipeline](https://github.com/kooglersHub/3D-Asset-Creator): Worker-Trennung
  und Modal sind übertragbar; Texturen, Skinning und Animation entfallen hier.
