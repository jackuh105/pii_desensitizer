# Word Boundary Fix + Recognizer Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace all `\b` word boundary assertions with ASCII-only lookbehind/lookahead so PII is detected when adjacent to Chinese characters, plus improve credit card (BIN-based), phone (3-tier score), and license plate (Macau format) recognizers, and remove bank account recognizer from active detection.

**Architecture:** Python 3's `\b` uses `\w` which includes Unicode Chinese characters, so `\b` between a Chinese char and an ASCII char does not match. Replace every leading `\b` with `(?<![A-Za-z0-9])` and every trailing `\b` with `(?![A-Za-z0-9])`. Additionally: rewrite credit card recognizer with per-brand BIN regex patterns, rewrite phone recognizer with 3-tier scoring, add Macau license plate format, and unregister bank account recognizer.

**Tech Stack:** No new dependencies. Pure regex and logic changes in existing recognizer files.

---

## Decisions Summary

| # | Decision | Details |
|---|---|---|
| 1 | All `\b` → ASCII-only boundaries | Leading: `(?<![A-Za-z0-9])`, Trailing: `(?![A-Za-z0-9])` |
| 2 | Bank account recognizer | Remove from `ALL_ENTITIES` and `__init__.py` registration; keep code |
| 3 | Credit card recognizer | Rewrite with 5 brand-specific BIN patterns + Luhn validation |
| 4 | Phone recognizer | 3-tier: +852/+853 score 0.95, `28` prefix score 0.85, other 8-digit score 0.4 |
| 5 | License plate recognizer | Add Macau format `XX-NN-NN` alongside existing HK format |
| 6 | HKID/Macau ID | Leading boundary only (trailing is `)`, natural boundary) |
| 7 | Address English patterns | Also replace `\b` |
| 8 | Birthday | Also replace `\b`, format unchanged |

---

## Task 1: Add Failing Tests for Chinese-Adjacent PII Detection (RED)

**Files:**
- Modify: `tests/recognizers/test_contact.py`
- Modify: `tests/recognizers/test_identity.py`
- Modify: `tests/recognizers/test_financial.py`
- Modify: `tests/recognizers/test_temporal.py`

Add test cases that verify PII is detected when directly preceded by Chinese characters. These tests will FAIL with the current `\b` regex.

**Step 1: Add Chinese-adjacent tests to `tests/recognizers/test_contact.py`**

Add these methods to the existing test classes:

In `TestEmailRecognizer`:
```python
    def test_detects_email_after_chinese_text(self):
        rec = EmailRecognizer()
        text = "我的電郵是testuser@example.com"
        results = rec.analyze(text=text, entities=["EMAIL"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "testuser@example.com"

    def test_detects_email_before_chinese_text(self):
        rec = EmailRecognizer()
        text = "testuser@example.com已收到"
        results = rec.analyze(text=text, entities=["EMAIL"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "testuser@example.com"
```

In `TestHKMacauPhoneRecognizer`:
```python
    def test_detects_phone_after_chinese_text(self):
        rec = HKMacauPhoneRecognizer()
        text = "電話98765432"
        results = rec.analyze(text=text, entities=["PHONE_NUMBER"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "98765432"

    def test_detects_macau_landline_28_prefix(self):
        rec = HKMacauPhoneRecognizer()
        text = "辦公電話28512345"
        results = rec.analyze(text=text, entities=["PHONE_NUMBER"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "28512345"
```

In `TestIPAddressRecognizer`:
```python
    def test_detects_ip_after_chinese_text(self):
        rec = IPAddressRecognizer()
        text = "伺服器192.168.1.1"
        results = rec.analyze(text=text, entities=["IP_ADDRESS"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "192.168.1.1"
```

**Step 2: Add Chinese-adjacent tests to `tests/recognizers/test_identity.py`**

In `TestHKIDRecognizer`:
```python
    def test_detects_hkid_after_chinese_text(self):
        rec = HKIDRecognizer()
        text = "身份證A123456(7)"
        results = rec.analyze(text=text, entities=["HKID"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "A123456(7)"
```

