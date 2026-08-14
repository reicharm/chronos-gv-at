#!/usr/bin/env python3
"""
Taeglicher Facetten-Snapshot von data.gv.at fuer CHRONOS.

Speichert ALLE Facetten zur Sicherung (fuer beliebige spaetere Visualisierungen),
counts-only und gzip-komprimiert, plus die Titel/Labels separat in voller Fidelitaet:

    stats/facets/<YYYY-MM-DD>.json.gz   {date, count, facets:{facetId:{itemId:count}}}
    stats/facet-labels.json             {facetId:{title, items:{itemId:title}}}  (gemergt)

Ein Request (filters=dataset, limit=0) genuegt. build_dashboard_data.py projiziert
daraus die fuers Dashboard genutzten Dimensionen.

Nur Abhaengigkeit: requests
"""
import datetime as dt
import gzip
import json
import os
import sys
import requests

BASE   = "https://www.data.gv.at/api/hub/search/search"
PARAMS = {"filters": "dataset", "limit": 0}
OUT    = "stats"

# SSL/Proxy wie im Dump-Skript (Env: REQUESTS_CA_BUNDLE, DUMP_INSECURE=1, DUMP_PROXY)
VERIFY_SSL = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("CURL_CA_BUNDLE") or True
if os.environ.get("DUMP_INSECURE") == "1":
    VERIFY_SSL = False
    import urllib3; urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
_p = os.environ.get("DUMP_PROXY")
PROXIES = {"http": _p, "https": _p} if _p else None


def build_snapshot(result, date):
    """Alle Facetten counts-only: {date, count, facets:{facetId:{itemId:count}}}."""
    facets = {}
    for f in result.get("facets", []):
        facets[f["id"]] = {it["id"]: it["count"] for it in f.get("items", [])}
    return {"date": date, "count": result.get("count", 0), "facets": facets}


def merge_labels(labels, result):
    """Titel akkumulieren (volle Fidelitaet, inkl. mehrsprachiger Titel-Dicts)."""
    for f in result.get("facets", []):
        entry = labels.setdefault(f["id"], {"title": f.get("title"), "items": {}})
        if f.get("title") is not None:
            entry["title"] = f["title"]
        for it in f.get("items", []):
            entry["items"][it["id"]] = it.get("title") if it.get("title") is not None else it["id"]
    return labels


def main():
    r = requests.get(BASE, params=PARAMS, timeout=60, verify=VERIFY_SSL, proxies=PROXIES,
                     headers={"User-Agent": "chronos-facets/1.0"})
    r.raise_for_status()
    result = r.json()["result"]

    date = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    snap = build_snapshot(result, date)

    os.makedirs(os.path.join(OUT, "facets"), exist_ok=True)
    with gzip.open(os.path.join(OUT, "facets", f"{date}.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, sort_keys=True)

    lbl_path = os.path.join(OUT, "facet-labels.json")
    labels = json.load(open(lbl_path, encoding="utf-8")) if os.path.exists(lbl_path) else {}
    merge_labels(labels, result)
    with open(lbl_path, "w", encoding="utf-8") as f:
        json.dump(labels, f, ensure_ascii=False, sort_keys=True, indent=0)

    items = sum(len(v) for v in snap["facets"].values())
    print(f"{date}: total={snap['count']}, facetten={len(snap['facets'])}, items={items}",
          file=sys.stderr)


if __name__ == "__main__":
    main()