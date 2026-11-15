"""Incremental daily revenue report: daily_revenue, kept up to date with $merge.

    uv run python daily_revenue.py          # one run on pagila_docs

Each run:
1. reads the watermark from report_state: the highest rentals._id already processed;
2. finds the days (UTC) of the rentals with _id above the watermark;
3. recomputes those days from ALL their rentals (old and new) and merges the result
   into daily_revenue, replacing the whole document of each day;
4. only then moves the watermark to the highest _id it saw.

If the run stops between 3 and 4, the next run recomputes the same days again and
gets the same values: running it twice never counts anything twice.
"""

import os
from datetime import timedelta

from pymongo import MongoClient
from pymongo.database import Database

STATE_ID = "daily_revenue"


def day_pipeline(match: dict) -> list[dict]:
    """rentals -> one document per day: _id (the day), rentals, revenue."""
    return [
        {"$match": match},
        {"$group": {
            "_id": {"$dateTrunc": {"date": "$rental_date", "unit": "day", "timezone": "UTC"}},
            "rentals": {"$sum": 1},
            "revenue": {"$sum": "$amount"},
        }},
    ]


def run_report(db: Database) -> list:
    """One run. Returns the days that were recomputed (empty if nothing was new)."""
    state = db.report_state.find_one({"_id": STATE_ID})
    watermark = state["watermark"] if state else None
    new = {"_id": {"$gt": watermark}} if watermark is not None else {}

    # the highest _id now; rentals inserted after this line wait for the next run
    last = db.rentals.find_one(new, {"_id": 1}, sort=[("_id", -1)])
    if last is None:
        return []
    upto = last["_id"]
    new_upto = {"_id": {"$gt": watermark, "$lte": upto}} if watermark is not None else {"_id": {"$lte": upto}}

    # 2. the days touched by the new rentals
    days = [d["_id"] for d in db.rentals.aggregate([
        {"$match": new_upto},
        {"$group": {"_id": {"$dateTrunc": {"date": "$rental_date", "unit": "day", "timezone": "UTC"}}}},
        {"$sort": {"_id": 1}},
    ])]

    # 3. recompute those days from all their rentals (a range per day, so an index on
    #    rental_date can be used) and replace them in daily_revenue
    if watermark is None:
        match = {}  # first run: every day
    else:
        match = {"$or": [{"rental_date": {"$gte": d, "$lt": d + timedelta(days=1)}} for d in days]}
    db.rentals.aggregate(day_pipeline(match) + [
        {"$merge": {"into": "daily_revenue", "on": "_id",
                    "whenMatched": "replace", "whenNotMatched": "insert"}},
    ])

    # 4. move the watermark only after the merge
    db.report_state.update_one({"_id": STATE_ID}, {"$set": {"watermark": upto}}, upsert=True)
    return days


def full_recompute(db: Database) -> dict:
    """The report computed from scratch, without touching daily_revenue (for checking)."""
    return {d["_id"]: d for d in db.rentals.aggregate(day_pipeline({}))}


if __name__ == "__main__":
    database = MongoClient(os.environ["MONGO_URL"], tz_aware=True)["pagila_docs"]
    touched = run_report(database)
    state = database.report_state.find_one({"_id": STATE_ID})
    print(f"days recomputed: {len(touched)}, watermark: {state['watermark'] if state else None}, "
          f"days in daily_revenue: {database.daily_revenue.count_documents({})}")
