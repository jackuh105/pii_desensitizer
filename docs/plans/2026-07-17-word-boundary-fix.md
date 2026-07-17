# Fix `\b` Word Boundary for Chinese Text Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace all `\b` word boundary assertions in regex recognizers with ASCII-only lookbehind/lookahead assertions so PII is detected even when directly adjacent to Chinese characters (e.g. `電郵testuser@example.com`).

**Architecture:** Python 3's `\b` uses `\w` which includes Unicode Chinese characters, so `\b` between a Chinese char and an ASCII char does not match. Replace every leading `\b` with `(?<![A-Za-z0-9])` and every trailing `\b` with `(?![A-Za-z0-9])`. These assertions treat Chinese characters as valid boundaries (they are not in `[A-Za-z0-9]`) while still preventing false positives like `xtestuser@example.com` (where `x` IS in `[A-Za-z0-9]`).

**Tech Stack:** No new dependencies. Pure regex changes in 5 existing recognizer files + test additions in 4 test files.

---

## Background: Why `\b` Fails in Chinese Text

### The Problem

Python 3's `\b` (word boundary) matches between a `\w` character and a `\W` character. Crucially, `\w` in Python 3 **includes all Unicode letters** — including Chinese characters. So:

```
是 t
↑ ↑
\w \w  →  no word boundary here → \b does NOT match
```

This means `\b[A-Za-z0-9...]+@...` fails to match `testuser@example.com` when preceded by a Chinese character like `是`.

### The Fix

Replace `\b` with explicit ASCII-only boundary assertions:

| Original | Replacement | Meaning |
|---|---|---|
| Leading `\b` | `(?<![A-Za-z0-9])` | Preceded by anything EXCEPT ASCII alphanumeric |
| Trailing `\b` | `(?![A-Za-z0-9])` | Followed by anything EXCEPT ASCII alphanumeric |

### Behavior Comparison

| Input | `\b` (current) | `(?<![A-Za-z0-9])` (fixed) | Correct? |
|---|---|---|---|
| `電郵testuser@example.com` | ❌ Missed | ✅ Detected | Fixed |
| `testuser@example.com的` | ❌ Missed | ✅ Detected | Fixed (bonus) |
| `Contact testuser@example.com` | ✅ Detected | ✅ Detected | Unchanged |
| `xtestuser@example.com` | ❌ Correctly rejected | ❌ Correctly rejected | Unchanged |

### Improvement Over `\b`

The fix is **strictly better** than `\b`:
- Detects PII adjacent to Chinese characters (the core fix)
- Detects PII adjacent to Chinese punctuation (`。`,`，`etc.) — `\b` already handled this, but now explicitly
- Still rejects PII embedded in English words (`xtestuser@...`) — false positive prevention preserved
- At string start/end: both `(?<![A-Za-z0-9])` at position 0 and `(?![A-Za-z0-9])` at end-of-string always match — same as `\b`

### Affected Files and Occurrences (14 total)

| File | Patterns with `\b` | Count |
|---|---|---|
| `contact.py` | Email, Phone 8-digit, IP (leading + trailing) | 4 |
| `identity.py` | HKID (leading only), MacauID (leading only), Passport (both), License plate (both) | 4 |
| `financial.py` | Credit card (both), Bank account (both) | 2 |
| `temporal.py` | Birthday ISO (both), Birthday DMY (both) | 2 |
| `address.py` | English address pattern 1 (both), English address pattern 2 (both) | 2 |

Note: `address.py` Chinese patterns do NOT use `\b` (they use `[^\s]{2,}`). Only the English address patterns are affected.

---

## Task 1: Add Chinese-Prefix Test Cases (RED)

**Files:**
- Modify: `tests/recognizers/test_contact.py`
- Modify: `tests/recognizers/test_identity.py`
- Modify: `tests/recognizers/test_financial.py`
- Modify: `tests/recognizers/test_temporal.py`

