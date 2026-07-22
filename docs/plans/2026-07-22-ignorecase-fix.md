# IGNORECASE False Positive Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate false positives caused by Presidio's default `re.IGNORECASE` flag on license plate and address recognizers, while preserving detection of uppercase and all-caps address variants.

**Architecture:** Replace the blanket `re.IGNORECASE` flag with explicit case alternation in regex patterns. For license plates, simply override `global_regex_flags` to remove `IGNORECASE` (plates are always uppercase). For addresses, rewrite English and Portuguese patterns so each suffix and word explicitly accepts Title Case OR ALL-CAPS (e.g. `Rd|RD`, `Rua|RUA`), and the following word accepts any letter case. HKID and Passport recognizers are NOT modified — lowercase IDs are real PII and must still be detected.

**Tech Stack:** Python 3.12, Presidio PatternRecognizer, pytest

---

## Background

### The Problem

Presidio's `PatternRecognizer.__init__` sets `global_regex_flags = re.DOTALL | re.MULTILINE | re.IGNORECASE` by default. The `re.IGNORECASE` flag makes `[A-Z]` match lowercase letters, causing false positives:

| Pattern | Text | False Match | Reason |
|---------|------|-------------|--------|
| `[A-Z]{2}\s?\d{4}` (plate) | `Born on 1990-01-15` | `on 1990` | `on` matches `[A-Z]{2}` |
| `[A-Z]{2}\s?\d{4}` (plate) | `He went to 2345` | `to 2345` | `to` matches `[A-Z]{2}` |
| `Rd\|St\|Ave` (EN addr) | `The rd is bumpy` | `The rd` | `rd` matches `Rd` |

### Why Not Just Remove IGNORECASE Everywhere?

HKID and Passport patterns use `[A-Z]` for letter prefixes. With IGNORECASE, they detect lowercase variants like `a123456(7)` and `h12345678` — these are real PII that users might type in informal text. Removing IGNORECASE would cause **missing detections** (false negatives). For a PII system, false negatives are worse than false positives.

### The Solution: Explicit Case Alternation

Instead of relying on IGNORECASE, explicitly enumerate allowed case variants in each pattern:

- **License plate**: Remove IGNORECASE. Plates are always uppercase on physical plates — no case variants needed.
- **English address**: Suffix becomes `Rd|RD|St|ST|Ave|AVE|...`. Street name word becomes `(?:[A-Z][a-z]+|[A-Z]{2,})` (Title Case OR all-caps).
- **Portuguese address**: Suffix becomes `Rua|RUA|Avenida|AVENIDA|...`. Following word becomes `[A-ZÀ-Ýa-zà-ÿ]+` (any case).
- **HKID / Passport**: No changes. Keep IGNORECASE for lowercase PII detection.

### Verification (pre-tested)

| Test Case | Result |
|-----------|--------|
| 16 existing should-match cases | All still match ✅ |
| 5 all-caps variants (`RUA DE EXEMPLO`, `123 MAIN ST`, etc.) | All match ✅ |
| 10 lowercase false positives (`on 1990`, `The rd`, etc.) | All eliminated ✅ |

---

## Task 1: Fix License Plate Recognizer — Remove IGNORECASE

**Files:**
- Modify: `src/pii_desensitizer/recognizers/identity.py:104-121`
- Test: `tests/recognizers/test_identity.py` (add tests to `TestHKLicensePlateRecognizer`)

**Step 1: Write the failing test**

Add to `tests/recognizers/test_identity.py`, inside `TestHKLicensePlateRecognizer` (after `test_detects_macau_license_plate`):

