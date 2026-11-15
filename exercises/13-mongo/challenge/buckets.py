"""Bucket pattern for the rental history of each customer.

    uv run python buckets.py load         # tasks 3 and 4: fill rental_buckets and rental_history
    uv run python buckets.py concurrency  # task 2: 8 threads add 120 rentals to one customer at once
    uv run python buckets.py concurrency --no-unique   # the same without the unique indexes
    uv run python buckets.py compare      # task 5: customer 380, sizes and read times
    uv run python buckets.py large        # the same for a made-up customer with 20,000 rentals

Reads the collection rentals of pagila_docs (exercise 13). MONGO_URL comes from the
environment.
"""

import os
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import bson
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import DuplicateKeyError

BUCKET_SIZE = 50
MAX_ATTEMPTS = 5
duplicate_key_retries = 0  # how many times add_rental had to repeat (for the evidence)

db = MongoClient(os.environ["MONGO_URL"], tz_aware=True)["pagila_docs"]


# ---------- task 1: the collection and its indexes ----------


def create_indexes(buckets) -> None:
    # One document per (customer, seq): two buckets can never have the same number.
    buckets.create_index([("customer_id", ASCENDING), ("seq", ASCENDING)], unique=True,
                         name="customer_seq")
    # At most one OPEN bucket (count < 50) per customer. This is what makes the
    # upsert of add_rental safe when two calls run at the same time (see the README).
    buckets.create_index([("customer_id", ASCENDING)], unique=True, name="one_open_bucket",
                         partialFilterExpression={"count": {"$lt": BUCKET_SIZE}})


# ---------- task 2: add_rental ----------


def add_rental(customer_id: int, rental: dict, buckets=None) -> None:
    """Add one rental to the customer's open bucket, or open a new one.

    The write is a single updateOne with upsert:
    - filter: this customer's bucket with count < 50 (the open one, if any);
    - $push the rental and $inc count: if the open bucket exists, it gets the rental;
    - $setOnInsert seq: only used when no bucket is open and the upsert creates one.

    The read before it only finds the number the new bucket would get. If another
    call opens that bucket first, the insert breaks a unique index and the whole
    call is repeated, now finding the open bucket.
    """
    global duplicate_key_retries
    buckets = buckets if buckets is not None else db.rental_buckets
    for _ in range(MAX_ATTEMPTS):
        last = buckets.find_one({"customer_id": customer_id}, {"seq": 1},
                                sort=[("seq", DESCENDING)])
        next_seq = last["seq"] + 1 if last else 1
        try:
            buckets.update_one(
                {"customer_id": customer_id, "count": {"$lt": BUCKET_SIZE}},
                {
                    "$push": {"rentals": rental},
                    "$inc": {"count": 1},
                    "$setOnInsert": {"seq": next_seq},
                },
                upsert=True,
            )
            return
        except DuplicateKeyError:
            # another call opened a bucket at the same time: try again
            duplicate_key_retries += 1
            continue
    raise RuntimeError(f"could not add rental {rental['rental_id']} for customer {customer_id}")


def bucket_rental(doc: dict) -> dict:
    """What a bucket keeps of each rental (customer_id is already in the bucket)."""
    fields = ("film_id", "title", "rental_date", "return_date", "amount")
    return {"rental_id": doc["_id"]} | {k: doc[k] for k in fields}


# ---------- tasks 3 and 4: loading ----------


