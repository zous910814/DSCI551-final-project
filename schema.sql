-- Pokemon TCG Card Market, Collection, and Deck-Building Database
-- Applied by init_db.py. Only keys and constraints are defined here.
-- Secondary indexes for the physical-design experiments are added separately.

CREATE TABLE IF NOT EXISTS series (
    series_id   VARCHAR(32)  NOT NULL,
    name        VARCHAR(128) NOT NULL,
    PRIMARY KEY (series_id)
);

CREATE TABLE IF NOT EXISTS card_sets (
    set_id              VARCHAR(32)  NOT NULL,
    series_id           VARCHAR(32)  NOT NULL,
    name                VARCHAR(128) NOT NULL,
    release_date        DATE         NULL,
    card_count_official SMALLINT UNSIGNED NULL,
    card_count_total    SMALLINT UNSIGNED NULL,
    PRIMARY KEY (set_id),
    CONSTRAINT fk_sets_series FOREIGN KEY (series_id) REFERENCES series (series_id)
);

CREATE TABLE IF NOT EXISTS cards (
    card_id         VARCHAR(32)  NOT NULL,
    set_id          VARCHAR(32)  NOT NULL,
    local_id        VARCHAR(16)  NOT NULL,
    name            VARCHAR(255) NOT NULL,
    category        ENUM('Pokemon', 'Trainer', 'Energy') NOT NULL,
    rarity          VARCHAR(64)  NULL,
    illustrator     VARCHAR(128) NULL,
    image_url       VARCHAR(255) NULL,
    hp              SMALLINT UNSIGNED NULL,
    stage           VARCHAR(32)  NULL,
    evolve_from     VARCHAR(128) NULL,
    retreat_cost    TINYINT UNSIGNED NULL,
    trainer_type    VARCHAR(32)  NULL,
    energy_type     VARCHAR(32)  NULL,
    regulation_mark VARCHAR(4)   NULL,
    is_standard     BOOLEAN      NOT NULL DEFAULT FALSE,
    is_expanded     BOOLEAN      NOT NULL DEFAULT FALSE,
    PRIMARY KEY (card_id),
    CONSTRAINT fk_cards_set FOREIGN KEY (set_id) REFERENCES card_sets (set_id)
);

CREATE TABLE IF NOT EXISTS card_types (
    type_id     TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
    type_name   VARCHAR(32) NOT NULL,
    PRIMARY KEY (type_id),
    UNIQUE KEY uq_type_name (type_name)
);

CREATE TABLE IF NOT EXISTS card_type_map (
    card_id     VARCHAR(32) NOT NULL,
    type_id     TINYINT UNSIGNED NOT NULL,
    PRIMARY KEY (card_id, type_id),
    CONSTRAINT fk_typemap_card FOREIGN KEY (card_id) REFERENCES cards (card_id) ON DELETE CASCADE,
    CONSTRAINT fk_typemap_type FOREIGN KEY (type_id) REFERENCES card_types (type_id)
);

-- damage is text because the API returns values such as '30+' and '20x'
CREATE TABLE IF NOT EXISTS attacks (
    attack_id   INT UNSIGNED NOT NULL AUTO_INCREMENT,
    card_id     VARCHAR(32)  NOT NULL,
    name        VARCHAR(128) NOT NULL,
    cost        VARCHAR(128) NULL,
    energy_cost TINYINT UNSIGNED NOT NULL DEFAULT 0,
    damage      VARCHAR(16)  NULL,
    effect      TEXT         NULL,
    PRIMARY KEY (attack_id),
    CONSTRAINT fk_attacks_card FOREIGN KEY (card_id) REFERENCES cards (card_id) ON DELETE CASCADE
);

