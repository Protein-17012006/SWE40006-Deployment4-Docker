-- Quick Poll 1.1.0: polls can close. NULL means the poll never closes, so 1.0.0 polls stay open.
ALTER TABLE polls ADD COLUMN closes_at timestamptz NULL;
