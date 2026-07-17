# Macau ID Simplified Format + NER False Positive Filter Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix three issues found in real-world testing: (1) Macau ID recognizer misses 8-digit simplified format (no parentheses), (2) spaCy NER produces false positives on punctuation-adjacent text like `)未`, (3) Macau ID formal format regex doesn't restrict the first digit.

**Architecture:** Add a new regex pattern to `MacauIDRecognizer` for the simplified 8-digit format (`[157]\d{7}`), with tiered scoring: `1`-prefixed IDs get high score (unambiguous — phones never start with `1`), `5/7`-prefixed IDs get low score (ambiguous with HK mobile — relies on context). Add a post-filter in `ChinesePersonRecognizer.analyze()` that discards PERSON results containing punctuation characters. Fix the formal format regex to require `[157]` as the first digit.

**Tech Stack:** No new dependencies. Regex changes in `identity.py`, post-filter logic in `person_ner.py`.

---

## Background

### Issue 1: Macau ID Simplified Format

Macau Identity Card numbers are 8 digits starting with `1`, `5`, or `7`. The formal representation is `XXXXXXX(X)` (7 digits + check digit in parentheses), but in practice they often appear as bare 8-digit numbers `XXXXXXXX`.

**Current regex:** `(?<![A-Za-z0-9])\d{7}\(\d\)` — only matches the formal format with parentheses. Also has a bug: doesn't restrict the first digit, so any 7-digit number + `(digit)` matches.

**Overlap with phone numbers:**

| Prefix | Macau ID? | Phone? | Ambiguous? |
|---|---|---|---|
| `1` | ✅ | ❌ (phones never start with 1) | No — unambiguous |
| `5` | ✅ | ✅ (HK mobile) | Yes |
| `7` | ✅ | ✅ (HK mobile) | Yes |

**Strategy:**
- Formal format `[157]\d{6}\(\d\)`: high score (0.85) — format is unique to ID cards
- Simplified `1\d{7}`: high score (0.85) — `1` prefix is unambiguous
- Simplified `[57]\d{7}`: low score (0.4) — ambiguous with phone, relies on context

Context keywords (existing): `macau`, `澳門`, `身份證`, `bilhete`, `id`, plus new: `id no`, `id number`, `證件號碼`, `證件編號`, `編號`

### Issue 2: NER False Positive on Punctuation

spaCy's `zh_core_web_sm` sometimes tags punctuation-adjacent text as `PERSON`. Real example: `工具(高級)未開啟` → NER tags `)未` as PERSON.

**Filter strategy:** After NER, discard any PERSON result whose matched text contains punctuation characters (`()（）.,，。、；;：:！!？?「」『』"'` etc.). Real person names (Chinese or English) never contain punctuation.

### Issue 3: Macau ID Formal Format First Digit

Current regex `\d{7}\(\d\)` accepts any digit as first character. Should be `[157]\d{6}\(\d\)` to match the actual Macau ID format.

---

## Task 1: Add Failing Tests for Macau ID Simplified Format and NER Filter (RED)

**Files:**
- Modify: `tests/recognizers/test_identity.py`
- Modify: `tests/recognizers/test_person_ner.py`

**Step 1: Add Macau ID tests to `tests/recognizers/test_identity.py`**

Add these methods to `TestMacauIDRecognizer`:

```python
    def test_detects_macau_id_simplified_1_prefix(self):
        """Simplified Macau ID starting with 1 (no parentheses)."""
        rec = MacauIDRecognizer()
        text = "ID NO.: 11234567"
        results = rec.analyze(text=text, entities=["MACAU_ID"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "11234567"

    def test_detects_macau_id_simplified_after_chinese(self):
        """Simplified Macau ID directly after Chinese text."""
        rec = MacauIDRecognizer()
        text = "身份證14567890"
        results = rec.analyze(text=text, entities=["MACAU_ID"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "14567890"

    def test_detects_macau_id_formal_1_prefix(self):
        """Formal Macau ID with parentheses, 1 prefix."""
        rec = MacauIDRecognizer()
        text = "1512720(2)"
        results = rec.analyze(text=text, entities=["MACAU_ID"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "1512720(2)"

    def test_detects_macau_id_formal_5_prefix(self):
        """Formal Macau ID with parentheses, 5 prefix."""
        rec = MacauIDRecognizer()
        text = "5123456(7)"
        results = rec.analyze(text=text, entities=["MACAU_ID"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "5123456(7)"

    def test_detects_macau_id_formal_7_prefix(self):
        """Formal Macau ID with parentheses, 7 prefix."""
        rec = MacauIDRecognizer()
        text = "7123456(8)"
        results = rec.analyze(text=text, entities=["MACAU_ID"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "7123456(7)"

    def test_no_false_positive_on_non_macau_id_formal(self):
        """8 digits starting with 2,3,4,6,8,9 should not match as Macau ID."""
        rec = MacauIDRecognizer()
        text = "ID: 28512345"
        results = rec.analyze(text=text, entities=["MACAU_ID"], nlp_artifacts=None)
        assert len(results) == 0

    def test_no_false_positive_on_non_macau_id_formal_parens(self):
        """Formal format with non-1/5/7 prefix should not match."""
        rec = MacauIDRecognizer()
        text = "8123456(9)"
        results = rec.analyze(text=text, entities=["MACAU_ID"], nlp_artifacts=None)
        assert len(results) == 0
```

