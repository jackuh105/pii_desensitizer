"""Person name recognizers for English and Chinese text.

EnglishPersonRecognizer:
  Subclasses Presidio's SpacyRecognizer to filter out PERSON spans containing
  CJK characters. en_core_web_sm is an English model that produces garbage NER
  results on Chinese text (e.g. tagging 47-char paragraphs as PERSON). Since
  ChinesePersonRecognizer handles all Chinese name detection, any PERSON span
  from the English model containing CJK is a false positive.

ChinesePersonRecognizer:
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

  Context-based fallback:
    zh_core_web_sm has inconsistent recall — some names are never
    detected even in isolation. A regex fallback matches form-field keywords
    (姓名, 子女, 申請人, etc.) followed by 2-4 CJK characters to catch names
    the NER model misses.

Architecture:
  - EnglishPersonRecognizer handles English PERSON (en_core_web_sm, CJK filtered)
  - ChinesePersonRecognizer handles Chinese PERSON (zh_core_web_sm + OpenCC + context fallback)
  - Both are registered for language "en"; Presidio's conflict resolution
    handles any overlapping results.
"""

from __future__ import annotations

import re
from typing import List, Optional

import spacy
from opencc import OpenCC
from presidio_analyzer import EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts
from presidio_analyzer.predefined_recognizers import SpacyRecognizer


class EnglishPersonRecognizer(SpacyRecognizer):
    """Wraps SpacyRecognizer to filter CJK from PERSON results.

    en_core_web_sm is an English model. When fed Chinese text, it produces
    massive false-positive PERSON spans (e.g. 47 chars across 3 lines).
    ChinesePersonRecognizer handles all Chinese name detection, so any
    PERSON span from the English model containing CJK characters is garbage.
    """

    _CJK_RE = re.compile(r"[\u3000-\u303f\u4e00-\u9fff]")

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["PERSON"],
            name="EnglishPersonRecognizer",
            supported_language="en",
        )

    @staticmethod
    def _is_stopword(span_text: str) -> bool:
        """Check if a PERSON span is a common English word, not a name.

        Only filters single-word spans (no spaces) that are pure ASCII.
        Multi-word spans (e.g. "John Smith") and spans with diacritics
        (e.g. "João") are never filtered.
        """
        if " " in span_text:
            return False
        if not span_text.isascii() or not span_text.isalpha():
            return False
        return span_text.lower() in _PERSON_STOPWORDS

    def analyze(
        self,
        text: str,
        entities: List[str],
        nlp_artifacts: Optional[NlpArtifacts] = None,
    ) -> List[RecognizerResult]:
        results = super().analyze(text, entities, nlp_artifacts)
        return [
            r
            for r in results
            if not (
                r.entity_type == "PERSON"
                and (
                    self._CJK_RE.search(text[r.start : r.end])
                    or self._is_stopword(text[r.start : r.end])
                    or _DIGITS_ONLY_RE.match(text[r.start : r.end])
                    or _PT_ADDRESS_PREFIX_RE.match(text[r.start : r.end])
                )
            )
        ]


# Form-field keywords that precede person names in HK/Macau government forms
_NAME_FIELD_KEYWORDS = (
    r"姓名|本人姓名|申請人|簽署|提交人|聯絡人|負責人|代表人|"
    r"家長|監護人|子女|本人|投訴人|反映人|發件人|收件人"
)

_CJK_NAME = r"[\u4e00-\u9fff]{2,4}"

# Common English words that spaCy mislabels as PERSON when processing
# mixed-language or short text. These are never person names.
# Only single-word spans (no spaces) are checked against this set.
_PERSON_STOPWORDS = frozenset({
    # Prepositions / conjunctions
    "for", "out", "but", "and", "nor", "yet", "so", "or",
    "in", "on", "at", "to", "of", "by", "with", "from",
    "into", "onto", "upon", "over", "under", "after", "before",
    "about", "above", "below", "between", "through", "during",
    # Common verbs
    "born", "been", "have", "has", "had", "was", "were",
    "will", "would", "could", "should", "shall", "may", "might",
    "can", "did", "does", "done", "made", "make", "makes",
    "get", "got", "put", "set", "let", "run", "ran",
    # Common nouns / adjectives
    "email", "phone", "tel", "fax", "date", "time", "year",
    "month", "day", "version", "address", "name", "number",
    "code", "id", "no", "yes", "true", "false", "null",
    "user", "test", "demo", "sample", "example", "data",
    "file", "form", "page", "link", "url", "http", "https",
    # Pronouns
    "this", "that", "these", "those", "there", "here",
    "which", "what", "who", "whom", "whose", "where", "when",
    "why", "how", "all", "any", "some", "none", "both",
    "each", "every", "other", "another", "such", "same",
})

