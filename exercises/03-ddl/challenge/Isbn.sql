-- isbn.sql: make the database reject invalid ISBN-13 values (session 03 challenge)
-- Run on an empty database:
--   psql -U postgres -d ch03 < isbn.sql

-- Format: digits, with single hyphens only between digits (so no leading,
-- trailing or double hyphen). Then exactly 13 digits. Then the check digit:
-- weights 1,3,1,3,... over the first 12 digits, check = (10 - sum % 10) % 10.
-- CASE is used so the checksum is only computed after the format is known to
-- be good (AND does not guarantee evaluation order, CASE does).
CREATE OR REPLACE FUNCTION is_valid_isbn13(text) RETURNS boolean
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
AS $$
    SELECT CASE
        WHEN $1 !~ '^[0-9]+(-[0-9]+)*$' THEN false
        WHEN length(replace($1, '-', '')) <> 13 THEN false
        ELSE (
            SELECT (10 - sum(d::integer * CASE WHEN i % 2 = 1 THEN 1 ELSE 3 END) % 10) % 10
            FROM regexp_split_to_table(left(replace($1, '-', ''), 12), '')
                 WITH ORDINALITY AS t(d, i)
        ) = right(replace($1, '-', ''), 1)::integer
    END
$$;

CREATE DOMAIN isbn13 AS text
    CONSTRAINT isbn13_valid CHECK (is_valid_isbn13(VALUE));

CREATE TABLE book (
    book_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    isbn    isbn13 NOT NULL UNIQUE,
    title   text NOT NULL
);

-- Valid: must be accepted
INSERT INTO book (isbn, title) VALUES ('978-0-306-40615-7', 'Valid 1');
INSERT INTO book (isbn, title) VALUES ('9781402894626', 'Valid 2');
INSERT INTO book (isbn, title) VALUES ('978-3-16-148410-0', 'Valid 3');

-- Invalid: must be rejected by the domain check
INSERT INTO book (isbn, title) VALUES ('978-0-306-40615-8', 'Wrong check digit');
INSERT INTO book (isbn, title) VALUES ('978-0-306-4061', 'Too short');
INSERT INTO book (isbn, title) VALUES ('-9780306406157', 'Leading hyphen');
INSERT INTO book (isbn, title) VALUES ('978--0306406157', 'Two hyphens in a row');

-- Only the 3 valid ones are stored
SELECT book_id, isbn, title FROM book ORDER BY book_id;