-- schema.sql: municipal library (session 03)
-- Run on an empty database:
--   psql -U postgres -d ex03 -v ON_ERROR_STOP=1 < schema.sql
--
-- Notes
-- * The table for copies is called book_copy because COPY is an SQL keyword.
-- * Dates use date; moments in time use timestamptz; money uses numeric(10,2).
-- * Rules a table structure cannot enforce (at most 5 open loans per reader,
--   reservation order, fine = 0.50 per day late) need a trigger or the
--   application and are not part of this script.

CREATE TABLE publisher (
    publisher_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name         text NOT NULL UNIQUE,
    country      text NOT NULL
);

CREATE TABLE author (
    author_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name      text NOT NULL
);

CREATE TABLE book (
    book_id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    isbn             text NOT NULL UNIQUE,
    title            text NOT NULL,
    publication_year integer NOT NULL,
    -- RESTRICT: a publisher that still has books in the catalogue cannot be
    -- deleted by accident; deleting it would orphan (or erase) the catalogue.
    publisher_id     integer NOT NULL REFERENCES publisher ON DELETE RESTRICT,
    CONSTRAINT isbn_13_digits CHECK (isbn ~ '^[0-9]{13}$'),
    CONSTRAINT publication_year_valid CHECK (publication_year BETWEEN 1 AND 2100)
);

CREATE TABLE book_author (
    -- CASCADE: the list of authors of a book means nothing without the book,
    -- so deleting a book removes its author links (the authors stay).
    book_id      integer NOT NULL REFERENCES book ON DELETE CASCADE,
    author_id    integer NOT NULL REFERENCES author ON DELETE RESTRICT,
    author_order integer NOT NULL,
    PRIMARY KEY (book_id, author_id),
    -- composite UNIQUE: two authors of the same book cannot share a position
    CONSTRAINT book_author_position_unique UNIQUE (book_id, author_order),
    CONSTRAINT author_order_positive CHECK (author_order >= 1)
);

CREATE TABLE book_copy (
    copy_id     integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- RESTRICT: copies and their loan history must not vanish with the book
    book_id     integer NOT NULL REFERENCES book ON DELETE RESTRICT,
    barcode     text NOT NULL UNIQUE,
    acquired_at date NOT NULL DEFAULT current_date,
    condition   text NOT NULL,
    CONSTRAINT copy_condition_valid
        CHECK (condition IN ('new', 'good', 'worn', 'damaged'))
);

CREATE TABLE reader (
    reader_id     integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    card_number   text NOT NULL UNIQUE,
    name          text NOT NULL,
    email         text NOT NULL UNIQUE,
    phone         text NOT NULL,
    address       text NOT NULL,
    registered_at date NOT NULL DEFAULT current_date
);

CREATE TABLE loan (
    loan_id     integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- RESTRICT: a reader (or copy) with loan history cannot be deleted
    reader_id   integer NOT NULL REFERENCES reader ON DELETE RESTRICT,
    copy_id     integer NOT NULL REFERENCES book_copy ON DELETE RESTRICT,
    loan_date   date NOT NULL DEFAULT current_date,
    due_date    date NOT NULL,
    return_date date,  -- empty until the copy is returned
    CONSTRAINT loan_due_date_14_days CHECK (due_date = loan_date + 14),
    CONSTRAINT loan_return_after_loan
        CHECK (return_date IS NULL OR return_date >= loan_date)
);

-- A copy can be in at most one open loan at a time.
CREATE UNIQUE INDEX one_open_loan_per_copy ON loan (copy_id)
    WHERE return_date IS NULL;

CREATE TABLE reservation (
    reservation_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reader_id      integer NOT NULL REFERENCES reader ON DELETE RESTRICT,
    book_id        integer NOT NULL REFERENCES book ON DELETE RESTRICT,
    reserved_at    timestamptz NOT NULL DEFAULT now(),
    status         text NOT NULL DEFAULT 'active',
    CONSTRAINT reservation_status_valid
        CHECK (status IN ('active', 'fulfilled', 'cancelled'))
);

-- A reader does not need two active reservations for the same book.
CREATE UNIQUE INDEX one_active_reservation_per_reader_book
    ON reservation (reader_id, book_id) WHERE status = 'active';

CREATE TABLE fine (
    fine_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- RESTRICT: fines are financial records; the loan behind one must stay.
    -- UNIQUE: at most one fine per loan.
    loan_id integer NOT NULL UNIQUE REFERENCES loan ON DELETE RESTRICT,
    amount  numeric(10,2) NOT NULL,
    paid_at date,  -- empty until the fine is paid
    CONSTRAINT fine_amount_positive CHECK (amount > 0)
);