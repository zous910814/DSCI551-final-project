"""REST API for the PTCG database, plus the static frontend in web/.

Start with:  uvicorn api:app --reload
Then open:   http://localhost:8000        (interactive API docs at /docs)
"""
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from statistics import median
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from db import get_connection

PAGE_SIZE = 24
TCGPLAYER, CARDMARKET = 1, 2

app = FastAPI(title="PTCG Market API")


@contextmanager
def cursor():
    """A dictionary cursor on a fresh connection; commits on success."""
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    try:
        yield cur
        conn.commit()
    finally:
        cur.close()
        conn.close()


def query(sql, params=()):
    with cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def execute(sql, params=()):
    with cursor() as cur:
        cur.execute(sql, params)
        return cur.lastrowid


def latest_date():
    """The newest price snapshot date; every price query filters on it."""
    return query("SELECT MAX(recorded_at) AS d FROM price_history")[0]["d"]


def demo_user_id():
    """The app has no login; everything belongs to one demo user."""
    execute("INSERT IGNORE INTO users (username) VALUES ('demo')")
    return query("SELECT user_id FROM users WHERE username = 'demo'")[0]["user_id"]


# Cheapest TCGplayer price among a card's variants on the latest snapshot
CHEAPEST = f"""(SELECT MIN(p.market_price)
    FROM card_variants v JOIN price_history p ON p.variant_id = v.variant_id
   WHERE v.card_id = dc.card_id AND p.marketplace_id = {TCGPLAYER} AND p.recorded_at = %s)"""


# ---------- Catalog ----------

@app.get("/api/meta")
def meta():
    return {
        "sets": query("SELECT set_id, name FROM card_sets ORDER BY release_date DESC"),
        "types": [r["type_name"] for r in query("SELECT type_name FROM card_types ORDER BY type_name")],
        "counts": query("SELECT (SELECT COUNT(*) FROM cards) AS cards, (SELECT COUNT(*) FROM card_sets) AS sets")[0],
        "latestDate": latest_date(),
    }


