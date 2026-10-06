"""Download set and card data from the TCGdex API: python fetch_data.py [--limit N] [--set SET_ID]

Writes raw JSON to data/raw/:
  sets.json                  every set with its series and release date
  cards_YYYY-MM-DD.jsonl     one full card object per line, including today's prices

Re-running on the same day resumes: cards already in today's file are skipped.
"""
import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from urllib.parse import quote

import requests

API = "https://api.tcgdex.net/v2/en"
RAW = Path(__file__).parent / "data" / "raw"
WORKERS = 8

session = requests.Session()
session.headers["User-Agent"] = "DSCI551-course-project"


def get(path):
    """GET with retries. Returns None for a 404."""
    for attempt in range(5):
        try:
            resp = session.get(f"{API}/{path}", timeout=30)
            if resp.status_code == 404:
                return None
            if resp.status_code == 200:
                return resp.json()
        except requests.RequestException:
            pass
        time.sleep(2 ** attempt)
    raise RuntimeError(f"gave up on {path}")


def fetch_all(paths, on_result, label):
    """Fetch many paths in parallel and hand each result to on_result as it arrives."""
    failed, done = [], 0
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = {pool.submit(get, p): p for p in paths}
        for future in as_completed(futures):
            done += 1
            try:
                data = future.result()
            except RuntimeError:
                data = None
            if data is None:
                failed.append(futures[future])
            else:
                on_result(data)
            if done % 500 == 0 or done == len(paths):
                print(f"  {label}: {done}/{len(paths)}", flush=True)
    return failed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="only fetch the first N cards (for testing)")
    parser.add_argument("--set", help="only fetch cards from one set, e.g. sv06")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)

    # Sets: the list endpoint lacks series and release date, so fetch each set
    set_ids = [s["id"] for s in get("sets")]
    sets = []

    def keep_set(data):
        data.pop("cards", None)
        sets.append(data)

    failed_sets = fetch_all([f"sets/{i}" for i in set_ids], keep_set, "sets")
    sets.sort(key=lambda s: s["id"])
    (RAW / "sets.json").write_text(json.dumps(sets, ensure_ascii=False), encoding="utf-8")

    # Cards: the list endpoint only has id and name, so fetch each card
    card_ids = [c["id"] for c in get("cards")]
    if args.set:
        card_ids = [i for i in card_ids if i.rsplit("-", 1)[0] == args.set]
    if args.limit:
        card_ids = card_ids[: args.limit]

    out_path = RAW / f"cards_{date.today().isoformat()}.jsonl"
    have = set()
    if out_path.exists():
        with out_path.open(encoding="utf-8") as f:
            have = {json.loads(line)["id"] for line in f if line.strip()}
    todo = [i for i in card_ids if i not in have]
    print(f"{len(card_ids)} cards wanted, {len(have)} already saved, {len(todo)} to fetch", flush=True)

    with out_path.open("a", encoding="utf-8") as out:
        failed_cards = fetch_all(
            [f"cards/{quote(i, safe='')}" for i in todo],
            lambda data: out.write(json.dumps(data, ensure_ascii=False) + "\n"),
            "cards",
        )

    print(f"Saved {len(sets)} sets to {RAW / 'sets.json'}")
    print(f"Saved cards to {out_path}")
    if failed_sets or failed_cards:
        print(f"Not fetched: {len(failed_sets)} sets, {len(failed_cards)} cards")
        for path in (failed_sets + failed_cards)[:20]:
            print("  ", path)


if __name__ == "__main__":
    main()
