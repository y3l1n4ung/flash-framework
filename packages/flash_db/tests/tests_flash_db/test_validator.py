import pytest
from flash_db.models import Model
from flash_db.validator import ModelValidator


class ValidModel(Model):
    __tablename__ = "valid"


class NotAModel:
    pass


class TestModelValidator:
    def test_validate_model_with_valid_model(self):
        """Test that a valid model passes validation."""
        assert ModelValidator.validate_model(ValidModel) == ValidModel

    def test_validate_model_with_non_class(self):
        """Test that a non-class raises TypeError."""
        with pytest.raises(TypeError, match="model must be a class"):
            ModelValidator.validate_model(123)  # type: ignore[arg-type]

    def test_validate_model_with_non_model_subclass(self):
        """Test that a non-Model subclass raises TypeError."""
        with pytest.raises(TypeError, match="model must be a Model subclass"):
            ModelValidator.validate_model(NotAModel)  # type: ignore[arg-type]

    def test_validate_model_missing_tablename(self):
        """Test that a Model without __tablename__ raises TypeError."""

        class MissingTablename(Model):
            __abstract__ = True

        with pytest.raises(TypeError, match="is missing __tablename__"):
            ModelValidator.validate_model(MissingTablename)

    def test_validate_model_missing_id_raises_typeerror(self):
        """Test that a Model without 'id' raises TypeError."""
        # We use a mock class and patch issubclass to trigger the 'id' check
        # because any real subclass of flash_db.Model automatically inherits 'id'.
        from unittest.mock import MagicMock, patch

        mock_model = MagicMock(spec=type)
        mock_model.__name__ = "MockModel"
        mock_model.__tablename__ = "mock_table"
        # Ensure it doesn't have an 'id' attribute
        del mock_model.id

        with (
            patch("flash_db.validator.issubclass", return_value=True),
            pytest.raises(TypeError, match="has no 'id' field"),
        ):
            ModelValidator.validate_model(mock_model)  # type: ignore  # ty:ignore[unused-ignore-comment]
