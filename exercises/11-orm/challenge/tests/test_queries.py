from films import list_films


def test_list_films_has_no_n_plus_one(session, assert_max_queries):
    with assert_max_queries(3):
        films = list_films(session, limit=100)

    assert len(films) == 100
    assert films[0]["title"] == "ACADEMY DINOSAUR"
    assert films[0]["actors"][0] == "PENELOPE GUINESS"
    assert all(film["actors"] for film in films)
    assert all(film["categories"] for film in films)


def test_assert_max_queries_counts_statements(session, assert_max_queries, statements):
    """The helper itself: one statement is allowed with n=1."""
    from sqlalchemy import text

    with assert_max_queries(1):
        session.execute(text("SELECT 1"))
    assert statements[-1] == "SELECT 1"
