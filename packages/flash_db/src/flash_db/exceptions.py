class FlashDBError(Exception):
    """Base class for all Flash DB exceptions."""


class DoesNotExistError(FlashDBError, ValueError):
    """Raised when a single object was expected but none was found."""


class MultipleObjectsReturnedError(FlashDBError, ValueError):
    """Raised when a single object was expected but multiple were found."""
