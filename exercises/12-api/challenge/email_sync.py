"""The trigger that keeps customer.email and customer.email_address equal.

Used by migration 0004 (upgrade) and by migration 0005 (downgrade), so both create
exactly the same function and trigger.
"""

CREATE_FUNCTION = """
CREATE FUNCTION customer_sync_email() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        -- a new row written by only one of the versions: fill the other column
        IF NEW.email_address IS NULL THEN
            NEW.email_address := NEW.email;
        ELSIF NEW.email IS NULL THEN
            NEW.email := NEW.email_address;
        END IF;
    ELSIF NEW.email IS DISTINCT FROM OLD.email
          AND NEW.email_address IS NOT DISTINCT FROM OLD.email_address THEN
        -- version 1 changed email
        NEW.email_address := NEW.email;
    ELSIF NEW.email_address IS DISTINCT FROM OLD.email_address
          AND NEW.email IS NOT DISTINCT FROM OLD.email THEN
        -- version 2 changed email_address
        NEW.email := NEW.email_address;
    END IF;
    RETURN NEW;
END;
$$
"""

CREATE_TRIGGER = """
CREATE TRIGGER customer_sync_email
BEFORE INSERT OR UPDATE OF email, email_address ON customer
FOR EACH ROW EXECUTE FUNCTION customer_sync_email()
"""

DROP_TRIGGER = "DROP TRIGGER customer_sync_email ON customer"
DROP_FUNCTION = "DROP FUNCTION customer_sync_email()"
