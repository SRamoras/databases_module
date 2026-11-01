-- invalid.sql: 5 statements that must fail, each rejected by a different constraint.
-- Run after schema.sql (without ON_ERROR_STOP, so every statement is tried):
--   psql -U postgres -d ex03 < invalid.sql
\set QUIET on

-- Valid data the failing statements need (these all succeed).
INSERT INTO publisher (name, country) VALUES ('Porto Editora', 'Portugal');
INSERT INTO author (name) VALUES ('Ana Silva'), ('Rui Costa');
INSERT INTO book (isbn, title, publication_year, publisher_id)
VALUES ('9780306406157', 'Sample book', 2020,
        (SELECT publisher_id FROM publisher WHERE name = 'Porto Editora'));
INSERT INTO book_author (book_id, author_id, author_order)
VALUES ((SELECT book_id FROM book WHERE isbn = '9780306406157'),
        (SELECT author_id FROM author WHERE name = 'Ana Silva'), 1);
INSERT INTO book_copy (book_id, barcode, condition)
VALUES ((SELECT book_id FROM book WHERE isbn = '9780306406157'), 'BC-0001', 'good'),
       ((SELECT book_id FROM book WHERE isbn = '9780306406157'), 'BC-0002', 'new');
INSERT INTO reader (card_number, name, email, phone, address)
VALUES ('R-0001', 'Maria Santos', 'maria@example.com', '910000000', 'Rua A, Faro');
INSERT INTO loan (reader_id, copy_id, loan_date, due_date)
VALUES ((SELECT reader_id FROM reader WHERE card_number = 'R-0001'),
        (SELECT copy_id FROM book_copy WHERE barcode = 'BC-0001'),
        '2026-10-01', '2026-10-15');

\echo
\echo '1) copy_condition_valid (CHECK)'
-- copy_condition_valid
INSERT INTO book_copy (book_id, barcode, condition)
VALUES ((SELECT book_id FROM book WHERE isbn = '9780306406157'), 'BC-0003', 'broken');

\echo
\echo '2) loan_due_date_14_days (CHECK)'
-- loan_due_date_14_days
INSERT INTO loan (reader_id, copy_id, loan_date, due_date)
VALUES ((SELECT reader_id FROM reader WHERE card_number = 'R-0001'),
        (SELECT copy_id FROM book_copy WHERE barcode = 'BC-0002'),
        '2026-10-02', '2026-10-20');

\echo
\echo '3) book_author_position_unique (composite UNIQUE)'
-- book_author_position_unique
INSERT INTO book_author (book_id, author_id, author_order)
VALUES ((SELECT book_id FROM book WHERE isbn = '9780306406157'),
        (SELECT author_id FROM author WHERE name = 'Rui Costa'), 1);

\echo
\echo '4) book_publisher_id_fkey (FOREIGN KEY, ON DELETE RESTRICT)'
-- book_publisher_id_fkey
DELETE FROM publisher WHERE name = 'Porto Editora';

\echo
\echo '5) one_open_loan_per_copy (partial UNIQUE index)'
-- one_open_loan_per_copy
INSERT INTO loan (reader_id, copy_id, loan_date, due_date)
VALUES ((SELECT reader_id FROM reader WHERE card_number = 'R-0001'),
        (SELECT copy_id FROM book_copy WHERE barcode = 'BC-0001'),
        '2026-10-05', '2026-10-19');