-- api_variant_id repeats across cards, so it is only unique together with card_id
CREATE TABLE IF NOT EXISTS card_variants (
    variant_id      INT UNSIGNED NOT NULL AUTO_INCREMENT,
    card_id         VARCHAR(32)  NOT NULL,
    api_variant_id  VARCHAR(64)  NOT NULL,
    variant_type    VARCHAR(32)  NOT NULL,
    subtype         VARCHAR(64)  NULL,
    size            VARCHAR(16)  NULL,
    stamp           VARCHAR(128) NULL,
    PRIMARY KEY (variant_id),
    UNIQUE KEY uq_variant_card_api (card_id, api_variant_id),
    CONSTRAINT fk_variants_card FOREIGN KEY (card_id) REFERENCES cards (card_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS marketplaces (
    marketplace_id  TINYINT UNSIGNED NOT NULL,
    name            VARCHAR(32) NOT NULL,
    currency        CHAR(3)     NOT NULL,
    PRIMARY KEY (marketplace_id),
    UNIQUE KEY uq_marketplace_name (name)
);

-- One row per variant, marketplace and day. Old snapshots are never overwritten.
CREATE TABLE IF NOT EXISTS price_history (
    variant_id        INT UNSIGNED     NOT NULL,
    marketplace_id    TINYINT UNSIGNED NOT NULL,
    recorded_at       DATE             NOT NULL,
    market_price      DECIMAL(10, 2)   NULL,
    low_price         DECIMAL(10, 2)   NULL,
    mid_price         DECIMAL(10, 2)   NULL,
    high_price        DECIMAL(10, 2)   NULL,
    avg_1d            DECIMAL(10, 2)   NULL,
    avg_7d            DECIMAL(10, 2)   NULL,
    avg_30d           DECIMAL(10, 2)   NULL,
    source_updated_at DATETIME         NULL,
    PRIMARY KEY (variant_id, marketplace_id, recorded_at),
    CONSTRAINT fk_price_variant FOREIGN KEY (variant_id) REFERENCES card_variants (variant_id) ON DELETE CASCADE,
    CONSTRAINT fk_price_marketplace FOREIGN KEY (marketplace_id) REFERENCES marketplaces (marketplace_id)
);

CREATE TABLE IF NOT EXISTS users (
    user_id     INT UNSIGNED NOT NULL AUTO_INCREMENT,
    username    VARCHAR(64)  NOT NULL,
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_username (username)
);

CREATE TABLE IF NOT EXISTS collections (
    user_id     INT UNSIGNED NOT NULL,
    variant_id  INT UNSIGNED NOT NULL,
    quantity    SMALLINT UNSIGNED NOT NULL DEFAULT 1,
    PRIMARY KEY (user_id, variant_id),
    CONSTRAINT fk_collections_user FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
    CONSTRAINT fk_collections_variant FOREIGN KEY (variant_id) REFERENCES card_variants (variant_id),
    CONSTRAINT chk_collections_quantity CHECK (quantity > 0)
);

CREATE TABLE IF NOT EXISTS decks (
    deck_id     INT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id     INT UNSIGNED NOT NULL,
    deck_name   VARCHAR(128) NOT NULL,
    format      ENUM('standard', 'expanded', 'unlimited') NOT NULL DEFAULT 'standard',
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (deck_id),
    CONSTRAINT fk_decks_user FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS deck_cards (
    deck_id     INT UNSIGNED NOT NULL,
    card_id     VARCHAR(32)  NOT NULL,
    quantity    TINYINT UNSIGNED NOT NULL DEFAULT 1,
    PRIMARY KEY (deck_id, card_id),
    CONSTRAINT fk_deckcards_deck FOREIGN KEY (deck_id) REFERENCES decks (deck_id) ON DELETE CASCADE,
    CONSTRAINT fk_deckcards_card FOREIGN KEY (card_id) REFERENCES cards (card_id),
    CONSTRAINT chk_deckcards_quantity CHECK (quantity > 0)
);

INSERT IGNORE INTO marketplaces (marketplace_id, name, currency) VALUES
    (1, 'TCGplayer', 'USD'),
    (2, 'Cardmarket', 'EUR');
