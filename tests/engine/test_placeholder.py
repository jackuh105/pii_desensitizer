# tests/engine/test_placeholder.py
"""Tests for the custom placeholder operator."""

import pytest

from pii_desensitizer.engine.placeholder import PlaceholderOperator


class TestPlaceholderOperator:
    """Tests for the {{TYPE_N}} placeholder operator."""

    def test_operator_name(self):
        op = PlaceholderOperator()
        assert op.operator_name() == "placeholder"

    def test_operator_type_is_anonymize(self):
        from presidio_anonymizer.operators import OperatorType
        op = PlaceholderOperator()
        assert op.operator_type() == OperatorType.Anonymize

    def test_replaces_single_value(self):
        op = PlaceholderOperator()
        result = op.operate(
            text="陳大文",
            params={"entity_type": "PERSON", "entity_mapping": {}},
        )
        assert result == "{{PERSON_0}}"

    def test_same_value_same_placeholder(self):
        """The same value always gets the same placeholder."""
        mapping: dict[str, dict[str, str]] = {}
        params = {"entity_type": "PERSON", "entity_mapping": mapping}

        op = PlaceholderOperator()
        first = op.operate(text="陳大文", params=params)
        second = op.operate(text="陳大文", params=params)

        assert first == "{{PERSON_0}}"
        assert second == "{{PERSON_0}}"

    def test_different_values_different_index(self):
        mapping: dict[str, dict[str, str]] = {}
        params = {"entity_type": "PERSON", "entity_mapping": mapping}

        op = PlaceholderOperator()
        first = op.operate(text="陳大文", params=params)
        second = op.operate(text="李小明", params=params)

        assert first == "{{PERSON_0}}"
        assert second == "{{PERSON_1}}"

    def test_different_entity_types_independent_indexing(self):
        mapping: dict[str, dict[str, str]] = {}
        op = PlaceholderOperator()

        name_result = op.operate(
            text="陳大文",
            params={"entity_type": "PERSON", "entity_mapping": mapping},
        )
        phone_result = op.operate(
            text="98765432",
            params={"entity_type": "PHONE_NUMBER", "entity_mapping": mapping},
        )

        assert name_result == "{{PERSON_0}}"
        assert phone_result == "{{PHONE_NUMBER_0}}"

    def test_pre_existing_mapping_is_reused(self):
        """When mapping already has entries, new values continue the index."""
        mapping: dict[str, dict[str, str]] = {
            "PERSON": {"陳大文": "{{PERSON_0}}"}
        }
        op = PlaceholderOperator()
        result = op.operate(
            text="李小明",
            params={"entity_type": "PERSON", "entity_mapping": mapping},
        )
        assert result == "{{PERSON_1}}"

    def test_pre_existing_value_gets_existing_placeholder(self):
        """A value already in the mapping returns its existing placeholder."""
        mapping: dict[str, dict[str, str]] = {
            "PERSON": {"陳大文": "{{PERSON_0}}"}
        }
        op = PlaceholderOperator()
        result = op.operate(
            text="陳大文",
            params={"entity_type": "PERSON", "entity_mapping": mapping},
        )
        assert result == "{{PERSON_0}}"

    def test_validate_requires_entity_mapping(self):
        op = PlaceholderOperator()
        with pytest.raises(ValueError, match="entity_mapping"):
            op.validate(params={"entity_type": "PERSON"})

    def test_validate_requires_entity_type(self):
        op = PlaceholderOperator()
        with pytest.raises(ValueError, match="entity_type"):
            op.validate(params={"entity_mapping": {}})