In `TestHKPassportRecognizer`:
```python
    def test_detects_passport_after_chinese_text(self):
        rec = HKPassportRecognizer()
        text = "護照H12345678"
        results = rec.analyze(text=text, entities=["PASSPORT"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "H12345678"
```

In `TestHKLicensePlateRecognizer`:
```python
    def test_detects_macau_license_plate(self):
        rec = HKLicensePlateRecognizer()
        text = "車牌MX-00-00"
        results = rec.analyze(text=text, entities=["LICENSE_PLATE"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "MX-00-00"
```

**Step 3: Add Chinese-adjacent tests to `tests/recognizers/test_financial.py`**

In `TestCreditCardRecognizer`:
```python
    def test_detects_visa_after_chinese_text(self):
        rec = CreditCardRecognizer()
        text = "信用卡4111-1111-1111-1111"
        results = rec.analyze(text=text, entities=["CREDIT_CARD"], nlp_artifacts=None)
        assert len(results) == 1

    def test_detects_unionpay(self):
        rec = CreditCardRecognizer()
        text = "銀聯卡6200000000000005"
        results = rec.analyze(text=text, entities=["CREDIT_CARD"], nlp_artifacts=None)
        assert len(results) == 1

    def test_detects_amex_15_digit(self):
        rec = CreditCardRecognizer()
        text = "378282246310005"
        results = rec.analyze(text=text, entities=["CREDIT_CARD"], nlp_artifacts=None)
        assert len(results) == 1

    def test_detects_mastercard(self):
        rec = CreditCardRecognizer()
        text = "5500000000000004"
        results = rec.analyze(text=text, entities=["CREDIT_CARD"], nlp_artifacts=None)
        assert len(results) == 1

    def test_detects_jcb(self):
        rec = CreditCardRecognizer()
        text = "3566002020360505"
        results = rec.analyze(text=text, entities=["CREDIT_CARD"], nlp_artifacts=None)
        assert len(results) == 1
```

**Step 4: Add Chinese-adjacent tests to `tests/recognizers/test_temporal.py`**

In `TestBirthdayRecognizer`:
```python
    def test_detects_birthday_after_chinese_text(self):
        rec = BirthdayRecognizer()
        text = "生日1990-01-15"
        results = rec.analyze(text=text, entities=["BIRTHDAY"], nlp_artifacts=None)
        assert len(results) == 1
```

**Step 5: Run tests to verify they fail**

Run: `uv run pytest tests/recognizers/ -v -k "chinese or macau or unionpay or amex or mastercard or jcb"`
Expected: Multiple FAILURES — all new tests fail with current `\b` regex or missing formats.

**Step 6: Commit**

```bash
git add tests/recognizers/
git commit -m "test: add Chinese-adjacent and BIN-format test cases (currently failing)"
```

---

## Task 2: Fix `\b` Boundaries + Rewrite Recognizers (GREEN)

**Files:**
- Modify: `src/pii_desensitizer/recognizers/contact.py`
- Modify: `src/pii_desensitizer/recognizers/identity.py`
- Modify: `src/pii_desensitizer/recognizers/financial.py`
- Modify: `src/pii_desensitizer/recognizers/temporal.py`
- Modify: `src/pii_desensitizer/recognizers/address.py`

**Step 1: Rewrite `src/pii_desensitizer/recognizers/contact.py`**

