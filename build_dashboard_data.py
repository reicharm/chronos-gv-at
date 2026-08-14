#!/usr/bin/env python3
"""
Projiziert aus dem gzip-Facetten-Archiv (stats/facets/*.json.gz) die vom
Dashboard gelesene Zeitreihe docs/data.json.

    {generated, dates:[...], total:[...],
     <dim>:{id:[...aligned...]} fuer jede DIM,
     labels:{<dim>:{id:title}}}

Welche Facetten als Dashboard-Dimensionen erscheinen, steuert DIMS - erweiterbar
(z.B. "categories", "format") OHNE erneute Erfassung, weil das Archiv alle Facetten
enthaelt. Reine Standardbibliothek.
"""
import glob
import gzip
import json
import os

STATS = "stats"
OUT   = os.path.join("docs", "data.json")
DIMS  = ("catalog", "publisher")     # spaeter erweiterbar, z.B. + "categories", "format"


def load_gz(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def pick_label(title, fallback):
    if isinstance(title, dict):
        return title.get("de") or title.get("en") or next(iter(title.values()), fallback)
    return title or fallback


def main():
    files = sorted(glob.glob(os.path.join(STATS, "facets", "*.json.gz")))
    if not files:
        raise SystemExit("Keine Snapshots unter stats/facets/ gefunden.")
    snaps = [load_gz(f) for f in files]
    dates = [s["date"] for s in snaps]

    data = {"generated": dates[-1], "dates": dates,
            "total": [s.get("count") for s in snaps], "labels": {}}

    lbl_path = os.path.join(STATS, "facet-labels.json")
    labels_raw = json.load(open(lbl_path, encoding="utf-8")) if os.path.exists(lbl_path) else {}

    for dim in DIMS:
        data[dim] = {}
        ids = set()
        for s in snaps:
            ids.update(s.get("facets", {}).get(dim, {}).keys())
        for did in sorted(ids):
            data[dim][did] = [s.get("facets", {}).get(dim, {}).get(did) for s in snaps]
        items = (labels_raw.get(dim, {}) or {}).get("items", {})
        data["labels"][dim] = {did: pick_label(items.get(did), did) for did in ids}

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    kb = os.path.getsize(OUT) / 1024
    dims = ", ".join(f"{d}={len(data[d])}" for d in DIMS)
    print(f"{OUT}: {len(dates)} Tage, {dims}, {kb:.0f} KB")


if __name__ == "__main__":
    main()