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