```python
"""Regex-based recognizers for contact PII: Email, Phone (HK/Macau), IP address."""

from __future__ import annotations

from presidio_analyzer import Pattern, PatternRecognizer


class EmailRecognizer(PatternRecognizer):
    """Detect email addresses."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity="EMAIL",
            patterns=[
                Pattern(
                    name="email_pattern",
                    regex=r"(?<![A-Za-z0-9])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9])",
                    score=0.95,
                )
            ],
            name="EmailRecognizer",
            context=["email", "mail", "contact", "reach", "電郵", "電子郵件"],
        )


class HKMacauPhoneRecognizer(PatternRecognizer):
    """Detect Hong Kong and Macau phone numbers.

    Three-tier scoring:
      - +852/+853 with country code: score 0.95 (highest confidence)
      - 28 prefix (Macau landline): score 0.85
      - Other 8-digit: score 0.4 (relies on context)
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="PHONE_NUMBER",
            patterns=[
                Pattern(
                    name="hk_macau_phone_with_country_code",
                    regex=r"(?<![A-Za-z0-9])(?:\+85[23])[\s-]?\d{4}[\s-]?\d{4}(?![A-Za-z0-9])",
                    score=0.95,
                ),
                Pattern(
                    name="macau_landline_28_prefix",
                    regex=r"(?<![A-Za-z0-9])28\d{6}(?![A-Za-z0-9])",
                    score=0.85,
                ),
                Pattern(
                    name="hk_macau_phone_8_digit",
                    regex=r"(?<![A-Za-z0-9])[2-9]\d{3}[\s-]?\d{4}(?![A-Za-z0-9])",
                    score=0.4,
                ),
            ],
            name="HKMacauPhoneRecognizer",
            context=["phone", "tel", "mobile", "call", "fax", "聯絡", "電話", "手提", "辦公"],
        )


class IPAddressRecognizer(PatternRecognizer):
    """Detect IPv4 addresses (4 octets, each 0-255)."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity="IP_ADDRESS",
            patterns=[
                Pattern(
                    name="ipv4_pattern",
                    regex=(
                        r"(?<![A-Za-z0-9])(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\."
                        r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\."
                        r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\."
                        r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)(?![A-Za-z0-9])"
                    ),
                    score=0.9,
                )
            ],
            name="IPAddressRecognizer",
            context=["ip", "server", "address", "host", "伺服器"],
        )
```

**Step 2: Rewrite `src/pii_desensitizer/recognizers/identity.py`**

```python
"""Regex-based recognizers for identity PII: HKID, Macau ID, Passport, License plate."""

from __future__ import annotations

from presidio_analyzer import Pattern, PatternRecognizer


class HKIDRecognizer(PatternRecognizer):
    """Detect Hong Kong Identity Card numbers.

    Format: 1-2 letters + 6 digits + (1 check digit or A)
    Example: A123456(7), AB123456(8)
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="HKID",
            patterns=[
                Pattern(
                    name="hkid_pattern",
                    regex=r"(?<![A-Za-z0-9])[A-Z]{1,2}\d{6}\([0-9A]\)",
                    score=0.95,
                )
            ],
            name="HKIDRecognizer",
            context=["HKID", "身份證", "身份", "identity", "id card", "card no"],
        )


class MacauIDRecognizer(PatternRecognizer):
    """Detect Macau Identity Card numbers.

    Format: 7 digits + (1 check digit)
    Example: 1234567(8)
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="MACAU_ID",
            patterns=[
                Pattern(
                    name="macau_id_pattern",
                    regex=r"(?<![A-Za-z0-9])\d{7}\(\d\)",
                    score=0.85,
                )
            ],
            name="MacauIDRecognizer",
            context=["macau", "澳門", "身份證", "bilhete", "id"],
        )


class HKPassportRecognizer(PatternRecognizer):
    """Detect Hong Kong SAR passport numbers.

    Format: H or K + 8 digits
    Example: H12345678, K12345678
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="PASSPORT",
            patterns=[
                Pattern(
                    name="hk_passport_pattern",
                    regex=r"(?<![A-Za-z0-9])[HK]\d{8}(?![A-Za-z0-9])",
                    score=0.85,
                )
            ],
            name="HKPassportRecognizer",
            context=["passport", "護照", "旅行證件", "travel"],
        )


class HKLicensePlateRecognizer(PatternRecognizer):
    """Detect Hong Kong and Macau vehicle license plates.

    HK format: 2 English letters + optional space + 4 digits
      Example: AB 1234, AB1234

    Macau format: 2 English letters + hyphen + 2 digits + hyphen + 2 digits
      Example: MX-00-00
    """

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
        )
```

**Step 3: Rewrite `src/pii_desensitizer/recognizers/financial.py`**

