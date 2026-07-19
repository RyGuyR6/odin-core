from app.intelligence.cross_reference import (
    CrossReferenceIndex,
    SymbolReference,
)


def test_add_definition():
    index = CrossReferenceIndex()

    symbol = SymbolReference(
        name="Repository",
        qualified_name="repository.Repository",
        module="repository.py",
        line=10,
    )

    index.add_definition(symbol)

    assert index.find_definition("Repository") == symbol


def test_add_reference():
    index = CrossReferenceIndex()

    symbol = SymbolReference(
        name="Repository",
        qualified_name="repository.Repository",
        module="repository.py",
        line=20,
    )

    index.add_reference(symbol)

    refs = index.find_references("Repository")

    assert len(refs) == 1
    assert refs[0] == symbol