def load() -> None:
    db.rental_buckets.drop()
    create_indexes(db.rental_buckets)

    started = time.perf_counter()
    n = 0
    cursor = db.rentals.find({}, sort=[("rental_date", ASCENDING), ("_id", ASCENDING)],
                             batch_size=5000)
    for doc in cursor:
        add_rental(doc["customer_id"], bucket_rental(doc))
        n += 1
    print(f"rental_buckets: {n} rentals added with add_rental in "
          f"{time.perf_counter() - started:.1f}s, {db.rental_buckets.count_documents({})} buckets")

    started = time.perf_counter()
    db.rentals.aggregate([
        {"$sort": {"rental_date": 1, "_id": 1}},
        {"$group": {
            "_id": "$customer_id",
            "count": {"$sum": 1},
            "rentals": {"$push": {
                "rental_id": "$_id", "film_id": "$film_id", "title": "$title",
                "rental_date": "$rental_date", "return_date": "$return_date", "amount": "$amount",
            }},
        }},
        {"$out": "rental_history"},
    ], allowDiskUse=True)
    print(f"rental_history: {db.rental_history.count_documents({})} documents in "
          f"{time.perf_counter() - started:.1f}s")

    stats = list(db.rental_buckets.aggregate([
        {"$group": {"_id": None, "buckets": {"$sum": 1}, "max_count": {"$max": "$count"},
                    "rentals": {"$sum": "$count"}, "full": {"$sum": {"$cond": [{"$eq": ["$count", 50]}, 1, 0]}}}},
    ]))[0]
    print(f"buckets: {stats['buckets']}, rentals in buckets: {stats['rentals']}, "
          f"largest bucket: {stats['max_count']}, full buckets: {stats['full']}")
    for b in db.rental_buckets.find({"customer_id": 380}, {"seq": 1, "count": 1}).sort("seq", 1):
        print(f"customer 380, bucket seq {b['seq']}: {b['count']} rentals")


# ---------- task 2: concurrency check ----------


def concurrency() -> None:
    """8 threads add 120 rentals to the same customer at the same time.

    With --no-unique the two unique indexes are not created, to show why they are needed.
    """
    test = db.rental_buckets_test
    test.drop()
    if "--no-unique" in sys.argv:
        print("(without the unique indexes)")
        test.create_index("customer_id")
    else:
        create_indexes(test)

    # 8 threads x 15 rentals. Before every rental, all 8 wait for each other, so that
    # they call add_rental at the same moment, also when a bucket has just filled up.
    start = threading.Barrier(8)

    def add(thread: int) -> None:
        for k in range(15):
            start.wait()
            i = thread * 15 + k + 1
            add_rental(999999, {"rental_id": i, "title": f"TEST {i}"}, buckets=test)

    with ThreadPoolExecutor(8) as pool:
        list(pool.map(add, range(8)))

    for b in test.find({}, {"seq": 1, "count": 1, "rentals": 1}).sort("seq", 1):
        print(f"bucket seq {b['seq']}: count {b['count']}, rentals in the array {len(b['rentals'])}")
    ids = [r["rental_id"] for b in test.find() for r in b["rentals"]]
    print(f"rentals stored: {len(ids)}, distinct: {len(set(ids))}, missing: {sorted(set(range(1, 121)) - set(ids))}")
    print(f"add_rental calls repeated after a DuplicateKeyError: {duplicate_key_retries}")
    test.drop()


# ---------- task 5: compare ----------


def timed(fn, runs: int = 2000) -> float:
    fn()  # warm up: document in the cache, connection open
    samples = []
    for _ in range(runs):
        t = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t) * 1000)
    return statistics.median(samples)


def recent_from_buckets(customer_id: int, n: int = 20) -> list:
    # the newest buckets first; each bucket's array is in rental_date order (oldest first)
    out = []
    for b in db.rental_buckets.find({"customer_id": customer_id}, {"rentals": 1}).sort("seq", -1).limit(2):
        out.extend(reversed(b["rentals"]))
        if len(out) >= n:
            break
    return out[:n]


def recent_from_history(customer_id: int, n: int = 20) -> list:
    doc = db.rental_history.find_one({"_id": customer_id}, {"rentals": {"$slice": -n}})
    return list(reversed(doc["rentals"]))


def recent_from_history_full(customer_id: int, n: int = 20) -> list:
    doc = db.rental_history.find_one({"_id": customer_id})
    return list(reversed(doc["rentals"]))[:n]