```python
"""Regex-based recognizers for financial PII: credit card (BIN-based)."""

from __future__ import annotations

from typing import List

from presidio_analyzer import Pattern, PatternRecognizer, RecognizerResult


def _luhn_check(number_str: str) -> bool:
    """Validate a number string using the Luhn algorithm."""
    digits = [int(d) for d in number_str if d.isdigit()]
    if len(digits) < 13:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, digit in enumerate(digits):
        if i % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


class CreditCardRecognizer(PatternRecognizer):
    """Detect credit card numbers by brand BIN prefix + Luhn validation.

    Brand-specific patterns:
      - Visa: starts with 4, length 13 or 16
      - Mastercard: starts with 51-55 or 2221-2720, length 16
      - Amex: starts with 34 or 37, length 15
      - JCB: starts with 3528-3589, length 16
      - UnionPay: starts with 62, length 16-19

    Each match is then validated with the Luhn algorithm.
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="CREDIT_CARD",
            patterns=[
                Pattern(
                    name="visa_pattern",
                    regex=r"(?<![A-Za-z0-9])4(?:\d[ -]?){12,15}(?![A-Za-z0-9])",
                    score=0.5,
                ),
                Pattern(
                    name="mastercard_pattern",
                    regex=r"(?<![A-Za-z0-9])(?:5[1-5]\d{2}|222[1-9]|22[3-9]\d|2[3-6]\d{2}|27[01]\d|2720)(?:\d[ -]?){11}(?![A-Za-z0-9])",
                    score=0.5,
                ),
                Pattern(
                    name="amex_pattern",
                    regex=r"(?<![A-Za-z0-9])3[47]\d{2}[\s-]?\d{6}[\s-]?\d{5}(?![A-Za-z0-9])",
                    score=0.5,
                ),
                Pattern(
                    name="jcb_pattern",
                    regex=r"(?<![A-Za-z0-9])3(?:5[2-9]\d{2}|5[89]\d)(?:\d[ -]?){10,11}(?![A-Za-z0-9])",
                    score=0.5,
                ),
                Pattern(
                    name="unionpay_pattern",
                    regex=r"(?<![A-Za-z0-9])62(?:\d[ -]?){14,17}(?![A-Za-z0-9])",
                    score=0.5,
                ),
            ],
            name="CreditCardRecognizer",
            context=["card", "credit", "visa", "master", "amex", "jcb", "unionpay", "銀聯", "信用卡", "卡號"],
        )

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None) -> List[RecognizerResult]:
        """Run regex match, then validate each match with Luhn."""
        results = super().analyze(text, entities, nlp_artifacts)
        validated = []
        for result in results:
            matched_text = text[result.start : result.end]
            digits_only = matched_text.replace(" ", "").replace("-", "")
            if _luhn_check(digits_only):
                result.score = 0.95
                validated.append(result)
        return validated


class BankAccountRecognizer(PatternRecognizer):
    """Detect HK bank account numbers.

    NOTE: Unregistered from active detection. Bank account numbers have no
    reliable format (vary by bank, 9-19 digits), making pure regex detection
    highly prone to false positives. Code is retained for potential future use
    with additional validation logic.
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="BANK_ACCOUNT",
            patterns=[
                Pattern(
                    name="bank_account_pattern",
                    regex=r"(?<![A-Za-z0-9])\d{9,12}(?![A-Za-z0-9])",
                    score=0.4,
                )
            ],
            name="BankAccountRecognizer",
            context=["account", "bank", "銀行", "戶口", "帳號", "轉帳", "transfer", "hsbc", "hang seng"],
        )
```

**Step 4: Rewrite `src/pii_desensitizer/recognizers/temporal.py`**

```python
"""Regex-based recognizer for birthday/date of birth."""

from __future__ import annotations

from presidio_analyzer import Pattern, PatternRecognizer


class BirthdayRecognizer(PatternRecognizer):
    """Detect birthday / date of birth in common formats.

    Formats matched:
      - YYYY-MM-DD (ISO): 1990-01-15
      - DD/MM/YYYY or DD-MM-YYYY: 15/01/1990
      - YYYY/MM/DD: 1990/01/15
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="BIRTHDAY",
            patterns=[
                Pattern(
                    name="birthday_iso",
                    regex=r"(?<![A-Za-z0-9])\d{4}[-/]\d{1,2}[-/]\d{1,2}(?![A-Za-z0-9])",
                    score=0.4,
                ),
                Pattern(
                    name="birthday_dmy",
                    regex=r"(?<![A-Za-z0-9])\d{1,2}[-/]\d{1,2}[-/]\d{4}(?![A-Za-z0-9])",
                    score=0.4,
                ),
            ],
            name="BirthdayRecognizer",
            context=["birth", "born", "dob", "生日", "出生", "birth date", "date of birth"],
        )
```

