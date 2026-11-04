"""A source restore must not turn retained production bookings into data loss."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import DateTime

from app.models.booking import Booking
from app.models.customer_workspace import CustomerBookingLink


def test_booking_storage_keeps_production_scheduling_fields():
    for name in ("scheduled_start", "scheduled_end", "owner_accepted_at"):
        column = Booking.__table__.c[name]
        assert column.nullable
        assert isinstance(column.type, DateTime)
        assert column.type.timezone
        assert column.default is None and column.server_default is None


def test_booking_link_storage_keeps_nullable_slot_and_foreign_key():
    column = CustomerBookingLink.__table__.c.slot_id
    assert column.nullable
    assert {fk.target_fullname for fk in column.foreign_keys} == {"customer_app_slots.id"}


def test_storage_migration_only_adds_fields_and_relaxes_constraint(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "alembic/versions/0017_preserve_booking_storage.py"
    spec = importlib.util.spec_from_file_location("booking_storage_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    changes = []
    monkeypatch.setattr(migration, "op", SimpleNamespace(
        alter_column=lambda *args, **kwargs: changes.append(("alter", args, kwargs)),
        add_column=lambda *args: changes.append(("add", args)),
    ))
    migration.upgrade()
    assert changes[0][1] == ("customer_app_booking_links", "slot_id")
    assert changes[0][2]["nullable"] is True
    assert len(changes) == 4
    for change, name in zip(changes[1:], ("scheduled_start", "scheduled_end", "owner_accepted_at")):
        assert change[0] == "add" and change[1][0] == "bookings"
        column = change[1][1]
        assert column.name == name and column.nullable and column.type.timezone
    with pytest.raises(RuntimeError, match="no automatic destructive downgrade"):
        migration.downgrade()