@app.get("/api/cards")
def search_cards(name: str = "", category: str = "", type: str = "", set: str = "", format: str = "",
                 maxPrice: Optional[float] = None, sort: str = "price_desc", page: int = 1):
    where, params = ["1 = 1"], [latest_date()]
    if name:
        where.append("c.name LIKE %s")
        params.append(f"%{name}%")
    if category in ("Pokemon", "Trainer", "Energy"):
        where.append("c.category = %s")
        params.append(category)
    if type:
        where.append("""EXISTS (SELECT 1 FROM card_type_map m JOIN card_types t ON t.type_id = m.type_id
                                 WHERE m.card_id = c.card_id AND t.type_name = %s)""")
        params.append(type)
    if set:
        where.append("c.set_id = %s")
        params.append(set)
    if format == "standard":
        where.append("c.is_standard = TRUE")
    if format == "expanded":
        where.append("c.is_expanded = TRUE")
    if maxPrice is not None:
        where.append("p.market_price <= %s")
        params.append(maxPrice)
    order = {
        "price_desc": "p.market_price IS NULL, p.market_price DESC",
        "price_asc": "p.market_price IS NULL, p.market_price ASC",
        "name": "c.name ASC",
    }.get(sort, "p.market_price IS NULL, p.market_price DESC")

    source = f"""FROM cards c
        JOIN card_sets s ON s.set_id = c.set_id
        JOIN card_variants v ON v.card_id = c.card_id
        LEFT JOIN price_history p ON p.variant_id = v.variant_id
             AND p.marketplace_id = {TCGPLAYER} AND p.recorded_at = %s
        WHERE {' AND '.join(where)}"""
    page = max(1, page)
    total = query(f"SELECT COUNT(*) AS total {source}", params)[0]["total"]
    rows = query(
        f"""SELECT c.card_id, c.name, c.image_url, s.name AS set_name, v.variant_type, p.market_price
            {source} ORDER BY {order}, c.card_id, v.variant_id LIMIT %s OFFSET %s""",
        params + [PAGE_SIZE, (page - 1) * PAGE_SIZE])
    return {"total": total, "page": page, "pages": max(1, -(-total // PAGE_SIZE)), "rows": rows}


@app.get("/api/cards/suggest")
def suggest_cards(name: str = ""):
    if not name.strip():
        return []
    return query(
        """SELECT c.card_id, c.name, c.local_id, s.name AS set_name
             FROM cards c JOIN card_sets s ON s.set_id = c.set_id
            WHERE c.name LIKE %s ORDER BY s.release_date DESC, c.card_id LIMIT 8""", (f"%{name.strip()}%",))


@app.get("/api/cards/{card_id}")
def card_detail(card_id: str):
    cards = query(
        """SELECT c.*, s.name AS set_name, s.card_count_official, se.name AS series_name
             FROM cards c JOIN card_sets s ON s.set_id = c.set_id JOIN series se ON se.series_id = s.series_id
            WHERE c.card_id = %s""", (card_id,))
    if not cards:
        raise HTTPException(404, "Card not found")
    date = latest_date()
    return {
        "card": cards[0],
        "types": [r["type_name"] for r in query(
            """SELECT t.type_name FROM card_type_map m JOIN card_types t ON t.type_id = m.type_id
                WHERE m.card_id = %s""", (card_id,))],
        "attacks": query("SELECT name, cost, damage, effect FROM attacks WHERE card_id = %s ORDER BY attack_id",
                         (card_id,)),
        "variants": query(
            f"""SELECT v.variant_id, v.variant_type, v.subtype, v.size, v.stamp,
                       t.market_price AS tcgplayer, cm.market_price AS cardmarket, cm.avg_7d
                  FROM card_variants v
                  LEFT JOIN price_history t ON t.variant_id = v.variant_id
                       AND t.marketplace_id = {TCGPLAYER} AND t.recorded_at = %s
                  LEFT JOIN price_history cm ON cm.variant_id = v.variant_id
                       AND cm.marketplace_id = {CARDMARKET} AND cm.recorded_at = %s
                 WHERE v.card_id = %s ORDER BY v.variant_id""", (date, date, card_id)),
        "history": query(
            f"""SELECT p.variant_id, p.recorded_at, p.market_price
                  FROM price_history p JOIN card_variants v ON v.variant_id = p.variant_id
                 WHERE v.card_id = %s AND p.marketplace_id = {TCGPLAYER} AND p.market_price IS NOT NULL
                 ORDER BY p.recorded_at""", (card_id,)),
    }


# ---------- Decks and collection ----------

class NewDeck(BaseModel):
    name: str
    format: str = "standard"


class DeckCard(BaseModel):
    card_id: str
    quantity: int = 1


class Quantity(BaseModel):
    quantity: int


class CollectionItem(BaseModel):
    variant_id: int


def own_deck(deck_id):
    decks = query("SELECT deck_id, deck_name, format FROM decks WHERE deck_id = %s AND user_id = %s",
                  (deck_id, demo_user_id()))
    if not decks:
        raise HTTPException(404, "Deck not found")
    return decks[0]


@app.get("/api/decks")
def list_decks():
    return query(
        f"""SELECT d.deck_id, d.deck_name, d.format,
                   COALESCE(SUM(dc.quantity), 0) AS cards,
                   ROUND(COALESCE(SUM(dc.quantity * {CHEAPEST}), 0), 2) AS cost
              FROM decks d LEFT JOIN deck_cards dc ON dc.deck_id = d.deck_id
             WHERE d.user_id = %s GROUP BY d.deck_id, d.deck_name, d.format ORDER BY d.deck_id""",
        (latest_date(), demo_user_id()))


@app.post("/api/decks")
def create_deck(body: NewDeck):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Deck name is required")
    deck_format = body.format if body.format in ("standard", "expanded", "unlimited") else "standard"
    deck_id = execute("INSERT INTO decks (user_id, deck_name, format) VALUES (%s, %s, %s)",
                      (demo_user_id(), name, deck_format))
    return {"deck_id": deck_id}


@app.delete("/api/decks/{deck_id}")
def delete_deck(deck_id: int):
    execute("DELETE FROM decks WHERE deck_id = %s AND user_id = %s", (deck_id, demo_user_id()))
    return {"ok": True}


@app.get("/api/decks/{deck_id}")
def deck_detail(deck_id: int):
    deck = own_deck(deck_id)
    cards = query(
        f"""SELECT dc.card_id, dc.quantity, c.name, c.category, c.is_standard, c.is_expanded,
                   c.regulation_mark, s.name AS set_name, {CHEAPEST} AS unit_price,
                   (SELECT COALESCE(SUM(col.quantity), 0)
                      FROM collections col JOIN card_variants v2 ON v2.variant_id = col.variant_id
                     WHERE col.user_id = %s AND v2.card_id = dc.card_id) AS owned
              FROM deck_cards dc
              JOIN cards c ON c.card_id = dc.card_id
              JOIN card_sets s ON s.set_id = c.set_id
             WHERE dc.deck_id = %s
             ORDER BY FIELD(c.category, 'Pokemon', 'Trainer', 'Energy'), c.name""",
        (latest_date(), demo_user_id(), deck_id))
    return {"deck": deck, "cards": cards}


@app.post("/api/decks/{deck_id}/cards")
def add_deck_card(deck_id: int, body: DeckCard):
    own_deck(deck_id)
    if not query("SELECT 1 FROM cards WHERE card_id = %s", (body.card_id,)):
        raise HTTPException(404, "Card not found")
    execute(
        """INSERT INTO deck_cards (deck_id, card_id, quantity) VALUES (%s, %s, %s)
           ON DUPLICATE KEY UPDATE quantity = LEAST(60, quantity + VALUES(quantity))""",
        (deck_id, body.card_id, min(60, max(1, body.quantity))))
    return {"ok": True}


@app.put("/api/decks/{deck_id}/cards/{card_id}")
def set_deck_card_quantity(deck_id: int, card_id: str, body: Quantity):
    own_deck(deck_id)
    if body.quantity <= 0:
        execute("DELETE FROM deck_cards WHERE deck_id = %s AND card_id = %s", (deck_id, card_id))
    else:
        execute("UPDATE deck_cards SET quantity = %s WHERE deck_id = %s AND card_id = %s",
                (min(60, body.quantity), deck_id, card_id))
    return {"ok": True}


@app.post("/api/collection")
def add_to_collection(body: CollectionItem):
    if not query("SELECT 1 FROM card_variants WHERE variant_id = %s", (body.variant_id,)):
        raise HTTPException(404, "Variant not found")
    execute(
        """INSERT INTO collections (user_id, variant_id, quantity) VALUES (%s, %s, 1)
           ON DUPLICATE KEY UPDATE quantity = quantity + 1""", (demo_user_id(), body.variant_id))
    return {"ok": True}


# ---------- Query Lab ----------
# Experiments run on price_exp, an index-free copy of price_history, because the real
# table's primary key and foreign-key indexes would hide the "no index" case.

LAB_DESIGNS = {
    "none": None,
    "price": "(market_price)",
    "eq_first": "(marketplace_id, recorded_at, market_price)",
    "range_first": "(market_price, marketplace_id, recorded_at)",
}
LAB_SQL = """SELECT c.name, s.name AS set_name, v.variant_type, p.market_price
FROM cards c
JOIN card_sets s     ON s.set_id = c.set_id
JOIN card_variants v ON v.card_id = c.card_id
JOIN price_exp p     ON p.variant_id = v.variant_id
WHERE c.is_standard = TRUE
  AND c.category = 'Pokemon'
  AND p.marketplace_id = %s
  AND p.recorded_at = %s
  AND p.market_price < %s
ORDER BY p.market_price DESC"""
lab_lock = threading.Lock()  # one experiment at a time: they rebuild the same index


class LabRun(BaseModel):
    designs: list[str]
    cap: float
    marketplace: int = TCGPLAYER
    refresh: bool = False


def run_design(cur, design, params):
    cur.execute(
        """SELECT 1 FROM information_schema.statistics
            WHERE table_schema = DATABASE() AND table_name = 'price_exp' AND index_name = 'idx_lab' LIMIT 1""")
    if cur.fetchall():
        cur.execute("ALTER TABLE price_exp DROP INDEX idx_lab")
    if LAB_DESIGNS[design]:
        cur.execute(f"CREATE INDEX idx_lab ON price_exp {LAB_DESIGNS[design]}")
    cur.execute("ANALYZE TABLE price_exp")
    cur.fetchall()

    cur.execute(f"EXPLAIN ANALYZE {LAB_SQL}", params)
    plan = cur.fetchall()[0]["EXPLAIN"]
    times, row_count = [], 0
    for _ in range(5):
        start = time.perf_counter()
        cur.execute(LAB_SQL, params)
        row_count = len(cur.fetchall())
        times.append((time.perf_counter() - start) * 1000)
    return {"design": design, "index": LAB_DESIGNS[design], "plan": plan,
            "ms": round(median(times), 2), "rows": row_count}


@app.post("/api/lab/run")
def lab_run(body: LabRun):
    designs = [d for d in body.designs if d in LAB_DESIGNS]
    if not designs:
        raise HTTPException(400, "Pick at least one index design")
    marketplace = CARDMARKET if body.marketplace == CARDMARKET else TCGPLAYER
    date = latest_date()
    params = (marketplace, date, body.cap)
    with lab_lock, cursor() as cur:
        if body.refresh:
            cur.execute("DROP TABLE IF EXISTS price_exp")
        cur.execute("SHOW TABLES LIKE 'price_exp'")
        if not cur.fetchall():
            cur.execute("CREATE TABLE price_exp AS SELECT * FROM price_history")
        cur.execute("SELECT COUNT(*) AS n FROM price_exp")
        table_rows = cur.fetchall()[0]["n"]
        results = [run_design(cur, design, params) for design in designs]
    shown_sql = LAB_SQL.replace("%s", "{}").format(marketplace, f"'{date}'", f"{body.cap:.2f}")
    return {"sql": shown_sql + ";", "tableRows": table_rows, "results": results}


# The frontend; mounted last so it does not shadow the /api routes
app.mount("/", StaticFiles(directory=Path(__file__).parent / "web", html=True), name="web")
