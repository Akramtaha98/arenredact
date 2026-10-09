"""Fetch random Wikipedia lead-section text (Arabic and English) as ordinary,
independently written text for false-positive measurement. Public MediaWiki
API; content is CC BY-SA 4.0 (see data/independent/README.md).

usage: python scripts/fetch_wikipedia_negatives.py LANG TARGET_PAGES [MAX_SECONDS]
Appends to data/independent/wikipedia_LANG.jsonl and can be re-run in chunks.
"""
import json, sys, time, urllib.request, urllib.parse, os

UA = "ArEnRedactResearch/1.0 (mailto:akramtaha30@gmail.com)"


def main(lang, target, budget):
    path = f"data/independent/wikipedia_{lang}.jsonl"
    seen = set()
    if os.path.exists(path):
        seen = {json.loads(l)["pageid"] for l in open(path, encoding="utf8")}
    t0 = time.time()
    while len(seen) < target and time.time() - t0 < budget:
        q = urllib.parse.urlencode({"action": "query", "generator": "random", "grnnamespace": 0, "grnlimit": 20,
                                    "prop": "extracts", "explaintext": 1, "exlimit": "max", "exintro": 1, "format": "json"})
        req = urllib.request.Request(f"https://{lang}.wikipedia.org/w/api.php?{q}", headers={"User-Agent": UA})
        try:
            data = json.load(urllib.request.urlopen(req, timeout=40))
        except Exception as exc:
            print("retry", exc, file=sys.stderr); time.sleep(2); continue
        with open(path, "a", encoding="utf8") as f:
            for p in data.get("query", {}).get("pages", {}).values():
                if p["pageid"] in seen or len(p.get("extract", "")) < 150:
                    continue
                seen.add(p["pageid"])
                f.write(json.dumps({"lang": lang, "pageid": p["pageid"], "title": p["title"],
                                    "text": p["extract"][:4000], "fetched": time.strftime("%Y-%m-%d")}, ensure_ascii=False) + "\n")
        time.sleep(0.3)
    print(lang, len(seen), "pages")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), float(sys.argv[3]) if len(sys.argv) > 3 else 90)
