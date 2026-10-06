"""Load downloaded TCGdex data into MySQL: python load_data.py [cards_YYYY-MM-DD.jsonl]

Defaults to the newest cards file in data/raw/. The date in the file name becomes
price_history.recorded_at, so each day's download adds one price snapshot.
Safe to re-run: catalog rows are updated in place and a day's prices are not duplicated.
"""
import json
import sys
from datetime import date, datetime
from pathlib import Path

from db import get_connection

RAW = Path(__file__).parent / "data" / "raw"
BATCH = 1000
TCGPLAYER, CARDMARKET = 1, 2
# TCGplayer lists prices per print; this maps a variant type to its print name
TCG_PRINT = {"normal": "normal", "holo": "holofoil", "reverse": "reverse-holofoil"}


def run_many(cur, sql, rows):
    for i in range(0, len(rows), BATCH):
        cur.executemany(sql, rows[i:i + BATCH])


def price(value):
    """The API uses 0 and null for 'no price'."""
    return value if value else None


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None) if value else None


def tcgplayer_row(variant_type, data):
    prints = {k: v for k, v in data.items() if isinstance(v, dict)}
    chosen = prints.get(TCG_PRINT.get(variant_type))
    if chosen is None and len(prints) == 1:
        chosen = next(iter(prints.values()))
    if chosen is None:
        return None
    return (price(chosen.get("marketPrice")), price(chosen.get("lowPrice")), price(chosen.get("midPrice")),
            price(chosen.get("highPrice")), None, None, None, timestamp(data.get("updated")))