**Step 5: Fix `src/pii_desensitizer/recognizers/address.py` English patterns**

Replace the `_EN_ADDRESS_PATTERNS` list (lines 28-31):

```python
_EN_ADDRESS_PATTERNS = [
    r"(?<![A-Za-z0-9])\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Rd|St|Ave|Drive|Dr|Bldg|Tower|Centre|Plaza|Garden|Ct|Cres|Terr|Ln)(?![A-Za-z0-9])",
    r"(?<![A-Za-z0-9])[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Rd|St|Ave|Drive|Bldg|Tower|Centre|Plaza|Garden)(?![A-Za-z0-9])",
]
```

**Step 6: Run Chinese-adjacent tests to verify they pass**

Run: `uv run pytest tests/recognizers/ -v -k "chinese or macau or unionpay or amex or mastercard or jcb"`
Expected: All previously-failing tests now PASS.

**Step 7: Run full recognizer test suite**

Run: `uv run pytest tests/recognizers/ -v`
Expected: All tests PASS (existing + new).

**Step 8: Commit**

```bash
git add src/pii_desensitizer/recognizers/
git commit -m "fix: replace \\b with ASCII-only boundaries, rewrite credit card BIN, phone 3-tier, Macau plate"
```

---

## Task 3: Unregister Bank Account Recognizer

**Files:**
- Modify: `src/pii_desensitizer/recognizers/__init__.py`

**Step 1: Remove BankAccountRecognizer from imports, ALL_ENTITIES, and registration**

In `src/pii_desensitizer/recognizers/__init__.py`:

1. Remove `BankAccountRecognizer` from the import statement:
```python
from pii_desensitizer.recognizers.financial import (
    CreditCardRecognizer,
)
```

2. Remove `"BANK_ACCOUNT"` from `ALL_ENTITIES` list.

3. Remove `BankAccountRecognizer()` from the `custom_recognizers` list.

**Step 2: Verify no import errors**

Run: `uv run python -c "from pii_desensitizer.recognizers import build_analyzer, ALL_ENTITIES; print(f'Entities: {ALL_ENTITIES}'); print(f'Count: {len(ALL_ENTITIES)}')"`
Expected: 11 entities listed, no `BANK_ACCOUNT`.

**Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS. Bank account recognizer tests still pass (code retained, just unregistered).

**Step 4: Commit**

```bash
git add src/pii_desensitizer/recognizers/__init__.py
git commit -m "refactor: unregister BankAccountRecognizer (no reliable format for detection)"
```

---

## Task 4: Update Integration Tests and README

**Files:**
- Modify: `tests/test_integration.py`
- Modify: `README.md`

**Step 1: Verify integration tests still pass with new regexes**

Run: `uv run pytest tests/test_integration.py -v`

If `test_multiple_pii_types_round_trip` uses `BANK_ACCOUNT`, update it. Check the test content and adjust if needed.

**Step 2: Update README**

In the PII Types table, mark Bank Account as removed and update count from 12 to 11.

In the Known Limitations section, add note about bank accounts.

**Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS.

**Step 4: Commit**

```bash
git add tests/test_integration.py README.md
git commit -m "docs: update README for bank account removal and recognizer improvements"
```

---

## Verification Checklist

After all tasks are complete:

- [ ] `uv run pytest tests/recognizers/ -v -k "chinese"` — all Chinese-adjacent tests pass
- [ ] `uv run pytest tests/recognizers/ -v` — all recognizer tests pass
- [ ] `uv run pytest -v` — full suite passes, no regressions
- [ ] `grep -rn '\\b' src/pii_desensitizer/recognizers/` — zero `\b` remaining
- [ ] `BANK_ACCOUNT` not in `ALL_ENTITIES`
- [ ] Credit card tests pass for Visa, Mastercard, Amex, JCB, UnionPay
- [ ] Macau license plate `MX-00-00` detected
- [ ] Phone `28` prefix gets higher score than generic 8-digit
