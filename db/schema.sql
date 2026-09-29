-- schema.sql - The database tables for the Northstar chatbot demo.
--
-- WHAT THIS FILE DOES
-- Creates two tables in the PostgreSQL database (hosted on Supabase):
--
--   customers     - one row per customer (name, balance, income, card status...)
--   transactions  - one row per transaction, linked to a customer by customer_id
--
-- One customer can have many transactions. This "one-to-many" link is the
-- most common pattern in real banking databases.
--
-- HOW TO RUN IT
--   Option A: python db/setup_db.py   (also loads the demo customers)
--   Option B: paste this file into Supabase -> SQL Editor -> Run
--
-- "if not exists" means running this file twice is safe: existing tables are kept.

-- ---------------------------------------------------------------------------
-- CUSTOMERS TABLE
-- ---------------------------------------------------------------------------
create table if not exists customers (
    customer_id        text primary key,          -- e.g. 'CUST-1001'; must be unique
    name               text not null,             -- e.g. 'Alex Morgan'
    account_type       text not null,             -- e.g. 'Everyday checking'
    account_last_four  text not null,             -- last 4 digits only, never the full number
    balance            numeric(12, 2) not null,   -- money: up to 12 digits, 2 after the decimal point
    monthly_income     numeric(12, 2) not null,
    monthly_debt       numeric(12, 2) not null,
    credit_band        text not null,             -- 'Fair', 'Good', 'Very good', 'Excellent'
    card_status        text not null              -- e.g. 'Active', 'Blocked'
);

-- ---------------------------------------------------------------------------
-- TRANSACTIONS TABLE
-- ---------------------------------------------------------------------------
create table if not exists transactions (
    transaction_id  bigint generated always as identity primary key,  -- automatic number 1, 2, 3...
    customer_id     text not null references customers (customer_id)  -- must match a real customer
                    on delete cascade,                                -- deleting a customer deletes their transactions
    txn_date        date not null,
    description     text not null,
    amount          numeric(12, 2) not null   -- negative = money out, positive = money in
);

-- An index works like a book's index: it lets the database quickly find
-- all transactions for one customer without reading the whole table.
create index if not exists transactions_customer_date_idx
    on transactions (customer_id, txn_date desc);

-- ---------------------------------------------------------------------------
-- SECURITY
-- ---------------------------------------------------------------------------
-- Supabase also exposes tables through a public web API. Turning on
-- "row level security" with no rules blocks that public API from reading
-- these tables. Our app connects directly as the database owner, which is
-- not affected, so the chatbot still works.
alter table customers enable row level security;
alter table transactions enable row level security;