**Step 2: Add NER false positive filter tests to `tests/recognizers/test_person_ner.py`**

Add these methods to `TestChinesePersonRecognizer`:

```python
    def test_filters_punctuation_false_positive(self, recognizer):
        """PERSON results containing punctuation should be filtered out."""
        text = "電子身份識別工具(高級)未開啟"
        results = recognizer.analyze(
            text=text,
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        for r in results:
            matched = text[r.start:r.end]
            assert "(" not in matched
            assert ")" not in matched
            assert "（" not in matched
            assert "）" not in matched

    def test_does_not_filter_real_names_with_no_punctuation(self, recognizer):
        """Real person names (no punctuation) should not be filtered."""
        text = "請聯絡陳大文先生"
        results = recognizer.analyze(
            text=text,
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        person_texts = [text[r.start:r.end] for r in results]
        assert "陳大文" in person_texts
```

**Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/recognizers/test_identity.py tests/recognizers/test_person_ner.py -v --tb=line`
Expected: Multiple FAILURES — Macau ID simplified format tests fail (regex doesn't match bare 8 digits), formal format prefix tests fail (regex accepts any first digit), NER filter test fails (`)未` is returned as PERSON).

**Step 4: Commit**

```bash
git add tests/recognizers/
git commit -m "test: add Macau ID simplified format and NER filter tests (currently failing)"
```

---

## Task 2: Fix Macau ID Recognizer (GREEN — Part 1)

**Files:**
- Modify: `src/pii_desensitizer/recognizers/identity.py`

**Step 1: Rewrite `MacauIDRecognizer`**

Replace the `MacauIDRecognizer` class (lines 30-49 in `identity.py`) with:

```python
class MacauIDRecognizer(PatternRecognizer):
    """Detect Macau Identity Card numbers.

    Macau ID numbers are 8 digits starting with 1, 5, or 7.
    Two formats:
      - Formal:   [157]XXXXXX(X)  e.g. 1512720(2)
      - Simplified: [157]XXXXXXX   e.g. 11234567

    Scoring:
      - Formal format: 0.85 (parentheses make it unambiguous)
      - Simplified 1-prefix: 0.85 (phones never start with 1)
      - Simplified 5/7-prefix: 0.4 (ambiguous with HK mobile, relies on context)
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="MACAU_ID",
            patterns=[
                Pattern(
                    name="macau_id_formal",
                    regex=r"(?<![A-Za-z0-9])[157]\d{6}\(\d\)",
                    score=0.85,
                ),
                Pattern(
                    name="macau_id_simplified_1_prefix",
                    regex=r"(?<![A-Za-z0-9])1\d{7}(?![A-Za-z0-9])",
                    score=0.85,
                ),
                Pattern(
                    name="macau_id_simplified_57_prefix",
                    regex=r"(?<![A-Za-z0-9])[57]\d{7}(?![A-Za-z0-9])",
                    score=0.4,
                ),
            ],
            name="MacauIDRecognizer",
            context=[
                "macau", "澳門", "身份證", "bilhete", "id",
                "id no", "id number", "證件號碼", "證件編號", "編號",
            ],
        )
```

**Step 2: Run Macau ID tests to verify they pass**

Run: `uv run pytest tests/recognizers/test_identity.py -v --tb=short`
Expected: All tests PASS.

**Step 3: Commit**

```bash
git add src/pii_desensitizer/recognizers/identity.py
git commit -m "fix: Macau ID recognizer supports simplified 8-digit format and restricts first digit"
```

---

## Task 3: Add NER Punctuation Post-Filter (GREEN — Part 2)

**Files:**
- Modify: `src/pii_desensitizer/recognizers/person_ner.py`

**Step 1: Add the post-filter to `ChinesePersonRecognizer.analyze()`**

Replace the `analyze` method in `person_ner.py` (lines 57-97) with:

```python
    # Characters that should never appear in a real person name
    _PUNCTUATION_CHARS = set("()（）.,，。、；;：:！!？?「」『』\"'`'\"")

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

            # Filter false positives: real person names never contain punctuation
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
```

**Step 2: Run NER tests to verify they pass**

Run: `uv run pytest tests/recognizers/test_person_ner.py -v`
Expected: All tests PASS, including the new `test_filters_punctuation_false_positive`.

**Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS, no regressions.

**Step 4: Commit**

```bash
git add src/pii_desensitizer/recognizers/person_ner.py
git commit -m "fix: filter spaCy NER false positives containing punctuation characters"
```

---

## Task 4: Verify with Real-World Example

**Files:**
- Modify: `tests/test_integration.py`

**Step 1: Add integration test with the real-world example**

Add this test class to the end of `tests/test_integration.py`:

```python
class TestRealWorldExample:
    """Test with a real-world case that exposed three bugs:

    1. Macau ID (8-digit simplified format) was not detected
    2. spaCy NER false positive: ')未' tagged as PERSON
    3. Macau ID formal regex didn't restrict first digit
    """

    @pytest.fixture(scope="module")
    def analyzer(self):
        from pii_desensitizer.recognizers import build_analyzer
        return build_analyzer()

    @pytest.fixture
    def store(self):
        return RedisMappingStore(redis_client=FakeRedis(), ttl_seconds=3600)

    @pytest.fixture
    def desensitize_engine(self, analyzer, store):
        return DesensitizationEngine(analyzer=analyzer, store=store)

    @pytest.fixture
    def restore_engine(self, store):
        return RestoreEngine(store=store)

    def test_real_case_macau_ids_detected(self, desensitize_engine, restore_engine):
        original = (
            "市民親臨櫃枱為兒子申請刑事紀錄證明書，"
            "兒子電子身份識別工具(高級)未開啟，"
            "ID NO.: 11234567\n"
            "母親姓名:陳美\n"
            "聯絡電話:61234567\n"
            "ID NO.: 14567890\n"
            "兒子姓名: 李明"
        )
        system_id = "test_sys"

        d_result = desensitize_engine.desensitize(
            text=original, system_id=system_id, session_id=None
        )

        # Macau IDs should be replaced
        assert "11234567" not in d_result.text
        assert "14567890" not in d_result.text
        assert "{{MACAU_ID_" in d_result.text

        # Person names should be replaced
        assert "陳美" not in d_result.text
        assert "李明" not in d_result.text
        assert "{{PERSON_" in d_result.text

        # Phone should be replaced
        assert "61234567" not in d_result.text
        assert "{{PHONE_NUMBER_" in d_result.text

        # The false positive ')未' should NOT be replaced (no placeholder for it)
        assert "(高級)未" in d_result.text

        # Restore should bring back original values
        r_result = restore_engine.restore(
            text=d_result.text, system_id=system_id, session_id=d_result.session_id
        )
        assert "11234567" in r_result.text
        assert "14567890" in r_result.text
        assert "陳美" in r_result.text
        assert "李明" in r_result.text
        assert "61234567" in r_result.text
```

**Step 2: Run integration tests**

Run: `uv run pytest tests/test_integration.py -v`
Expected: All tests PASS.

**Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS.

**Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add real-world integration test for Macau ID + NER filter fixes"
```

---

## Verification Checklist

- [ ] `uv run pytest tests/recognizers/test_identity.py -v` — all Macau ID tests pass
- [ ] `uv run pytest tests/recognizers/test_person_ner.py -v` — NER filter tests pass
- [ ] `uv run pytest tests/test_integration.py -v` — real-world example passes
- [ ] `uv run pytest -v` — full suite passes, no regressions
- [ ] Macau ID `11234567` (simplified, no parens) is detected
- [ ] Macau ID `14567890` (simplified, no parens) is detected
- [ ] `)未` is NOT returned as PERSON
- [ ] Real names (陳美, 李明) are still detected
- [ ] Non-Macau-ID 8-digit numbers (28512345) are NOT matched as MACAU_ID
