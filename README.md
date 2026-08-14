# CHRONOS

**C**ontinuous **H**istorical **R**ecord **O**f **N**ational **O**pen-data **S**napshots

Ein täglich aktualisiertes, **diffbares Archiv der Metadaten aller offenen Daten von
[data.gv.at](https://www.data.gv.at)**, dem offenen Datenportal der österreichischen
Verwaltung. Für jeden Tag gibt es einen Commit und einen Tag – so lässt sich per
`git diff` nachvollziehen, welche Datensätze neu hinzugekommen, geändert oder
entfernt wurden.

> **Wichtig:** Archiviert werden die **Metadaten** (die DCAT-AP.at-Katalogeinträge:
> Titel, Beschreibung, Schlagworte, Distributionen, Herausgeber usw.) – **nicht** die
> eigentlichen Datendateien hinter den Distributionen. Das Repo ist also ein
> versioniertes Abbild des *Katalogs*, nicht der Nutzdaten selbst.

## Wie es funktioniert

Ein GitHub-Actions-Workflow läuft täglich und

1. lädt alle Datensätze über die **Piveau Search API** von data.gv.at
   (`/api/hub/search/search`) via Scroll-Mechanismus vollständig herunter,
2. legt **eine JSON-Datei pro Datensatz** ab, gruppiert in **Unterordner je Katalog**,
3. schreibt Dateien nur bei tatsächlich geändertem Inhalt (deterministisches JSON mit
   sortierten Schlüsseln → saubere, minimale Diffs),
4. löscht Dateien von Datensätzen, die aus dem Portal verschwunden sind,
5. committet den Tagesstand und setzt einen Datums-Tag `snapshot-YYYY-MM-DD`.

Dadurch zeigt schon der geänderte Ordner-Teilbaum, in **welchem Katalog** sich etwas
bewegt hat.

## Repo-Struktur

```
.
├── .github/workflows/daily-archive.yml   # täglicher Workflow (Cron + manuell)
├── dump_data_gv_at_perfile.py            # Downloader / Ablage-Logik
├── datasets/                             # das Archiv (vom Skript gepflegt)
│   ├── _index.json                       # Anzahl Datensätze je Katalog
│   ├── <katalog-a>/
│   │   ├── <dataset-id>.json
│   │   └── ...
│   └── <katalog-b>/
│       └── ...
└── README.md
```

## Nutzung

Den heutigen Stand ansehen: einfach durch `datasets/` browsen.

Was hat sich zuletzt geändert:

```bash
git log --oneline -- datasets/
git show <commit>                     # kompletter Tagesdiff
git show <commit> -- datasets/<katalog>/   # Änderungen eines einzelnen Katalogs
```

Den exakten Stand eines bestimmten Tages herstellen:

```bash
git checkout snapshot-2026-08-14
```

Änderungen eines Datensatzes über die Zeit:

```bash
git log -p -- datasets/<katalog>/<dataset-id>.json
```

## Datenquelle & Lizenz

Die Metadaten stammen von **[data.gv.at](https://www.data.gv.at)**. Für ihre
Nachnutzung gelten die dortigen Lizenz- bzw. Nutzungsbedingungen – bitte am Portal
prüfen und die jeweilige Quelle entsprechend zitieren.

Dieses Repository ist ein **inoffizielles** Community-Archiv und steht in keiner
Verbindung zum Betreiber von data.gv.at.

## Konfiguration

Alle Stellschrauben stehen als Konstanten oben in `dump_data_gv_at_perfile.py`:
Index-Filter, Seitengröße, Feld-Reduktion (`INCLUDES`), Katalog-Schlüssel
(`CATALOGUE_KEYS`), zu ignorierende volatile Felder (`IGNORE_KEYS`), sowie
SSL- und Proxy-Optionen. Zeitpunkt und Verhalten des täglichen Laufs stehen in
`.github/workflows/daily-archive.yml`.

## Hinweise

- **Erstlauf:** Der erste Durchlauf legt zehntausende Dateien an – am besten einmal
  lokal erzeugen und als Initial-Commit pushen (siehe Einrichtung).
- **Rausch-Felder:** Falls einzelne Felder bei jedem Harvest wechseln, obwohl sich
  inhaltlich nichts geändert hat, in `IGNORE_KEYS` eintragen, damit die Tagesdiffs
  aussagekräftig bleiben.
- **Repo-Größe:** Durch die vielen Kleinstdateien wächst `.git` über die Jahre. Solange
  es im Bereich der GitHub-Empfehlung (grob < 5 GB) bleibt, ist das unkritisch.