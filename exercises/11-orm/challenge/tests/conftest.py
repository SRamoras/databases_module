import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

# the modules under test (models.py, films.py) are in the folder above tests/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import make_engine  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    engine = make_engine(echo=False)
    # Open one connection before any test, so the queries the dialect runs on its
    # first connection (server version, current schema...) are never counted.
    with engine.connect():
        pass
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def statements(engine):
    """Every SQL statement the engine runs during the test, in order."""
    executed: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        executed.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    yield executed
    event.remove(engine, "before_cursor_execute", record)


@pytest.fixture
def assert_max_queries(statements):
    """Context manager: fails the test if more than n statements run inside the block.

        with assert_max_queries(3):
            list_films(session)
    """

    @contextmanager
    def check(n: int):
        start = len(statements)
        yield
        ran = statements[start:]
        if len(ran) > n:
            shown = "\n".join(f"  {i}. {s.split(chr(10))[0][:100]}" for i, s in enumerate(ran[:5], 1))
            pytest.fail(
                f"expected at most {n} SQL statements, but {len(ran)} ran. First ones:\n{shown}",
                pytrace=False,
            )

    return check
