"""Custom Presidio EntityRecognizer for Chinese person name detection.

Uses spaCy's zh_core_web_sm model to detect PERSON entities in Chinese text.
Loaded independently of Presidio's NLP engine (which is configured for English).

Traditional Chinese support:
  zh_core_web_sm is trained on Simplified Chinese (OntoNotes 5). To detect
  Traditional Chinese names (HK/Macau), we convert the input text from
  Traditional to Simplified using OpenCC before running NER.

  OpenCC is a 1:1 character mapping — the converted string always has the
  same length as the original. This means NER offsets from the Simplified
  text are directly valid on the original Traditional text. Presidio's
  AnonymizerEngine slices the original text (not the conversion), so the
  mapping table stores the original Traditional value, and restore returns
  Traditional text.

Architecture:
  - Presidio's built-in SpacyRecognizer handles English PERSON (via en_core_web_sm)
  - This recognizer handles Chinese PERSON (via zh_core_web_sm + OpenCC)
  - Both are registered for language "en"; Presidio's conflict resolution
    handles any overlapping results.
"""

from __future__ import annotations

from typing import List, Optional

import spacy
from opencc import OpenCC
from presidio_analyzer import EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts


class ChinesePersonRecognizer(EntityRecognizer):
    """Detect Chinese person names using spaCy zh_core_web_sm NER.

    Converts Traditional→Simplified before NER for better recall on
    HK/Macau text. Offsets remain valid on the original text because
    OpenCC preserves string length (1:1 character mapping).
    """

    _PUNCTUATION_CHARS = set("()（）.,，。、；;：:！!？?「」『』\"'`'\"")

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["PERSON"],
            name="ChinesePersonRecognizer",
            supported_language="en",
        )
        self._nlp: Optional[spacy.language.Language] = None
        self._cc: Optional[OpenCC] = None

    def load(self) -> None:
        """Load the spaCy Chinese model and OpenCC converter."""
        self._nlp = spacy.load("zh_core_web_sm")
        self._cc = OpenCC("t2s")

    def analyze(
        self,
        text: str,
        entities: List[str],
        nlp_artifacts: Optional[NlpArtifacts] = None,
    ) -> List[RecognizerResult]:
        """Analyze text for Chinese person names.

        Converts Traditional→Simplified before NER. Returns offsets that
        are valid on the original (Traditional) text. Filters out false
        positives where spaCy tags punctuation-adjacent text as PERSON.
        """
        if not self._nlp or not self._cc or not text.strip():
            return []

        if "PERSON" not in entities:
            return []

        simplified_text = self._cc.convert(text)

        doc = self._nlp(simplified_text)

        results: List[RecognizerResult] = []
        for ent in doc.ents:
            if ent.label_ != "PERSON":
                continue

            if self._PUNCTUATION_CHARS & set(ent.text):
                continue

            results.append(
                RecognizerResult(
                    entity_type="PERSON",
                    start=ent.start_char,
                    end=ent.end_char,
                    score=0.85,
                    recognition_metadata={
                        RecognizerResult.RECOGNIZER_NAME_KEY: self.name,
                        RecognizerResult.RECOGNIZER_IDENTIFIER_KEY: self.id,
                    },
                )
            )

        return results
