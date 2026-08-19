![CHRONOS](chronos-logo.svg)

# CHRONOS

**C**ontinuous **H**istorical **R**ecord **O**f **N**ational **O**pen-data **S**napshots

Ein täglich aktualisiertes, **diffbares Archiv der Metadaten aller offenen Daten von
[data.gv.at](https://www.data.gv.at)**, dem offenen Datenportal der österreichischen
Verwaltung. Für jeden Tag gibt es einen Commit und einen Tag – so lässt sich per
`git diff` nachvollziehen, welche Datensätze neu hinzugekommen, geändert oder
entfernt wurden. Ein interaktives **Dashboard** zeigt die Entwicklung der Datenbestände
über die Zeit.

> **Wichtig:** Archiviert werden die **Metadaten** (die DCAT-AP.at-Katalogeinträge:
> Titel, Beschreibung, Schlagworte, Distributionen, Herausgeber usw.) – **nicht** die
> eigentlichen Datendateien hinter den Distributionen. Das Repo ist ein versioniertes
> Abbild des *Katalogs*, nicht der Nutzdaten selbst.

## Dashboard

Das Dashboard visualisiert die Bestandsveränderung über die Zeit – gesamt, je Katalog
und je veröffentlichende Stelle – mit wählbarem Aspekt, Zeitraum, Zeitachsen-Granularität
(Tag/Woche/Monat) und Umschaltung zwischen Bestand und Veränderung (Δ). Es läuft als
statische Seite auf **GitHub Pages**:

- **Dashboard:** `https://<user>.github.io/chronos-gv-at/`
- **Über das Projekt:** `https://<user>.github.io/chronos-gv-at/about.html`

## Wie es funktioniert

Ein GitHub-Actions-Workflow läuft täglich und

1. lädt alle Datensätze über die **Piveau Search API** von data.gv.at
   (`/api/hub/search/search`) via Scroll-Mechanismus vollständig herunter,
2. legt **eine JSON-Datei pro Datensatz** ab, gruppiert in **Unterordner je Katalog**
   (deterministisches JSON mit sortierten Schlüsseln → saubere, minimale Diffs; geschrieben
   nur bei tatsächlich geändertem Inhalt),
3. löscht Dateien von Datensätzen, die aus dem Portal verschwunden sind,
4. erfasst **alle Facetten** (`filters=dataset&limit=0`) als komprimierte Tages-Sicherung
   – Grundlage für beliebige spätere Visualisierungen,
5. baut daraus die Daten fürs Dashboard und deployt die Seite auf GitHub Pages,
6. committet den Tagesstand und setzt einen Datums-Tag `snapshot-YYYY-MM-DD`
   (an änderungslosen Tagen ein Keepalive-Commit, damit der Cron aktiv bleibt).

Dadurch zeigt schon der geänderte Ordner-Teilbaum, in **welchem Katalog** sich etwas
bewegt hat.

## Repo-Struktur

```
.
├── .github/workflows/daily-archive.yml   # täglicher Workflow (Cron + manuell)
├── dump_data_gv_at_perfile.py            # Volldump: 1 JSON-Datei je Datensatz
├── capture_facets.py                     # täglicher All-Facetten-Snapshot (Sicherung)
├── build_dashboard_data.py               # baut docs/data.json aus dem Facetten-Archiv
├── datasets/                             # das diffbare Archiv (vom Skript gepflegt)
│   ├── _index.json                       # Anzahl Datensätze je Katalog
│   └── <katalog>/<dataset-id>.json
├── stats/                                # Facetten-Sicherung (alle Facetten, gzip)
│   ├── facets/<datum>.json.gz
│   └── facet-labels.json
├── docs/                                 # GitHub Pages
│   ├── index.html                        # Dashboard
│   ├── about.html                        # Infoseite
│   ├── chronos-mark.svg                  # Logo-Mark / Favicon
│   └── data.json                         # täglich gebaut & als Pages-Artefakt deployt
│                                         #   (NICHT eingecheckt, siehe .gitignore)
├── chronos-logo.svg                      # Logo-Lockup (Wortmarke)
└── README.md
```

## Nutzung

Den heutigen Stand ansehen: durch `datasets/` browsen. Änderungen nachvollziehen:

```bash
git log --oneline -- datasets/
git show <commit>                          # kompletter Tagesdiff
git show <commit> -- datasets/<katalog>/   # Änderungen eines Katalogs
git checkout snapshot-2026-08-14           # exakter Stand eines Tages
git log -p -- datasets/<katalog>/<id>.json # ein Datensatz über die Zeit
```

## Datenquelle & Lizenz

Die Metadaten stammen von **[data.gv.at](https://www.data.gv.at)**. Für ihre
Nachnutzung gelten die dortigen Lizenz- bzw. Nutzungsbedingungen – bitte am Portal
prüfen und die jeweilige Quelle entsprechend zitieren.

Dieses Repository ist ein **inoffizielles** Community-Archiv und steht in keiner
Verbindung zum Betreiber von data.gv.at.

## Konfiguration

- `dump_data_gv_at_perfile.py`: Index-Filter, Seitengröße, Feld-Reduktion (`INCLUDES`),
  Katalog-Schlüssel (`CATALOGUE_KEYS`), volatile Felder (`IGNORE_KEYS`), SSL/Proxy.
- `build_dashboard_data.py`: `DIMS` steuert, welche Facetten als Dashboard-Dimensionen
  erscheinen – erweiterbar (z. B. `categories`, `format`) **ohne** erneute Erfassung,
  weil das Facetten-Archiv rückwirkend alle Facetten enthält.
- `.github/workflows/daily-archive.yml`: Zeitpunkt und Ablauf des täglichen Laufs.

## Betrieb & Größe

- **Pages:** Source in den Repo-Settings auf **„GitHub Actions"** stellen. `docs/data.json`
  wird täglich gebaut und als Pages-Artefakt deployt, aber **nicht** committet – so bleibt
  die Git-History schlank.
- **Größen-Wächter:** Der Workflow gibt die serverseitige Repo-Größe aus und warnt ab 4 GB.
  Prüfen lässt sie sich jederzeit mit `gh api repos/<user>/chronos-gv-at --jq '.size'` (KB).
- **5-GB-Grenze (Empfehlung, kein harter Block):** Wächst `.git` über die Jahre zu stark,
  hilft ein jährlicher **Rollover** – aktuellen Stand samt History als Bundle sichern
  (`git bundle create chronos-JAHR.bundle --all`) und die Live-Historie auf einen frischen
  Wurzel-Commit zurücksetzen. Die Facetten-Sicherung lässt sich bei Bedarf aus der History
  in Release-Assets auslagern.

## Hinweise

- **Erstlauf:** Der erste Durchlauf legt zehntausende Dateien an – am besten einmal lokal
  erzeugen und als Initial-Commit pushen.
- **Rausch-Felder:** Wechseln einzelne Felder bei jedem Harvest ohne inhaltliche Änderung,
  in `IGNORE_KEYS` eintragen, damit die Tagesdiffs aussagekräftig bleiben.
- **Kataloge vs. Stellen:** Die größten „Kataloge" sind teils Harvester-Quellen (OHOLD,
  offenerhaushalt.at …); die veröffentlichende Stelle (Publisher) ist die inhaltlich nähere Achse.