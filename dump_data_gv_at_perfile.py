#!/usr/bin/env python3
"""
Vollabzug der Piveau Search API von data.gv.at als *diffbare* Ablage:
eine JSON-Datei pro Datensatz, gruppiert in Unterordner je Katalog.

Layout:
    <OUT_DIR>/<katalog>/<dataset-id>.json
    <OUT_DIR>/_index.json          (optional: {katalog: anzahl}, sortiert)

Ziel ist eine Git-Historie, in der ein Tagescommit genau die geaenderten,
neuen und geloeschten Datensaetze zeigt - und dank Ordnerstruktur auch,
in welchem Katalog sich etwas bewegt hat.

Wichtig fuer saubere Diffs:
  * JSON wird deterministisch geschrieben (sort_keys + indent) -> Zeilendiffs
  * Dateien werden nur bei tatsaechlich geaendertem Inhalt neu geschrieben
  * verschwundene Datensaetze werden geloescht (mark & sweep), damit der
    Commit die Entfernung zeigt - mit Schutz gegen Massenloeschung bei
    abgebrochenem Lauf

Nur Abhaengigkeit: requests  ->  pip install requests
"""

import hashlib
import json
import os
import re
import sys
import time
import requests

# ---------------------------------------------------------------------------
# Konfiguration (Fetch)
# ---------------------------------------------------------------------------
BASE        = "https://www.data.gv.at/api/hub/search"
SEARCH_PATH = "/search"
SCROLL_PATH = "/scroll"
FILTER_PARAM = "filters"      # aktuelle Piveau-Versionen: "filters"; aeltere ggf. "filter"
FILTER_VALUE = "dataset"
PAGE_SIZE    = 1000           # 1..1000
INCLUDES     = ""             # nur bestimmte Felder holen -> kleinere Files; leer = voll

DELAY        = 0.2
TIMEOUT      = 60
MAX_RETRIES  = 5
HEADERS      = {"User-Agent": "data-gv-at-dump/1.0 (+kontakt)"}

# SSL: True | "/pfad/ca.pem" | False   (Env: REQUESTS_CA_BUNDLE, DUMP_INSECURE=1)
VERIFY_SSL = True
# Proxy: None | "http://proxy:3128" | {"http": ..., "https": ...}  (Env: DUMP_PROXY)
PROXY = None

# ---------------------------------------------------------------------------
# Konfiguration (Ablage / Diff)
# ---------------------------------------------------------------------------
OUT_DIR            = "datasets"
GROUP_BY_CATALOGUE = True
# In dieser Reihenfolge wird der Katalog-Schluessel im Dokument gesucht.
# Wert kann ein String oder ein Objekt mit "id" sein. Nach dem 1. Lauf die
# erzeugten Ordnernamen pruefen und hier ggf. auf den echten Schluessel fixieren.
CATALOGUE_KEYS = ["catalog", "catalogue", "is_part_of"]
UNKNOWN_CATALOGUE = "_unknown"

# Volatile Top-Level-Felder, die jeden Harvest wechseln und Diffs verrauschen
# wuerden, hier vor dem Schreiben entfernen. Z.B. ["count"]. Leer = nichts entfernen.
IGNORE_KEYS = []

WRITE_INDEX     = True        # _index.json mit {katalog: anzahl}
SWEEP_DELETES   = True        # verschwundene Datensaetze loeschen
SWEEP_MIN_RATIO = 0.5         # Loesch-Kehrung nur, wenn >= 50% der erwarteten Menge
                              # geschrieben wurde (Schutz vor Massenloeschung)

# ---------------------------------------------------------------------------
# SSL / Proxy Setup (identisch zum Single-File-Skript)
# ---------------------------------------------------------------------------
_ca_env = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("CURL_CA_BUNDLE")
if _ca_env:
    VERIFY_SSL = _ca_env
if os.environ.get("DUMP_INSECURE") == "1":
    VERIFY_SSL = False
if VERIFY_SSL is False:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    print("  ! WARNUNG: SSL-Verifizierung ist deaktiviert (verify=False).",
          file=sys.stderr)

_proxy_env = os.environ.get("DUMP_PROXY")
if _proxy_env:
    PROXY = _proxy_env
PROXIES = {"http": PROXY, "https": PROXY} if isinstance(PROXY, str) else PROXY
if PROXIES:
    print(f"  i Nutze Proxy: {PROXIES}", file=sys.stderr)

# ---------------------------------------------------------------------------

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_name(value, maxlen=180):
    """Dateisystem-sicherer, deterministischer Name. Bei Kuerzung Hash-Suffix,
    damit unterschiedliche lange IDs nicht kollidieren."""
    raw = str(value)
    name = _SAFE.sub("_", raw).strip("._") or "_"
    if len(name) > maxlen:
        h = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
        name = name[: maxlen - 11].rstrip("._") + "-" + h
    return name


def catalogue_of(doc):
    """Katalog-Slug aus dem Dokument extrahieren (defensiv ueber mehrere Keys)."""
    if not GROUP_BY_CATALOGUE:
        return ""
    for key in CATALOGUE_KEYS:
        val = doc.get(key)
        if isinstance(val, dict):
            val = val.get("id") or val.get("originalId")
        if isinstance(val, list) and val:
            val = val[0].get("id") if isinstance(val[0], dict) else val[0]
        if val:
            return safe_name(val)
    return UNKNOWN_CATALOGUE


