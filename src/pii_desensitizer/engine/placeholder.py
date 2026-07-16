# src/pii_desensitizer/engine/placeholder.py
"""Custom Presidio Operator that replaces PII values with {{TYPE_N}} placeholders.

The same original value always maps to the same placeholder within a single
entity_mapping dict, enabling:
  1. Consistent replacement across a document (LLM sees {{PERSON_0}} for every
     occurrence of the same name).
  2. Reversible restoration: the entity_mapping dict is the lookup table.

Format: {{ENTITY_TYPE_INDEX}}  e.g. {{PERSON_0}}, {{PHONE_NUMBER_1}}
"""

from __future__ import annotations

from typing import Dict

from presidio_anonymizer.operators import Operator, OperatorType


class PlaceholderOperator(Operator):
    """Replace PII values with {{TYPE_N}} placeholders.

    Uses a shared ``entity_mapping`` dict (passed via params) to maintain
    value -> placeholder consistency across multiple operate() calls within
    the same anonymization pass.

    The entity_mapping structure:
        {
            "PERSON": {"陳大文": "{{PERSON_0}}", "李小明": "{{PERSON_1}}"},
            "PHONE_NUMBER": {"98765432": "{{PHONE_NUMBER_0}}"},
        }
    """

    def operate(self, text: str, params: Dict | None = None) -> str:
        """Replace ``text`` with its {{TYPE_N}} placeholder.

        If the value was seen before (exists in mapping), return the existing
        placeholder. Otherwise, assign the next index for this entity type.
        """
        if params is None:
            params = {}

        entity_type: str = params["entity_type"]
        entity_mapping: Dict[str, Dict[str, str]] = params["entity_mapping"]

        per_type = entity_mapping.setdefault(entity_type, {})

        if text in per_type:
            return per_type[text]

        index = len(per_type)
        placeholder = "{{" + f"{entity_type}_{index}" + "}}"

        per_type[text] = placeholder
        return placeholder

    def validate(self, params: Dict | None = None) -> None:
        """Validate that required params are present."""
        if params is None:
            params = {}
        if "entity_mapping" not in params:
            raise ValueError(
                "An input Dict called `entity_mapping` is required."
            )
        if "entity_type" not in params:
            raise ValueError("An `entity_type` param is required.")

    def operator_name(self) -> str:
        """Return the operator name used in OperatorConfig."""
        return "placeholder"

    def operator_type(self) -> OperatorType:
        """Return the operator type (Anonymize)."""
        return OperatorType.Anonymize