```python
def test_no_false_positive_on_lowercase_word_with_digits(self):
    """Lowercase 2-letter words followed by 4 digits should NOT match as plates.

    Presidio's default re.IGNORECASE makes [A-Z]{2} match lowercase,
    causing 'on 1990', 'to 2345', 'at 1990' to match as license plates.
    License plates are always uppercase — lowercase must not match.
    """
    rec = HKLicensePlateRecognizer()
    false_positive_texts = [
        "Born on 1990-01-15",
        "He went to 2345 block",
        "Born at 1990",
        "Died on 2023",
        "Please go to 5678 room",
    ]
    for text in false_positive_texts:
        results = rec.analyze(
            text=text, entities=["LICENSE_PLATE"], nlp_artifacts=None
        )
        assert len(results) == 0, (
            f"Expected no plate match for {text!r}, but got "
            f"{[text[r.start:r.end] for r in results]}"
        )
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/recognizers/test_identity.py::TestHKLicensePlateRecognizer::test_no_false_positive_on_lowercase_word_with_digits -v
```

Expected: FAIL — lowercase words like `on`, `to`, `at` match `[A-Z]{2}` under IGNORECASE.

**Step 3: Override `global_regex_flags` in HKLicensePlateRecognizer**

In `src/pii_desensitizer/recognizers/identity.py`, add `import re` at the top (if not already present) and add `global_regex_flags` to the `HKLicensePlateRecognizer.__init__` call:

```python
"""Regex-based recognizers for identity PII: HKID, Macau ID, Passport, License plate."""

from __future__ import annotations

import re

from presidio_analyzer import Pattern, PatternRecognizer
```

Then in `HKLicensePlateRecognizer.__init__`, add `global_regex_flags`:

```python
    def __init__(self) -> None:
        super().__init__(
            supported_entity="LICENSE_PLATE",
            patterns=[
                Pattern(
                    name="hk_plate_pattern",
                    regex=r"(?<![A-Za-z0-9])[A-Z]{2}\s?\d{4}(?![A-Za-z0-9])",
                    score=0.7,
                ),
                Pattern(
                    name="macau_plate_pattern",
                    regex=r"(?<![A-Za-z0-9])[A-Z]{2}-\d{2}-\d{2}(?![A-Za-z0-9])",
                    score=0.85,
                ),
            ],
            name="HKLicensePlateRecognizer",
            context=["plate", "車牌", "vehicle", "car", "license"],
            global_regex_flags=re.MULTILINE | re.DOTALL,
        )
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/recognizers/test_identity.py::TestHKLicensePlateRecognizer -v
```

Expected: all tests PASS, including the new false positive test and existing detection tests.

**Step 5: Run full test suite**

```bash
uv run pytest tests/ -x -q
```

Expected: all tests pass (150 existing + 1 new = 151).

**Step 6: Commit**

```bash
git add src/pii_desensitizer/recognizers/identity.py tests/recognizers/test_identity.py
git commit -m "fix: remove IGNORECASE from license plate recognizer to eliminate lowercase false positives"
```

---

## Task 2: Fix Address Recognizer — English Patterns

**Files:**
- Modify: `src/pii_desensitizer/recognizers/address.py:34-37` (English patterns) and `:83-100` (add `global_regex_flags`)
- Test: `tests/recognizers/test_address.py` (add tests to `TestAddressRecognizer`)

**Step 1: Write the failing tests**

Add to `tests/recognizers/test_address.py`, inside `TestAddressRecognizer` (after the last test):

```python
def test_no_false_positive_on_lowercase_road_abbreviation(self):
    """Lowercase 'rd', 'st', 'ave' in common text should NOT match as addresses.

    Presidio's default re.IGNORECASE makes Rd|St|Ave match lowercase,
    causing 'The rd is bumpy' to match as an address.
    """
    rec = AddressRecognizer()
    false_positive_texts = [
        "The rd is bumpy",
        "This st is narrow",
        "Walk down the ave",
    ]
    for text in false_positive_texts:
        results = rec.analyze(
            text=text, entities=["ADDRESS"], nlp_artifacts=None
        )
        assert len(results) == 0, (
            f"Expected no address match for {text!r}, but got "
            f"{[text[r.start:r.end] for r in results]}"
        )

def test_detects_all_caps_english_address(self):
    """All-caps English addresses (e.g. envelope labels) should be detected.

    '123 MAIN ST' and '1 Des Voeux RD' use all-caps suffixes and possibly
    all-caps street names. These are real addresses and must be detected.
    """
    rec = AddressRecognizer()
    test_cases = [
        "1 Des Voeux RD, Central",
        "123 MAIN ST",
    ]
    for text in test_cases:
        results = rec.analyze(
            text=text, entities=["ADDRESS"], nlp_artifacts=None
        )
        assert len(results) >= 1, (
            f"Expected address match for {text!r}, but got none"
        )
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/recognizers/test_address.py::TestAddressRecognizer::test_no_false_positive_on_lowercase_road_abbreviation tests/recognizers/test_address.py::TestAddressRecognizer::test_detects_all_caps_english_address -v
```

