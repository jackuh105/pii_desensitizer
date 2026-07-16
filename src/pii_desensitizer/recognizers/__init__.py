# src/pii_desensitizer/recognizers/__init__.py
"""Recognizer registry: builds and configures the Presidio AnalyzerEngine.

Architecture:
  1. Configure NLP engine with en_core_web_sm only (for English NER + nlp_artifacts)
  2. Add SpacyRecognizer via add_nlp_recognizer (handles English PERSON via NER)
  3. Register custom regex recognizers for all HK/Macau PII types
  4. Register ChinesePersonRecognizer (loads zh_core_web_sm independently)
  5. All recognizers registered for language "en" (mixed text handled in one pass)

Note: We use add_nlp_recognizer instead of load_predefined_recognizers because
our custom EmailRecognizer and CreditCardRecognizer class names collide with
Presidio's built-in ones. The built-in loader scans __subclasses__() and would
pick up our custom classes, causing a TypeError on instantiation. We only need
the SpacyRecognizer from the built-ins, so add_nlp_recognizer is sufficient.
"""

from __future__ import annotations

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider

from pii_desensitizer.recognizers.contact import (
    EmailRecognizer,
    HKMacauPhoneRecognizer,
    IPAddressRecognizer,
)
from pii_desensitizer.recognizers.identity import (
    HKIDRecognizer,
    HKLicensePlateRecognizer,
    HKPassportRecognizer,
    MacauIDRecognizer,
)
from pii_desensitizer.recognizers.financial import (
    BankAccountRecognizer,
    CreditCardRecognizer,
)
from pii_desensitizer.recognizers.temporal import BirthdayRecognizer
from pii_desensitizer.recognizers.address import AddressRecognizer
from pii_desensitizer.recognizers.person_ner import ChinesePersonRecognizer

# All entity types this system detects
ALL_ENTITIES = [
    "PERSON",
    "PHONE_NUMBER",
    "EMAIL",
    "HKID",
    "MACAU_ID",
    "ADDRESS",
    "CREDIT_CARD",
    "BANK_ACCOUNT",
    "PASSPORT",
    "BIRTHDAY",
    "IP_ADDRESS",
    "LICENSE_PLATE",
]


def build_analyzer() -> AnalyzerEngine:
    """Build and configure the Presidio AnalyzerEngine.

    Returns an AnalyzerEngine with:
      - English NLP engine (en_core_web_sm) for nlp_artifacts
      - SpacyRecognizer for English PERSON (via add_nlp_recognizer)
      - Custom regex recognizers for all HK/Macau PII types
      - ChinesePersonRecognizer for Chinese person name NER
    """
    # 1. Configure NLP engine with English model only
    nlp_config = {
        "nlp_engine_name": "spacy",
        "models": [
            {"lang_code": "en", "model_name": "en_core_web_sm"},
        ],
    }
    provider = NlpEngineProvider(nlp_configuration=nlp_config)
    nlp_engine = provider.create_engine()

    # 2. Create registry and add SpacyRecognizer for English NER
    registry = RecognizerRegistry()
    registry.add_nlp_recognizer(nlp_engine=nlp_engine)

    # 3. Register custom recognizers (all for language "en")
    custom_recognizers = [
        EmailRecognizer(),
        HKMacauPhoneRecognizer(),
        IPAddressRecognizer(),
        HKIDRecognizer(),
        MacauIDRecognizer(),
        AddressRecognizer(),
        CreditCardRecognizer(),
        BankAccountRecognizer(),
        HKPassportRecognizer(),
        BirthdayRecognizer(),
        HKLicensePlateRecognizer(),
        ChinesePersonRecognizer(),
    ]

    for recognizer in custom_recognizers:
        registry.add_recognizer(recognizer)

    # 4. Build analyzer
    analyzer = AnalyzerEngine(
        registry=registry,
        nlp_engine=nlp_engine,
        supported_languages=["en"],
    )

    return analyzer
