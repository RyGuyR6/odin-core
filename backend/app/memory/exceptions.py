class MemoryError(Exception):
    """Base exception for the memory subsystem."""

class MemoryNotFoundError(MemoryError):
    pass

class MemoryValidationError(MemoryError):
    pass

class IngestionError(MemoryError):
    pass

class EmbeddingError(MemoryError):
    pass