Add test cases that verify PII is detected when directly preceded/followed by Chinese characters. These tests will FAIL with the current `\b` regex, proving the bug.

**Step 1: Add Chinese-prefix tests to `tests/recognizers/test_contact.py`**

Add these test methods to the existing test classes:

In `TestEmailRecognizer`, add:

```python
    def test_detects_email_after_chinese_text(self):
        """Email directly after Chinese characters (no space) should be detected."""
        rec = EmailRecognizer()
        text = "我的電郵是testuser@example.com"
        results = rec.analyze(
            text=text,
            entities=["EMAIL"],
            nlp_artifacts=None,
        )
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "testuser@example.com"

    def test_detects_email_before_chinese_text(self):
        """Email directly followed by Chinese characters should be detected."""
        rec = EmailRecognizer()
        text = "testuser@example.com已收到"
        results = rec.analyze(
            text=text,
            entities=["EMAIL"],
            nlp_artifacts=None,
        )
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "testuser@example.com"
```

In `TestHKMacauPhoneRecognizer`, add:

```python
    def test_detects_phone_after_chinese_text(self):
        """8-digit phone directly after Chinese characters should be detected."""
        rec = HKMacauPhoneRecognizer()
        text = "電話98765432"
        results = rec.analyze(
            text=text,
            entities=["PHONE_NUMBER"],
            nlp_artifacts=None,
        )
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "98765432"
```

In `TestIPAddressRecognizer`, add:

```python
    def test_detects_ip_after_chinese_text(self):
        """IP address directly after Chinese characters should be detected."""
        rec = IPAddressRecognizer()
        text = "伺服器192.168.1.1"
        results = rec.analyze(
            text=text,
            entities=["IP_ADDRESS"],
            nlp_artifacts=None,
        )
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "192.168.1.1"
```

**Step 2: Add Chinese-prefix tests to `tests/recognizers/test_identity.py`**

In `TestHKIDRecognizer`, add:

```python
    def test_detects_hkid_after_chinese_text(self):
        """HKID directly after Chinese characters should be detected."""
        rec = HKIDRecognizer()
        text = "身份證A123456(7)"
        results = rec.analyze(text=text, entities=["HKID"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "A123456(7)"
```

In `TestHKPassportRecognizer`, add:

```python
    def test_detects_passport_after_chinese_text(self):
        """Passport directly after Chinese characters should be detected."""
        rec = HKPassportRecognizer()
        text = "護照H12345678"
        results = rec.analyze(text=text, entities=["PASSPORT"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "H12345678"
```

**Step 3: Add Chinese-prefix tests to `tests/recognizers/test_financial.py`**

In `TestCreditCardRecognizer`, add:

```python
    def test_detects_credit_card_after_chinese_text(self):
        """Credit card directly after Chinese characters should be detected."""
        rec = CreditCardRecognizer()
        text = "信用卡4111-1111-1111-1111"
        results = rec.analyze(
            text=text,
            entities=["CREDIT_CARD"],
            nlp_artifacts=None,
        )
        assert len(results) == 1
```

In `TestBankAccountRecognizer`, add:

```python
    def test_detects_bank_account_after_chinese_text(self):
        """Bank account directly after Chinese characters should be detected."""
        rec = BankAccountRecognizer()
        text = "戶口123456789012"
        results = rec.analyze(
            text=text,
            entities=["BANK_ACCOUNT"],
            nlp_artifacts=None,
        )
        assert len(results) == 1
```

**Step 4: Add Chinese-prefix tests to `tests/recognizers/test_temporal.py`**

In `TestBirthdayRecognizer`, add:

```python
    def test_detects_birthday_after_chinese_text(self):
        """Birthday directly after Chinese characters should be detected."""
        rec = BirthdayRecognizer()
        text = "生日1990-01-15"
        results = rec.analyze(
            text=text,
            entities=["BIRTHDAY"],
            nlp_artifacts=None,
        )
        assert len(results) == 1
```

