-- S&P 500 Dashboard — Supabase schema
-- Run this once in the Supabase SQL Editor (https://supabase.com/dashboard → SQL Editor)

-- Stores the current S&P 500 member list, refreshed daily by the ETL.
CREATE TABLE IF NOT EXISTS constituents (
    ticker      TEXT        PRIMARY KEY,
    name        TEXT        NOT NULL,
    sector      TEXT        NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Stores one row per ticker per trading day.
-- open/close are the official OHLC values; market_cap is the EOD snapshot.
CREATE TABLE IF NOT EXISTS daily_prices (
    ticker      TEXT        NOT NULL REFERENCES constituents (ticker) ON DELETE CASCADE,
    date        DATE        NOT NULL,
    open        NUMERIC     NOT NULL,
    close       NUMERIC     NOT NULL,
    market_cap  BIGINT,
    PRIMARY KEY (ticker, date)
);

-- Index speeds up the boundary-window queries the dashboard makes.
CREATE INDEX IF NOT EXISTS idx_daily_prices_date ON daily_prices (date);

-- Allow the dashboard's anon key to read both tables.
-- (Only needed if Row Level Security is enabled on your project.)
ALTER TABLE constituents  ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_prices  ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anon read constituents"
    ON constituents FOR SELECT USING (true);

CREATE POLICY "anon read daily_prices"
    ON daily_prices FOR SELECT USING (true);