Expected:
- `test_no_false_positive_on_lowercase_road_abbreviation`: FAIL — lowercase `rd`, `st`, `ave` match under IGNORECASE.
- `test_detects_all_caps_english_address`: FAIL — all-caps `MAIN` doesn't match `[A-Z][a-z]+` without the new pattern, and `RD`/`ST` don't match `Rd|St` without explicit alternation.

**Step 3: Rewrite English address patterns and remove IGNORECASE**

In `src/pii_desensitizer/recognizers/address.py`, replace the `_EN_ADDRESS_PATTERNS` list (lines 34-37) and add `import re` and `global_regex_flags`:

Add `import re` at the top (after `from __future__ import annotations`):

```python
from __future__ import annotations

import re

from presidio_analyzer import Pattern, PatternRecognizer
```

Replace `_EN_ADDRESS_PATTERNS`:

```python
# English address word: Title Case (e.g. "Des", "Voeux") OR all-caps (e.g. "MAIN")
_EN_WORD = r"(?:[A-ZÀ-Ý][a-zà-ÿ]+|[A-ZÀ-Ý]{2,})"

# English address suffix: Title Case OR all-caps (e.g. "Rd" or "RD", not "rd")
_EN_SUFFIXES = (
    r"Rd|RD|St|ST|Ave|AVE|Drive|DRIVE|Dr|DR|Bldg|BLDG|"
    r"Tower|TOWER|Centre|CENTRE|Plaza|PLAZA|Garden|GARDEN|"
    r"Ct|CT|Cres|CRES|Terr|TERR|Ln|LN"
)

_EN_ADDRESS_PATTERNS = [
    rf"(?<![A-Za-z0-9])\d+\s+{_EN_WORD}(?:\s+{_EN_WORD})*\s+(?:{_EN_SUFFIXES})(?![A-Za-z0-9])",
    rf"(?<![A-Za-z0-9]){_EN_WORD}(?:\s+{_EN_WORD})*\s+(?:{_EN_SUFFIXES})(?![A-Za-z0-9])",
]
```

Then in `AddressRecognizer.__init__`, add `global_regex_flags`:

```python
    def __init__(self) -> None:
        patterns = [
            Pattern(name=f"zh_addr_{i}", regex=p, score=0.6)
            for i, p in enumerate(_ZH_ADDRESS_PATTERNS)
        ] + [
            Pattern(name=f"en_addr_{i}", regex=p, score=0.6)
            for i, p in enumerate(_EN_ADDRESS_PATTERNS)
        ] + [
            Pattern(name=f"pt_addr_{i}", regex=p, score=0.6)
            for i, p in enumerate(_PT_ADDRESS_PATTERNS)
        ]

        super().__init__(
            supported_entity="ADDRESS",
            patterns=patterns,
            name="AddressRecognizer",
            context=_HK_MACAU_DISTRICTS,
            global_regex_flags=re.MULTILINE | re.DOTALL,
        )
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/recognizers/test_address.py::TestAddressRecognizer -v
```

Expected: all tests pass, including the two new tests and all existing address detection tests.

**Step 5: Run full test suite**

```bash
uv run pytest tests/ -x -q
```

Expected: all tests pass (151 + 2 new = 153).

**Step 6: Commit**

```bash
git add src/pii_desensitizer/recognizers/address.py tests/recognizers/test_address.py
git commit -m "fix: use explicit case alternation in English address patterns instead of IGNORECASE"
```