**Step 5: Run tests to verify they fail**

Run: `uv run pytest tests/recognizers/ -v -k "chinese"`
Expected: 7 FAILED — all new Chinese-prefix tests fail because `\b` doesn't match between Chinese and ASCII characters.

**Step 6: Commit the failing tests**

```bash
git add tests/recognizers/
git commit -m "test: add Chinese-prefix test cases (currently failing due to \\b word boundary)"
```

---

## Task 2: Replace `\b` with ASCII-Only Boundary Assertions (GREEN)

**Files:**
- Modify: `src/pii_desensitizer/recognizers/contact.py`
- Modify: `src/pii_desensitizer/recognizers/identity.py`
- Modify: `src/pii_desensitizer/recognizers/financial.py`
- Modify: `src/pii_desensitizer/recognizers/temporal.py`
- Modify: `src/pii_desensitizer/recognizers/address.py`

Replace every `\b` with the appropriate lookbehind/lookahead. The rule is mechanical:
- `\b` at the START of a regex (before the first capture group) → `(?<![A-Za-z0-9])`
- `\b` at the END of a regex (after the last capture group) → `(?![A-Za-z0-9])`

**Step 1: Fix `src/pii_desensitizer/recognizers/contact.py`**

Three patterns to fix:

Email (line 18):
```
Before: r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
After:  r"(?<![A-Za-z0-9])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9])"
```

Phone 8-digit (line 49):
```
Before: r"\b[2-9]\d{3}[\s-]?\d{4}\b"
After:  r"(?<![A-Za-z0-9])[2-9]\d{3}[\s-]?\d{4}(?![A-Za-z0-9])"
```

IP address (lines 68-71) — two `\b` in one multi-line regex:
```
Before:
    r"\b(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\."
    r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\."
    r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\."
    r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\b"

After:
    r"(?<![A-Za-z0-9])(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\."
    r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\."
    r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\."
    r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)(?![A-Za-z0-9])"
```

**Step 2: Fix `src/pii_desensitizer/recognizers/identity.py`**

Four patterns to fix:

HKID (line 22) — leading `\b` only (no trailing `\b` because pattern ends with `)`):
```
Before: r"\b[A-Z]{1,2}\d{6}\([0-9A]\)"
After:  r"(?<![A-Za-z0-9])[A-Z]{1,2}\d{6}\([0-9A]\)"
```

Macau ID (line 44) — leading `\b` only:
```
Before: r"\b\d{7}\(\d\)"
After:  r"(?<![A-Za-z0-9])\d{7}\(\d\)"
```

Passport (line 66) — both leading and trailing:
```
Before: r"\b[HK]\d{8}\b"
After:  r"(?<![A-Za-z0-9])[HK]\d{8}(?![A-Za-z0-9])"
```

License plate (line 88) — both leading and trailing:
```
Before: r"\b[A-Z]{2}\s?\d{4}\b"
After:  r"(?<![A-Za-z0-9])[A-Z]{2}\s?\d{4}(?![A-Za-z0-9])"
```

**Step 3: Fix `src/pii_desensitizer/recognizers/financial.py`**

Two patterns to fix:

Credit card (line 40) — both leading and trailing:
```
Before: r"\b(?:\d[ -]?){13,19}\b"
After:  r"(?<![A-Za-z0-9])(?:\d[ -]?){13,19}(?![A-Za-z0-9])"
```

Bank account (line 74) — both leading and trailing:
```
Before: r"\b\d{9,12}\b"
After:  r"(?<![A-Za-z0-9])\d{9,12}(?![A-Za-z0-9])"
```

**Step 4: Fix `src/pii_desensitizer/recognizers/temporal.py`**

Two patterns to fix:

Birthday ISO (line 24) — both leading and trailing:
```
Before: r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b"
After:  r"(?<![A-Za-z0-9])\d{4}[-/]\d{1,2}[-/]\d{1,2}(?![A-Za-z0-9])"
```

