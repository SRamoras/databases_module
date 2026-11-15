-- The outbox table of the challenge, in ex16.
CREATE TABLE outbox (
    outbox_id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id  integer NOT NULL,
    film_id      integer NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz
);

-- The worker always looks for the oldest unprocessed rows; this index holds only those.
CREATE INDEX outbox_unprocessed ON outbox (outbox_id) WHERE processed_at IS NULL;
