# src/pii_desensitizer/recognizers/person_ner.py
"""Custom Presidio EntityRecognizer for Chinese person name detection.

Uses spaCy's zh_core_web_sm model to detect PERSON entities in Chinese text.
Loaded independently of Presidio's NLP engine (which is configured for English).

Architecture:
  - Presidio's built-in SpacyRecognizer handles English PERSON (via en_core_web_sm)
  - This recognizer handles Chinese PERSON (via zh_core_web_sm)
  - Both are registered for language "en"; Presidio's conflict resolution
    handles any overlapping results.

Known limitation: zh_core_web_sm is trained on Simplified Chinese (OntoNotes 5).
Traditional Chinese (HK/Macau) will have lower recall. Accepted per design.
"""

from __future__ import annotations

from typing import List, Optional

import spacy
from presidio_analyzer import EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts


class ChinesePersonRecognizer(EntityRecognizer):
    """Detect Chinese person names using spaCy zh_core_web_sm NER."""

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["PERSON"],
            name="ChinesePersonRecognizer",
            # Registered for "en" so it runs alongside en nlp_artifacts;
            # built-in SpacyRecognizer handles English PERSON, this handles Chinese.
            supported_language="en",
        )
        self._nlp: Optional[spacy.language.Language] = None

    def load(self) -> None:
        self._nlp = spacy.load("zh_core_web_sm")

    def analyze(
        self,
        text: str,
        entities: List[str],
        nlp_artifacts: Optional[NlpArtifacts] = None,
    ) -> List[RecognizerResult]:
        # nlp_artifacts are English-specific; this recognizer runs zh model independently
        if not self._nlp or not text.strip():
            return []

        if "PERSON" not in entities:
            return []

        results: List[RecognizerResult] = []

        doc = self._nlp(text)
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                results.append(
                    RecognizerResult(
                        entity_type="PERSON",
                        start=ent.start_char,
                        end=ent.end_char,
                        # spaCy NER has no per-entity confidence; use constant
                        score=0.85,
                        recognition_metadata={
                            RecognizerResult.RECOGNIZER_NAME_KEY: self.name,
                            RecognizerResult.RECOGNIZER_IDENTIFIER_KEY: self.id,
                        },
                    )
                )

        return results