---

## Task 3: Fix Address Recognizer — Portuguese Patterns

**Files:**
- Modify: `src/pii_desensitizer/recognizers/address.py:39-58` (Portuguese patterns)
- Test: `tests/recognizers/test_address.py` (add tests to `TestAddressRecognizer`)

**Step 1: Write the failing tests**

Add to `tests/recognizers/test_address.py`, inside `TestAddressRecognizer` (after the tests from Task 2):

```python
def test_detects_all_caps_portuguese_street(self):
    """All-caps Portuguese street names (e.g. official documents) should be detected.

    'RUA DE EXEMPLO' and 'AVENIDA DE TESTE GRANDE' use all-caps suffixes.
    These are real addresses and must be detected.
    """
    rec = AddressRecognizer()
    test_cases = [
        "RUA DE EXEMPLO",
        "AVENIDA DE TESTE GRANDE",
    ]
    for text in test_cases:
        results = rec.analyze(
            text=text, entities=["ADDRESS"], nlp_artifacts=None
        )
        assert len(results) >= 1, (
            f"Expected address match for {text!r}, but got none"
        )

def test_detects_all_caps_portuguese_building(self):
    """All-caps Portuguese building names should be detected."""
    rec = AddressRecognizer()
    text = "EDIFÍCIO COMERCIAL TESTE"
    results = rec.analyze(
        text=text, entities=["ADDRESS"], nlp_artifacts=None
    )
    assert len(results) >= 1, (
        f"Expected address match for {text!r}, but got none"
    )

def test_no_false_positive_on_lowercase_portuguese_word(self):
    """Lowercase Portuguese common nouns should NOT match as addresses.

    'rua' (street) as a common noun in prose should not trigger address
    detection — only the proper noun form (Rua/RUA) should.
    """
    rec = AddressRecognizer()
    text = "A rua é longa"
    results = rec.analyze(
        text=text, entities=["ADDRESS"], nlp_artifacts=None
    )
    assert len(results) == 0, (
        f"Expected no address match for {text!r}, but got "
        f"{[text[r.start:r.end] for r in results]}"
    )
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/recognizers/test_address.py::TestAddressRecognizer::test_detects_all_caps_portuguese_street tests/recognizers/test_address.py::TestAddressRecognizer::test_detects_all_caps_portuguese_building tests/recognizers/test_address.py::TestAddressRecognizer::test_no_false_positive_on_lowercase_portuguese_word -v
```