# Pure digit/separator pattern: matches strings that are entirely digits
# with optional separators (spaces, hyphens, parentheses).
# Digit strings are never person names.
_DIGITS_ONLY_RE = re.compile(r"^[\d\s\-\(\)]+$")

# Portuguese building/street suffixes that indicate an address, not a name.
# If a PERSON span starts with one of these, it's an address false positive.
_PT_ADDRESS_PREFIX_RE = re.compile(
    r"^(?:Edif[ií]cio|Centro Comercial|Centro|Jardins?|Bloco|Torre|"
    r"Urbaniza[çc][ãa]o|Condom[ií]nio|Vivenda|Quinta|"
    r"Rua|Avenida|Av\.?|Travessa|Tv\.?|Estrada|Caminho|"
    r"Cal[çc]ada|Largo|Pra[çc]a|Praceta|Beco|P[áa]tio|"
    r"Alameda|Rotunda|Bairro|Parque|Jardim|Adro|"
    r"Azinhaga|Escadaria|Miradouro|Rampa|Istmo|Ponte|T[úu]nel|Viaduto)\b",
    re.IGNORECASE,
)

_ALL_CAPS_NAME = r"[A-ZÀ-Ý]{2,}(?:\s+[A-ZÀ-Ý]{2,}){1,5}"

_TITLE_CASE_NAME = (
    r"[A-Z][a-zà-ÿ]+"
    r"(?:\s+(?:de|da|do|das|dos)\s+[A-Z][a-zà-ÿ]+"
    r"|\s+[A-Z][a-zà-ÿ]+){1,5}"
)

_CONTEXT_NAME_RE = re.compile(
    rf"(?:{_NAME_FIELD_KEYWORDS})"
    rf"(?:簽署)?"
    rf"\s*[：:]\s*"
    rf"({_ALL_CAPS_NAME}|{_TITLE_CASE_NAME}|{_CJK_NAME})"
)


class ChinesePersonRecognizer(EntityRecognizer):
    """Detect Chinese person names using spaCy zh_core_web_sm NER + context fallback.

    Primary: zh_core_web_sm NER (converted Traditional→Simplified via OpenCC).
    Fallback: regex matching form-field keywords followed by 2-4 CJK characters,
    for names the NER model misses.
    """

    _PUNCTUATION_CHARS = set("()（）.,，。、；;：:！!？?「」『』\"'`'\"")

    # Reuse the stopword filter from EnglishPersonRecognizer
    _is_stopword = staticmethod(EnglishPersonRecognizer._is_stopword)

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["PERSON"],
            name="ChinesePersonRecognizer",
            supported_language="en",
        )
        self._nlp: Optional[spacy.language.Language] = None
        self._cc: Optional[OpenCC] = None

    def load(self) -> None:
        self._nlp = spacy.load("zh_core_web_sm")
        self._cc = OpenCC("t2s")

    def analyze(
        self,
        text: str,
        entities: List[str],
        nlp_artifacts: Optional[NlpArtifacts] = None,
    ) -> List[RecognizerResult]:
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

        # Filter English common words that zh_core_web_sm mislabels as PERSON
        # when processing English text (e.g. "for", "out", "Born")
        results = [
            r for r in results
            if not self._is_stopword(text[r.start:r.end])
        ]

        for m in _CONTEXT_NAME_RE.finditer(text):
            start, end = m.start(1), m.end(1)
            # Skip if this span overlaps with an existing NER result
            if any(r.start < end and start < r.end for r in results):
                continue
            results.append(
                RecognizerResult(
                    entity_type="PERSON",
                    start=start,
                    end=end,
                    score=0.75,
                    recognition_metadata={
                        RecognizerResult.RECOGNIZER_NAME_KEY: self.name,
                        RecognizerResult.RECOGNIZER_IDENTIFIER_KEY: self.id,
                    },
                )
            )

        return results