def cardmarket_row(variant_type, data):
    # Foil versions have their own '-holo' fields when Cardmarket tracks them separately
    s = "-holo" if variant_type != "normal" and data.get("avg-holo") is not None else ""
    return (price(data.get("trend" + s)) or price(data.get("avg" + s)), price(data.get("low" + s)), None, None,
            price(data.get("avg1" + s)), price(data.get("avg7" + s)), price(data.get("avg30" + s)),
            timestamp(data.get("updated")))


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else max(RAW.glob("cards_*.jsonl"))
    if not path.exists():
        path = RAW / path.name
    snapshot = date.fromisoformat(path.stem.split("_")[1])

    sets = json.loads((RAW / "sets.json").read_text(encoding="utf-8"))
    cards = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                cards.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # a partly written last line while a download is still running
    known_sets = {s["id"] for s in sets}
    skipped = [c["id"] for c in cards if c["set"]["id"] not in known_sets]
    cards = [c for c in cards if c["set"]["id"] in known_sets]
    print(f"Loading {len(cards)} cards from {path.name} (snapshot {snapshot})")

    conn = get_connection()
    cur = conn.cursor()

    series = {s["serie"]["id"]: s["serie"]["name"] for s in sets}
    run_many(cur, "INSERT INTO series (series_id, name) VALUES (%s, %s) "
                  "ON DUPLICATE KEY UPDATE name = VALUES(name)", list(series.items()))
    run_many(cur, "INSERT INTO card_sets (set_id, series_id, name, release_date, card_count_official, "
                  "card_count_total) VALUES (%s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE "
                  "name = VALUES(name), release_date = VALUES(release_date), "
                  "card_count_official = VALUES(card_count_official), card_count_total = VALUES(card_count_total)",
             [(s["id"], s["serie"]["id"], s["name"], s.get("releaseDate"),
               s["cardCount"].get("official"), s["cardCount"].get("total")) for s in sets])

    run_many(cur, "INSERT INTO cards (card_id, set_id, local_id, name, category, rarity, illustrator, image_url, "
                  "hp, stage, evolve_from, retreat_cost, trainer_type, energy_type, regulation_mark, is_standard, "
                  "is_expanded) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                  "ON DUPLICATE KEY UPDATE name = VALUES(name), rarity = VALUES(rarity), "
                  "image_url = VALUES(image_url), regulation_mark = VALUES(regulation_mark), "
                  "is_standard = VALUES(is_standard), is_expanded = VALUES(is_expanded)",
             [(c["id"], c["set"]["id"], c["localId"], c["name"], c["category"], c.get("rarity"),
               c.get("illustrator"), c.get("image"), c.get("hp"), c.get("stage"), c.get("evolveFrom"),
               c.get("retreat"), c.get("trainerType"), c.get("energyType"), c.get("regulationMark"),
               bool(c.get("legal", {}).get("standard")), bool(c.get("legal", {}).get("expanded")))
              for c in cards])

    type_names = sorted({t for c in cards for t in c.get("types") or []})
    run_many(cur, "INSERT IGNORE INTO card_types (type_name) VALUES (%s)", [(t,) for t in type_names])
    cur.execute("SELECT type_name, type_id FROM card_types")
    type_ids = dict(cur.fetchall())
    run_many(cur, "INSERT IGNORE INTO card_type_map (card_id, type_id) VALUES (%s, %s)",
             [(c["id"], type_ids[t]) for c in cards for t in set(c.get("types") or [])])

    # Attacks have no natural key, so replace them for every card being loaded
    run_many(cur, "DELETE FROM attacks WHERE card_id = %s", [(c["id"],) for c in cards])
    run_many(cur, "INSERT INTO attacks (card_id, name, cost, energy_cost, damage, effect) "
                  "VALUES (%s, %s, %s, %s, %s, %s)",
             [(c["id"], a.get("name") or "", ",".join(a.get("cost") or []) or None, len(a.get("cost") or []),
               str(a["damage"]) if a.get("damage") is not None else None, a.get("effect"))
              for c in cards for a in c.get("attacks") or []])

    run_many(cur, "INSERT INTO card_variants (card_id, api_variant_id, variant_type, subtype, size, stamp) "
                  "VALUES (%s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE variant_type = VALUES(variant_type), "
                  "subtype = VALUES(subtype), size = VALUES(size), stamp = VALUES(stamp)",
             [(c["id"], v["variantId"], v["type"], v.get("subtype"), v.get("size"),
               ",".join(v.get("stamp") or []) or None)
              for c in cards for v in c.get("variants_detailed") or []])
    cur.execute("SELECT card_id, api_variant_id, variant_id FROM card_variants")
    variant_ids = {(card_id, api_id): variant_id for card_id, api_id, variant_id in cur.fetchall()}

    prices = []
    for c in cards:
        for v in c.get("variants_detailed") or []:
            pricing = v.get("pricing") or {}
            variant_id = variant_ids[(c["id"], v["variantId"])]
            for marketplace, row in (
                (TCGPLAYER, tcgplayer_row(v["type"], pricing["tcgplayer"]) if pricing.get("tcgplayer") else None),
                (CARDMARKET, cardmarket_row(v["type"], pricing["cardmarket"]) if pricing.get("cardmarket") else None),
            ):
                if row and any(x is not None for x in row[:7]):
                    prices.append((variant_id, marketplace, snapshot) + row)
    run_many(cur, "INSERT INTO price_history (variant_id, marketplace_id, recorded_at, market_price, low_price, "
                  "mid_price, high_price, avg_1d, avg_7d, avg_30d, source_updated_at) "
                  "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE "
                  "market_price = VALUES(market_price), low_price = VALUES(low_price), "
                  "mid_price = VALUES(mid_price), high_price = VALUES(high_price), avg_1d = VALUES(avg_1d), "
                  "avg_7d = VALUES(avg_7d), avg_30d = VALUES(avg_30d), "
                  "source_updated_at = VALUES(source_updated_at)", prices)
    conn.commit()

    for table in ("series", "card_sets", "cards", "card_types", "card_type_map", "attacks", "card_variants",
                  "price_history"):
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        print(f"  {table:<14} {cur.fetchone()[0]:>7} rows")
    if skipped:
        print(f"Skipped {len(skipped)} cards whose set is not in sets.json, e.g. {skipped[:5]}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