Expected:
- `test_detects_all_caps_portuguese_street`: FAIL — `RUA` doesn't match `Rua` without explicit alternation.
- `test_detects_all_caps_portuguese_building`: FAIL — `EDIFÍCIO` doesn't match `Edifício`.
- `test_no_false_positive_on_lowercase_portuguese_word`: may PASS or FAIL depending on whether IGNORECASE was already removed in Task 2 (it was, so `rua` won't match `Rua`). If it already passes, that's fine — it's a regression guard.

**Step 3: Rewrite Portuguese address patterns**

In `src/pii_desensitizer/recognizers/address.py`, replace `_PT_STREET_SUFFIXES`, `_PT_BUILDING_SUFFIXES`, and `_PT_ADDRESS_PATTERNS`:

```python
# Portuguese street suffixes: Title Case OR all-caps (not lowercase)
_PT_STREET_SUFFIXES_TITLE = (
    r"Rua|Avenida|Av|Travessa|Tv|Estrada|Caminho|Calçada|Largo|Praça|"
    r"Praceta|Beco|Pátio|Alameda|Rotunda|Bairro|Parque|Jardim|Adro|"
    r"Azinhaga|Escadaria|Miradouro|Rampa|Istmo|Ponte|Túnel|Viaduto"
)
_PT_STREET_SUFFIXES_UPPER = _PT_STREET_SUFFIXES_TITLE.upper()

# Portuguese building suffixes: Title Case OR all-caps (not lowercase)
_PT_BUILDING_SUFFIXES_TITLE = (
    r"Edifício|Centro Comercial|Centro|Jardins|Bloco|Torre|"
    r"Urbanização|Condomínio|Vivenda|Quinta"
)
_PT_BUILDING_SUFFIXES_UPPER = _PT_BUILDING_SUFFIXES_TITLE.upper()

# Portuguese prepositions: lowercase or all-caps (they follow the suffix)
_PT_PREPOSITIONS = r"(?:de|da|do|das|dos|DE|DA|DO|DAS|DOS)"

_PT_ADDRESS_PATTERNS = [
    rf"(?<![A-Za-z0-9])(?:{_PT_STREET_SUFFIXES_TITLE}|{_PT_STREET_SUFFIXES_UPPER})\.?\s+"
    rf"(?:{_PT_PREPOSITIONS}\s+)?"
    rf"[A-ZÀ-Ýa-zà-ÿ]+"
    rf"(?:\s+[A-ZÀ-Ýa-zà-ÿ]+)*",
    rf"(?<![A-Za-z0-9])(?:{_PT_BUILDING_SUFFIXES_TITLE}|{_PT_BUILDING_SUFFIXES_UPPER})\s+"
    rf"[A-ZÀ-Ýa-zà-ÿ]+"
    rf"(?:\s+[A-ZÀ-Ýa-zà-ÿ]+)*",
]
```

Note: `_PT_STREET_SUFFIXES.upper()` converts the Python string to uppercase at module load time, producing `RUA|AVENIDA|AV|TRAVESSA|...`. This works because `.upper()` correctly handles accented characters (`çada` → `ÇADA`, `pátio` → `PÁTIO`, etc.).

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/recognizers/test_address.py::TestAddressRecognizer -v
```

Expected: all tests pass, including all-caps detection tests, lowercase rejection test, and all existing Title Case detection tests.

**Step 5: Run full test suite**

```bash
uv run pytest tests/ -x -q
```

Expected: all tests pass (153 + 3 new = 156).

**Step 6: Commit**

```bash
git add src/pii_desensitizer/recognizers/address.py tests/recognizers/test_address.py
git commit -m "fix: use explicit case alternation in Portuguese address patterns instead of IGNORECASE"
```

---

## Final Verification

**Step 1: Run full pytest suite**

```bash
uv run pytest tests/ -x -q
```

Expected: all tests pass, 0 failures.

**Step 2: Run the test runner against the live server**

```bash
# Restart server to pick up code changes
kill $(lsof -ti:8200) 2>/dev/null; sleep 1
uv run uvicorn pii_desensitizer.api.app:create_app --factory --port 8200 &
sleep 5

# Run the integration test suite
uv run python run_tests.py --server-url http://localhost --port 8200 --api-key test-key-a-00000000
```

Expected outcome:

| Case | Before | After | Notes |
|------|--------|-------|-------|
| `temporal_01` | FAIL (FP=2: "Born" + "on 1990") | PASS | "Born" fixed by stopword filter (previous plan); "on 1990" fixed by this plan |
| `contact_17` | FAIL | FAIL | Deferred (root cause E — context awareness) |
| `identity_11` | FAIL | FAIL | Deferred (root cause E — context awareness) |

Total: **10 → 2 failures** (1 fixed by this plan, 2 deferred).

**Step 3: Verify no real PII in test data**

All test data uses synthetic tokens: `Exemplo`, `Teste`, `AB 1234`, `MX-00-00`, `Des Voeux Rd`, `MAIN ST`, `RUA DE EXEMPLO`, `EDIFÍCIO COMERCIAL TESTE`. No real names, IDs, or addresses.

---

## Constraints

- **NEVER ADD REAL DATA TO TEST CASE** — all test data uses synthetic tokens
- Use `uv` for all Python commands
- Follow TDD: write failing test → verify it fails → implement → verify it passes → commit
- Do NOT modify `HKIDRecognizer` or `HKPassportRecognizer` — they keep IGNORECASE for lowercase PII detection
- Do NOT modify Chinese address patterns (`_ZH_ADDRESS_PATTERNS`) — they use CJK characters, not affected by IGNORECASE
