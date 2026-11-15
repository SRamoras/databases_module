"""Task 3: the incremental report changes only the new days, equals a full
recomputation, and a run with nothing new changes nothing.

Runs on a copy of pagila_docs.rentals in the database ch14_test (dropped at the
end), so the collections of the exercises are never changed.
"""

import os
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from bson.decimal128 import Decimal128
from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daily_revenue import full_recompute, run_report  # noqa: E402

DAY_28 = datetime(2026, 7, 28, tzinfo=UTC)
DAY_29 = datetime(2026, 7, 29, tzinfo=UTC)


@pytest.fixture(scope="module")
def db():
    client = MongoClient(os.environ["MONGO_URL"], tz_aware=True)
    client.drop_database("ch14_test")
    client["pagila_docs"].rentals.aggregate([{"$out": {"db": "ch14_test", "coll": "rentals"}}])
    test_db = client["ch14_test"]
    yield test_db
    client.drop_database("ch14_test")


def snapshot(db) -> dict:
    return {d["_id"]: d for d in db.daily_revenue.find()}


def show(label: str, doc: dict | None) -> str:
    if doc is None:
        return f"{label}: (none)"
    return f"{label}: rentals {doc['rentals']}, revenue {doc['revenue']}"


def test_incremental_report(db):
    # 1. full run
    days = run_report(db)
    first = snapshot(db)
    print(f"\nrun 1: {len(days)} days computed, {len(first)} days in daily_revenue, "
          f"watermark {db.report_state.find_one()['watermark']}")
    print(show("  2026-07-28", first.get(DAY_28)))
    print(show("  2026-07-29", first.get(DAY_29)))
    assert first == full_recompute(db)
    assert DAY_28 in first and DAY_29 not in first

    # 2. five new rentals above the current maximum _id
    top = db.rentals.find_one(sort=[("_id", -1)])["_id"]
    new = [
        (DAY_28.replace(hour=23, minute=1), "1.99"),
        (DAY_28.replace(hour=23, minute=2), "2.99"),
        (DAY_28.replace(hour=23, minute=3), "0.99"),
        (DAY_29.replace(hour=9), "4.99"),
        (DAY_29.replace(hour=10), "3.99"),
    ]
    db.rentals.insert_many([
        {"_id": top + i + 1, "customer_id": 1, "film_id": 1, "title": "ACADEMY DINOSAUR",
         "categories": ["Games", "New", "Travel"], "store_id": 1,
         "rental_date": when, "return_date": None, "amount": Decimal128(amount)}
        for i, (when, amount) in enumerate(new)
    ])
    print(f"inserted 5 rentals: _id {top + 1} to {top + 5}")

    # 3. second run: only those 2 days change
    days = run_report(db)
    second = snapshot(db)
    changed = sorted(d for d in second if second[d] != first.get(d))
    print(f"run 2: days recomputed {[d.date().isoformat() for d in days]}, "
          f"days whose document changed {[d.date().isoformat() for d in changed]}")
    print(show("  2026-07-28", second.get(DAY_28)))
    print(show("  2026-07-29", second.get(DAY_29)))
    assert days == [DAY_28, DAY_29]
    assert changed == [DAY_28, DAY_29]
    assert second[DAY_28]["rentals"] == first[DAY_28]["rentals"] + 3
    assert second[DAY_28]["revenue"].to_decimal() == first[DAY_28]["revenue"].to_decimal() + Decimal("5.97")
    assert second[DAY_29]["rentals"] == 2
    assert second[DAY_29]["revenue"].to_decimal() == Decimal("8.98")
    assert len(second) == len(first) + 1

    # 4. equal to a full recomputation from scratch
    assert second == full_recompute(db)
    print(f"run 2 equals a full recomputation: {len(second)} days")

    # 5. third run: nothing new, nothing changes
    days = run_report(db)
    third = snapshot(db)
    print(f"run 3: days recomputed {len(days)}, daily_revenue unchanged: {third == second}")
    assert days == []
    assert third == second
