from app.repository import Repository


def test_load_repository():

    repo = Repository(".")

    files = repo.load()

    assert len(files) > 0

    assert all(file.extension == ".py" for file in files)