def compare(customer_id: int = 380) -> None:
    buckets = list(db.rental_buckets.find({"customer_id": customer_id}).sort("seq", 1))
    history = db.rental_history.find_one({"_id": customer_id})

    print(f"customer {customer_id}: {history['count']} rentals")
    for b in buckets:
        print(f"  rental_buckets seq {b['seq']}: {b['count']} rentals, {len(bson.encode(b)):,} bytes")
    print(f"  rental_buckets total: {sum(len(bson.encode(b)) for b in buckets):,} bytes")
    print(f"  rental_history: 1 document, {len(bson.encode(history)):,} bytes")

    a = recent_from_buckets(customer_id)
    b = recent_from_history(customer_id)
    assert [r["rental_id"] for r in a] == [r["rental_id"] for r in b], "the two reads differ"
    print(f"  the 20 most recent rentals are the same in both (newest: {a[0]['rental_id']})")

    print("median time to read the 20 most recent rentals (2,000 reads each):")
    print(f"  rental_buckets (last 1 or 2 buckets):       {timed(lambda: recent_from_buckets(customer_id)):.3f} ms")
    print(f"  rental_history with $slice: -20:            {timed(lambda: recent_from_history(customer_id)):.3f} ms")
    print(f"  rental_history, whole document:             {timed(lambda: recent_from_history_full(customer_id)):.3f} ms")

    # the largest documents of each collection
    biggest_history = next(db.rental_history.aggregate([
        {"$project": {"size": {"$bsonSize": "$$ROOT"}, "count": 1}}, {"$sort": {"size": -1}}, {"$limit": 1}]))
    biggest_bucket = next(db.rental_buckets.aggregate([
        {"$project": {"size": {"$bsonSize": "$$ROOT"}, "count": 1}}, {"$sort": {"size": -1}}, {"$limit": 1}]))
    print(f"largest rental_history document: {biggest_history['size']:,} bytes ({biggest_history['count']} rentals)")
    print(f"largest rental_buckets document: {biggest_bucket['size']:,} bytes ({biggest_bucket['count']} rentals)")


def large(n: int = 20_000) -> None:
    """The same comparison for a made-up customer 0 with 20,000 rentals.

    Customer 380 is too small to show the difference; this shows what happens when
    the history really grows. The made-up documents are removed at the end.
    """
    sample = db.rentals.find_one({"customer_id": 380})
    rentals = [bucket_rental(sample) | {"rental_id": 1_000_000 + i} for i in range(n)]

    db.rental_history.delete_one({"_id": 0})
    db.rental_buckets.delete_many({"customer_id": 0})
    db.rental_history.insert_one({"_id": 0, "count": n, "rentals": rentals})
    db.rental_buckets.insert_many([
        {"customer_id": 0, "seq": s + 1, "count": BUCKET_SIZE,
         "rentals": rentals[s * BUCKET_SIZE:(s + 1) * BUCKET_SIZE]}
        for s in range(n // BUCKET_SIZE)
    ])
    try:
        history = db.rental_history.find_one({"_id": 0})
        last_bucket = db.rental_buckets.find_one({"customer_id": 0}, sort=[("seq", -1)])
        print(f"made-up customer 0: {n:,} rentals")
        print(f"  rental_history: 1 document, {len(bson.encode(history)):,} bytes")
        print(f"  rental_buckets: {n // BUCKET_SIZE} documents, the newest {len(bson.encode(last_bucket)):,} bytes")
        print("median time to read the 20 most recent rentals (200 reads each):")
        print(f"  rental_buckets (last 1 or 2 buckets):       {timed(lambda: recent_from_buckets(0), 200):.3f} ms")
        print(f"  rental_history with $slice: -20:            {timed(lambda: recent_from_history(0), 200):.3f} ms")
        print(f"  rental_history, whole document:             {timed(lambda: recent_from_history_full(0), 200):.3f} ms")
        started = time.perf_counter()
        for i in range(200):
            db.rental_history.update_one({"_id": 0}, {"$push": {"rentals": rentals[i]}, "$inc": {"count": 1}})
        push_history = (time.perf_counter() - started) / 200 * 1000
        started = time.perf_counter()
        for i in range(200):
            db.rental_buckets.update_one({"customer_id": 0, "seq": n // BUCKET_SIZE},
                                         {"$push": {"rentals": rentals[i]}, "$inc": {"count": 1}})
        push_bucket = (time.perf_counter() - started) / 200 * 1000
        print("mean time of one $push of a new rental (200 pushes each):")
        print(f"  into the bucket:                            {push_bucket:.3f} ms")
        print(f"  into the rental_history document:           {push_history:.3f} ms")
    finally:
        db.rental_history.delete_one({"_id": 0})
        db.rental_buckets.delete_many({"customer_id": 0})


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "load"
    {"load": load, "concurrency": concurrency, "compare": compare, "large": large}[command]()
