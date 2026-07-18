from app.repository.models import (
    ImportSymbol,
    RepositorySymbol,
)


def test_repository_symbol():

    symbol = RepositorySymbol(
        name="Repository",
        kind="class",
        module="repository",
        file="repository.py",
        line=10,
    )

    assert symbol.name == "Repository"
    assert symbol.kind == "class"
    assert symbol.module == "repository"
    assert symbol.file == "repository.py"
    assert symbol.line == 10
    assert symbol.decorators == []
    assert symbol.bases == []


def test_import_symbol():

    imp = ImportSymbol(
        module="pathlib",
        name="Path",
        alias=None,
        line=1,
    )

    assert imp.module == "pathlib"
    assert imp.name == "Path"
    assert imp.alias is None
    assert imp.line == 1