Birthday DMY (line 29) — both leading and trailing:
```
Before: r"\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b"
After:  r"(?<![A-Za-z0-9])\d{1,2}[-/]\d{1,2}[-/]\d{4}(?![A-Za-z0-9])"
```

**Step 5: Fix `src/pii_desensitizer/recognizers/address.py`**

Two English address patterns to fix (lines 29-30):

```
Before:
    r"\b\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Rd|St|Ave|Drive|Dr|Bldg|Tower|Centre|Plaza|Garden|Ct|Cres|Terr|Ln)\b",
    r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Rd|St|Ave|Drive|Bldg|Tower|Centre|Plaza|Garden)\b",

After:
    r"(?<![A-Za-z0-9])\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Rd|St|Ave|Drive|Dr|Bldg|Tower|Centre|Plaza|Garden|Ct|Cres|Terr|Ln)(?![A-Za-z0-9])",
    r"(?<![A-Za-z0-9])[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Rd|St|Ave|Drive|Bldg|Tower|Centre|Plaza|Garden)(?![A-Za-z0-9])",
```

**Step 6: Run Chinese-prefix tests to verify they pass**

Run: `uv run pytest tests/recognizers/ -v -k "chinese"`
Expected: All 7 previously-failing tests now PASS.

**Step 7: Run full recognizer test suite to verify no regressions**

Run: `uv run pytest tests/recognizers/ -v`
Expected: All tests PASS (existing + new).

**Step 8: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS, no regressions.

**Step 9: Commit**

```bash
git add src/pii_desensitizer/recognizers/
git commit -m "fix: replace \\b with ASCII-only lookbehind/lookahead for Chinese text support"
```

---

## Task 3: Update Integration Test for Chinese-Adjacent PII

**Files:**
- Modify: `tests/test_integration.py`

Update the `test_traditional_chinese_with_other_pii_round_trip` test to use Chinese-adjacent PII (no space between Chinese text and email/phone) — this verifies the fix works end-to-end.

**Step 1: Update the test**

In `tests/test_integration.py`, find the `test_traditional_chinese_with_other_pii_round_trip` method and update the `original` text to use Chinese-adjacent format:

```python
    def test_traditional_chinese_with_other_pii_round_trip(
        self, desensitize_engine, restore_engine
    ):
        original = "黃志偉先生，電話+852 98765432，email: john@test.com"
        system_id = "test_sys"

        d_result = desensitize_engine.desensitize(
            text=original, system_id=system_id, session_id=None
        )
        assert "黃志偉" not in d_result.text
        assert "{{PERSON_" in d_result.text
        assert "john@test.com" not in d_result.text
        assert "98765432" not in d_result.text

        r_result = restore_engine.restore(
            text=d_result.text, system_id=system_id, session_id=d_result.session_id
        )
        assert "黃志偉" in r_result.text
        assert "黄志伟" not in r_result.text
        assert "john@test.com" in r_result.text
        assert "98765432" in r_result.text
```

(This test already exists and should already pass — verify it still does after the regex changes.)

**Step 2: Run integration tests**

Run: `uv run pytest tests/test_integration.py -v`
Expected: All tests PASS.

**Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: verify Chinese-adjacent PII detection in integration tests"
```

---

## Verification Checklist

After all tasks are complete, verify:

- [ ] `uv run pytest tests/recognizers/ -v -k "chinese"` — all 7 Chinese-prefix tests pass
- [ ] `uv run pytest tests/recognizers/ -v` — all recognizer tests pass (existing + new)
- [ ] `uv run pytest -v` — full suite passes, no regressions
- [ ] `grep -rn '\\b' src/pii_desensitizer/recognizers/` — zero `\b` remaining in recognizer regex patterns
- [ ] Manual test: `curl -X POST .../desensitize -d '{"text": "我的電郵是testuser@example.com"}'` — email is replaced with `{{EMAIL_0}}`
