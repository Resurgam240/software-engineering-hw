"""Create the initial schema and database-enforced historical immutability."""

from alembic import op

from campus_market.models import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Install relational keys, partial unique indexes, and append-only triggers."""
    Base.metadata.create_all(op.get_bind())
    op.execute("""
        CREATE FUNCTION reject_historical_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'historical data is immutable'; END $$
    """)
    for table in ("operation_logs", "private_access_logs", "violation_records", "operation_receipts",
                  "reservation_snapshots", "snapshot_images", "image_assets"):
        op.execute(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION reject_historical_mutation()")
    for table in ("product_versions", "product_version_images"):
        op.execute(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION reject_historical_mutation()")
    op.execute("""
        CREATE FUNCTION protect_reservation_history() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.original_message IS DISTINCT FROM NEW.original_message
            OR OLD.product_id IS DISTINCT FROM NEW.product_id
            OR OLD.buyer_id IS DISTINCT FROM NEW.buyer_id
            OR OLD.seller_id IS DISTINCT FROM NEW.seller_id THEN
            RAISE EXCEPTION 'reservation parties and original message are immutable';
          END IF;
          RETURN NEW;
        END $$
    """)
    op.execute("CREATE TRIGGER immutable_reservation_history BEFORE UPDATE ON reservations "
               "FOR EACH ROW EXECUTE FUNCTION protect_reservation_history()")


def downgrade():
    """Destructive downgrades are deliberately unavailable for retained course history."""
    raise RuntimeError("Restore into a separate development database instead of deleting history")
