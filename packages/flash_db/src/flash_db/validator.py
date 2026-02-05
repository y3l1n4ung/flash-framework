import logging
from typing import Type, TypeVar

from .models import Model

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="Model")


class ModelValidator:
    """Validates that a class is a proper Model."""

    @staticmethod
    def validate_model(model: Type[T]) -> Type[T]:
        """
        Validate that the provided class is a Model subclass.

        Raises:
            TypeError: If model is not a Model subclass or missing required attributes.
        """
        if not isinstance(model, type):
            msg = f"model must be a class, got {type(model).__name__}"
            raise TypeError(msg)

        if not issubclass(model, Model):
            msg = (
                f"model must be a Model subclass, got {model.__name__}. "
                f"Make sure '{model.__name__}' inherits from flash_db.Model"
            )
            raise TypeError(
                msg,
            )

        if not hasattr(model, "__tablename__"):
            msg = (
                f"Model {model.__name__} is missing __tablename__. "
                f"SQLAlchemy requires this attribute."
            )
            raise TypeError(
                msg,
            )

        if not hasattr(model, "id"):
            msg = (
                f"Model {model.__name__} has no 'id' field. "
                f"flash_db requires an 'id' field for model operations."
            )
            raise TypeError(msg)

        return model