def get_json(url, params=None):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS,
                             timeout=TIMEOUT, verify=VERIFY_SSL, proxies=PROXIES)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            if attempt == MAX_RETRIES:
                raise
            wait = min(2 ** attempt, 30)
            print(f"  ! Fehler ({e}); Retry {attempt}/{MAX_RETRIES} in {wait}s",
                  file=sys.stderr)
            time.sleep(wait)


def serialize(doc):
    """Deterministische JSON-Repraesentation fuer stabile Zeilendiffs."""
    if IGNORE_KEYS:
        doc = {k: v for k, v in doc.items() if k not in IGNORE_KEYS}
    return json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def iter_all_datasets():
    """Alle Datensaetze via Scroll durchlaufen (yield doc)."""
    params = {FILTER_PARAM: FILTER_VALUE, "scroll": "true", "limit": PAGE_SIZE}
    if INCLUDES:
        params["includes"] = INCLUDES

    print(f"Starte Scroll gegen {BASE}{SEARCH_PATH} ...", file=sys.stderr)
    data = get_json(BASE + SEARCH_PATH, params)["result"]
    total = data.get("count")
    scroll_id = data.get("scrollId")
    page = data.get("results", [])
    if scroll_id is None:
        sys.exit("Kein scrollId in der Antwort - Instanz ohne Scroll-Support? "
                 "Dann searchAfter-Variante nutzen.")
    print(f"Gesamt laut Index: {total} Datensaetze", file=sys.stderr)
    yield total, None  # erste Ausgabe: nur die Gesamtzahl signalisieren

    while page:
        for doc in page:
            yield None, doc
        time.sleep(DELAY)
        data = get_json(BASE + SCROLL_PATH, {"scrollId": scroll_id})["result"]
        scroll_id = data.get("scrollId", scroll_id)
        page = data.get("results", [])


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    written_rel = set()          # relative Pfade, die dieser Lauf erzeugt/bestaetigt hat
    per_cat = {}                 # katalog -> anzahl
    total_expected = None
    added = changed = unchanged = 0

    for total, doc in iter_all_datasets():
        if doc is None:          # erstes Yield mit der Gesamtzahl
            total_expected = total
            continue

        ds_id = doc.get("id")
        if not ds_id:
            print("  ! Dokument ohne id uebersprungen", file=sys.stderr)
            continue

        cat = catalogue_of(doc)
        rel = os.path.join(cat, safe_name(ds_id) + ".json") if cat \
            else safe_name(ds_id) + ".json"
        path = os.path.join(OUT_DIR, rel)

        if rel in written_rel:
            print(f"  ! Namenskollision fuer '{ds_id}' -> '{rel}' (uebersprungen)",
                  file=sys.stderr)
            continue
        written_rel.add(rel)
        per_cat[cat or "."] = per_cat.get(cat or ".", 0) + 1

        new_content = serialize(doc)
        old_content = None
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                old_content = f.read()

        if old_content is None:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            added += 1
        elif old_content != new_content:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            changed += 1
        else:
            unchanged += 1

        n = added + changed + unchanged
        if n % 5000 == 0:
            print(f"  {n} verarbeitet ...", file=sys.stderr)

    total_written = len(written_rel)

    # --- Lösch-Kehrung: bestehende Files, die dieser Lauf NICHT bestaetigt hat ---
    deleted = 0
    safe_to_sweep = True
    if SWEEP_DELETES:
        if total_expected and total_written < total_expected * SWEEP_MIN_RATIO:
            safe_to_sweep = False
            print(f"  ! Nur {total_written}/{total_expected} geschrieben "
                  f"(< {SWEEP_MIN_RATIO:.0%}). Loesch-Kehrung wird UEBERSPRUNGEN.",
                  file=sys.stderr)
        else:
            for root, _dirs, files in os.walk(OUT_DIR):
                for fn in files:
                    if not fn.endswith(".json") or fn == "_index.json":
                        continue
                    rel = os.path.relpath(os.path.join(root, fn), OUT_DIR)
                    if rel not in written_rel:
                        os.remove(os.path.join(root, fn))
                        deleted += 1
            # leere Katalog-Ordner entfernen
            for root, dirs, files in os.walk(OUT_DIR, topdown=False):
                if root == OUT_DIR:
                    continue
                if not os.listdir(root):
                    os.rmdir(root)

    # --- optionaler Index ---
    if WRITE_INDEX:
        index = {k: per_cat[k] for k in sorted(per_cat)}
        with open(os.path.join(OUT_DIR, "_index.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    print(f"\nFertig. {total_written} Datensaetze in {len(per_cat)} Katalog(en).",
          file=sys.stderr)
    print(f"  neu: {added}   geaendert: {changed}   unveraendert: {unchanged}   "
          f"geloescht: {deleted if safe_to_sweep else 'uebersprungen'}",
          file=sys.stderr)


if __name__ == "__main__":
    main()