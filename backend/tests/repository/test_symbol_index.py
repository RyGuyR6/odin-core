from app.repository import Repository


def test_symbol_index():

    repo = Repository(".")

    repo.load()

    repo.index()

    assert len(repo.index_db) > 0


def test_find_repository_symbol():

    repo = Repository(".")

    repo.load()

    repo.index()

    symbol = repo.find_symbol("Repository")

    assert symbol is not None
    assert symbol.kind == "class"
