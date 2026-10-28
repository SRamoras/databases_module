#### 2. A list of tables in 3NF, with primary and foreign keys. ####
```
READER(id PK, name, nif UK, email UK, phone, address, registered_at)

PUBLISHER(id PK, name, country)

AUTHOR(id PK, name, nationality)

BOOK(id PK, title, isbn UK, publication_year, publisher_id FK -> PUBLISHER)

COPY(id PK, book_id FK -> BOOK, barcode UK, status)

LOAN(id PK, reader_id FK -> READER, copy_id FK -> COPY, loan_date, due_date, return_date)

RESERVATION(id PK, reader_id FK -> READER, book_id FK -> BOOK, reserved_at, expires_at, status)

FINE(id PK, loan_id UK FK -> LOAN, amount, issued_at, paid_at)
```