#!/usr/bin/env python3
"""
Vollabzug aller Datensätze der Piveau Search API von data.gv.at.

Nutzt den Scroll-Mechanismus (Snapshot des Index), weil bei ~117k Einträgen
simple page/limit-Pagination am Elasticsearch max_result_window (page*limit > 10000)
scheitert.

Ausgabe: eine valide JSON-Datei (Array von Dokumenten), streamend geschrieben,
damit nichts komplett im RAM landet. Für einen NDJSON-Abzug (ein Dokument pro
Zeile, noch robuster/resumierbarer) siehe NDJSON = True.

Nur Abhängigkeit: requests  ->  pip install requests
"""

import json
import os
import sys
import time
import requests

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
BASE        = "https://www.data.gv.at/api/hub/search"  # Proxy-Basis auf data.gv.at
SEARCH_PATH = "/search"                                 # Start des Scrolls
SCROLL_PATH = "/scroll"                                 # Folge-Seiten
FILTER_PARAM = "filters"      # aktuelle Piveau-Versionen: "filters"; aeltere ggf. "filter"
FILTER_VALUE = "dataset"      # zu dumpender Index: dataset | catalogue | vocabulary
PAGE_SIZE    = 1000           # 1..1000; 1000 => ~118 Requests fuer 117k Records
OUT_FILE     = "data_gv_at_datasets.json"

# Nur bestimmte Felder holen -> deutlich kleinere Datei. Leer lassen = volle Dokumente.
# Beispiel: "id,title,description,keywords,distributions,publisher,modified"
INCLUDES = ""

NDJSON       = False          # True => ein Dokument pro Zeile statt JSON-Array
DELAY        = 0.2            # Sekunden Pause zwischen Requests (freundlich zum Server)
TIMEOUT      = 60
MAX_RETRIES  = 5
HEADERS      = {"User-Agent": "data-gv-at-dump/1.0 (+kontakt)"}

# SSL-Verifizierung. Drei Moeglichkeiten fuer self-signed / eigene CA:
#   True              -> normale Verifizierung gegen System-CAs (Default)
#   "/pfad/ca.pem"    -> gegen eigenes CA-Bundle pruefen  (EMPFOHLEN bei self-signed)
#   False             -> Verifizierung komplett aus (nur fuer Test/intern; unsicher!)
# Alternativ per Umgebungsvariable ueberschreibbar:
#   REQUESTS_CA_BUNDLE=/pfad/ca.pem  bzw.  DUMP_INSECURE=1
VERIFY_SSL = True

# Optionale Proxy-Einstellungen fuer HTTP/HTTPS:
#   None                              -> kein expliziter Proxy
#   "http://proxy.host:3128"          -> gleicher Proxy fuer http und https
#   {"http": "...", "https": "..."}   -> pro Schema getrennt konfigurieren
# Hinweis: requests beachtet ohnehin automatisch die Umgebungsvariablen
#   HTTP_PROXY / HTTPS_PROXY / NO_PROXY (kein Code noetig) - PROXY setzt das nur explizit.
# Ueberschreibbar per Env:  DUMP_PROXY=http://proxy.host:3128
# Auth im Proxy-URL: http://user:pass@proxy.host:3128
PROXY = None

# ---------------------------------------------------------------------------

# --- Proxy-Setup: Env-Override und Normalisierung auf requests-Dict ---
_proxy_env = os.environ.get("DUMP_PROXY")
if _proxy_env:
    PROXY = _proxy_env
if isinstance(PROXY, str):
    PROXIES = {"http": PROXY, "https": PROXY}
else:
    PROXIES = PROXY   # dict oder None
if PROXIES:
    print(f"  i Nutze Proxy: {PROXIES}", file=sys.stderr)

# --- SSL-Setup: Env-Overrides und Warnungsunterdrueckung ---
_ca_env = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("CURL_CA_BUNDLE")
if _ca_env:
    VERIFY_SSL = _ca_env
if os.environ.get("DUMP_INSECURE") == "1":
    VERIFY_SSL = False

if VERIFY_SSL is False:
    # sonst spammt urllib3 bei jedem Request eine InsecureRequestWarning
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    print("  ! WARNUNG: SSL-Verifizierung ist deaktiviert (verify=False).",
          file=sys.stderr)

def get_json(url, params=None):
    """GET mit einfachem Exponential-Backoff."""
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


def main():
    start_params = {
        FILTER_PARAM: FILTER_VALUE,
        "scroll": "true",
        "limit": PAGE_SIZE,
    }
    if INCLUDES:
        start_params["includes"] = INCLUDES

    print(f"Starte Scroll gegen {BASE}{SEARCH_PATH} ...", file=sys.stderr)
    data = get_json(BASE + SEARCH_PATH, start_params)
    result = data.get("result", {})

    total    = result.get("count")
    scroll_id = result.get("scrollId")
    results   = result.get("results", [])

    if scroll_id is None:
        sys.exit("Kein scrollId in der Antwort - laeuft diese Instanz evtl. eine "
                 "Piveau-Version ohne Scroll? Dann searchAfter-Variante nutzen.")

    print(f"Gesamt laut Index: {total} Datensaetze", file=sys.stderr)

    written = 0
    bytes_written = 0

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        if not NDJSON:
            f.write("[")
        first = True

        page = results
        while page:
            for doc in page:
                line = json.dumps(doc, ensure_ascii=False)
                if NDJSON:
                    f.write(line + "\n")
                else:
                    f.write(("" if first else ",") + line)
                first = False
                written += 1
                bytes_written += len(line.encode("utf-8"))

            print(f"  {written:>7} / {total}   (~{bytes_written/1_048_576:.1f} MB)",
                  file=sys.stderr)

            # naechste Seite holen
            time.sleep(DELAY)
            data = get_json(BASE + SCROLL_PATH, {"scrollId": scroll_id})
            result = data.get("result", {})
            # scrollId kann sich pro Aufruf aendern -> immer aktualisieren, wenn geliefert
            scroll_id = result.get("scrollId", scroll_id)
            page = result.get("results", [])

        if not NDJSON:
            f.write("]")

    print(f"\nFertig: {written} Datensaetze in '{OUT_FILE}' "
          f"({bytes_written/1_048_576:.1f} MB Nutzdaten).", file=sys.stderr)


if __name__ == "__main__":
    main()