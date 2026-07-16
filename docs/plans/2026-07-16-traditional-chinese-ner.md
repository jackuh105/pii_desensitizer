# Traditional Chinese NER Support via OpenCC Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add OpenCC Traditional→Simplified conversion to `ChinesePersonRecognizer` so that Traditional Chinese (HK/Macau) person names are detected by the Simplified-trained spaCy model.

**Architecture:** In `ChinesePersonRecognizer.analyze()`, convert the input text from Traditional to Simplified Chinese using OpenCC before running spaCy NER. Because OpenCC is a 1:1 character mapping (string length is preserved), the character offsets from NER on the Simplified text are directly valid on the original Traditional text — no offset remapping needed. The AnonymizerEngine then slices the original Traditional text using those offsets, so the mapping table stores the original Traditional value, and restore returns Traditional text.

**Tech Stack:** `opencc-python-reimplemented` (pure Python, no C dependency), existing spaCy `zh_core_web_sm`

---

## Background: Why This Works

### The Problem

`zh_core_web_sm` is trained on Simplified Chinese (OntoNotes 5). Traditional Chinese person names like `陳大文` are mostly missed by NER (~20% recall). Simplified equivalents like `陈大文` are detected reliably (~100% recall).

### The Solution

OpenCC converts Traditional→Simplified character-by-character:

```
我是陳大文  →  我是陈大文   (length: 6 → 6, identical)
歐陽小姐    →  欧阳小姐     (length: 4 → 4, identical)
```

**OpenCC preserves string length 1:1 in all cases** (verified across 7 test cases including `頭髮→头发`, `吃著飯→吃著饭`). This means:

1. NER runs on the Simplified text and returns offsets `[start_char, end_char]`
2. These offsets are directly valid on the original Traditional text (same length)
3. Presidio's AnonymizerEngine slices the **original** `text` parameter (not the Simplified conversion) using those offsets
4. The mapping table stores `陳大文` (Traditional), not `陈大文` (Simplified)
5. Restore returns `陳大文` (Traditional)

### Data Flow

```
ChinesePersonRecognizer.analyze(text="我是陳大文")
  │
  ├── cc.convert("我是陳大文") → "我是陈大文"   (Simplified, same length)
  ├── nlp("我是陈大文") → NER detects "陈大文" at [2:5]
  └── return RecognizerResult(start=2, end=5)     ← offsets only, no text
        │
        ▼
AnonymizerEngine.anonymize(text="我是陳大文", analyzer_results=[{start:2, end:5}])
  │
  ├── text[2:5] = "陳大文"                        ← slices ORIGINAL Traditional text
  ├── PlaceholderOperator.operate(text="陳大文")
  │   └── mapping["PERSON_0"] = "陳大文"          ← stores Traditional
  └── output: "我是{{PERSON_0}}"
        │
        ▼
RestoreEngine.restore(text="我是{{PERSON_0}}")
  └── output: "我是陳大文"                        ← restores Traditional
```

### Verified Results

| Text (Traditional) | Before OpenCC | After OpenCC |
|---|---|---|
| 我是陳大文，請聯絡我 | ❌ Missed | ✅ `('陳大文', 2, 5)` |
| 請聯絡黃志偉先生 | ❌ Missed | ✅ `('黃志偉', 3, 6)` |
| 張偉、王芳、李強都是同事 | ⚠️ 2 of 3 | ✅ All 3 |
| John和陳大文開會 | ❌ Missed | ✅ Both John + 陳大文 |
| 歐陽小姐住在香港 | ❌ Missed | ❌ Still missed (compound surname limitation) |

### Remaining Limitations (not solvable by OpenCC)

- **Compound surnames** (歐陽, 司徒, 司馬): spaCy's segmenter mis-segmentates these even in Simplified form
- **Single-character names**: lack of context, NER confidence too low
- These are spaCy NER limitations, not Traditional/Simplified issues

---

## Task 1: Add OpenCC Dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add the dependency**

Run:
```bash
uv add opencc-python-reimplemented
```

**Step 2: Verify import works**

Run:
```bash
uv run python -c "from opencc import OpenCC; cc = OpenCC('t2s'); print(cc.convert('陳大文'))"
```

Expected output: `陈大文`

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add opencc-python-reimplemented for Traditional→Simplified conversion"
```

---

## Task 2: Update Tests to Assert Traditional Chinese Detection

**Files:**
- Modify: `tests/recognizers/test_person_ner.py`

The current tests are intentionally lenient (`assert len(results) >= 0`) because Traditional Chinese was known to fail. With OpenCC, Traditional Chinese should now be detected. We need to:

1. Replace the lenient assertions with real assertions that verify Traditional Chinese names are detected
2. Add tests that verify the offsets point to the **original Traditional text** (not the Simplified conversion)
3. Add a test that verifies the full desensitize→restore round-trip preserves Traditional Chinese

**Step 1: Replace the test file**

Replace the entire contents of `tests/recognizers/test_person_ner.py` with:

```python
# tests/recognizers/test_person_ner.py
"""Tests for Chinese person name recognizer with OpenCC Traditional→Simplified conversion."""

import pytest

from pii_desensitizer.recognizers.person_ner import ChinesePersonRecognizer


@pytest.fixture(scope="module")
def recognizer():
    """Shared recognizer instance (model loading is expensive)."""
    rec = ChinesePersonRecognizer()
    rec.load()
    return rec


class TestChinesePersonRecognizer:
    """Tests verifying Traditional Chinese person name detection via OpenCC conversion."""

    def test_detects_traditional_chinese_name(self, recognizer):
        """Traditional Chinese name '陳大文' should be detected after OpenCC conversion."""
        text = "我是陳大文，請聯絡我"
        results = recognizer.analyze(
            text=text,
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        assert len(results) >= 1
        person_text = text[results[0].start:results[0].end]
        assert person_text == "陳大文"

    def test_detects_traditional_chinese_name_with_context(self, recognizer):
        """Traditional Chinese name '黃志偉' should be detected even with surrounding text."""
        text = "請聯絡黃志偉先生"
        results = recognizer.analyze(
            text=text,
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        assert len(results) >= 1
        person_text = text[results[0].start:results[0].end]
        assert person_text == "黃志偉"

    def test_detects_multiple_traditional_chinese_names(self, recognizer):
        """Multiple Traditional Chinese names in one text should all be detected."""
        text = "張偉、王芳、李強都是同事"
        results = recognizer.analyze(
            text=text,
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        person_texts = [text[r.start:r.end] for r in results]
        assert "張偉" in person_texts
        assert "王芳" in person_texts
        assert "李強" in person_texts

    def test_detects_simplified_chinese_name(self, recognizer):
        """Simplified Chinese should still work (OpenCC is idempotent on Simplified input)."""
        text = "张三和李明在开会"
        results = recognizer.analyze(
            text=text,
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        assert len(results) >= 1
        person_texts = [text[r.start:r.end] for r in results]
        assert "张三" in person_texts

    def test_offsets_point_to_original_traditional_text(self, recognizer):
        """Offsets must be valid on the original Traditional text, not the Simplified conversion.

        This is the critical test: NER runs on Simplified text, but offsets must
        correctly slice the original Traditional text. If OpenCC changed string length,
        this test would fail.
        """
        text = "我是陳大文，請聯絡我"
        results = recognizer.analyze(
            text=text,
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        assert len(results) >= 1
        for r in results:
            assert 0 <= r.start < r.end <= len(text)
            sliced = text[r.start:r.end]
            assert len(sliced) == r.end - r.start
            # The sliced text must contain Traditional Chinese characters,
            # NOT the Simplified ones (proving we're slicing the original text)
            assert "陳" in sliced or "大" in sliced or "文" in sliced
            # Must NOT contain Simplified-only characters
            assert "陈" not in sliced

    def test_mixed_chinese_english_text(self, recognizer):
        """Mixed Chinese+English text should detect both Chinese and English names."""
        text = "John和陳大文開會"
        results = recognizer.analyze(
            text=text,
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        person_texts = [text[r.start:r.end] for r in results]
        assert "John" in person_texts
        assert "陳大文" in person_texts

    def test_results_have_correct_entity_type(self, recognizer):
        text = "王先生今天不在"
        results = recognizer.analyze(
            text=text,
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        for r in results:
            assert r.entity_type == "PERSON"

    def test_no_crash_on_empty_text(self, recognizer):
        results = recognizer.analyze(
            text="",
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        assert results == []

    def test_no_crash_on_english_only_text(self, recognizer):
        results = recognizer.analyze(
            text="Hello world, no names here",
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        assert isinstance(results, list)

    def test_no_crash_on_pure_simplified_text(self, recognizer):
        """OpenCC should be idempotent on already-Simplified text (no crash, no double-conversion)."""
        text = "张三来过"
        results = recognizer.analyze(
            text=text,
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        assert isinstance(results, list)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/recognizers/test_person_ner.py -v`

Expected: FAIL — `test_detects_traditional_chinese_name` and `test_detects_traditional_chinese_name_with_context` will fail because the current code has no OpenCC conversion. `test_detects_multiple_traditional_chinese_names` may also fail (張偉 is missed without conversion). `test_offsets_point_to_original_traditional_text` will fail because no results are returned.

**Step 3: Commit the failing tests**

```bash
git add tests/recognizers/test_person_ner.py
git commit -m "test: assert Traditional Chinese detection (currently failing, will pass after OpenCC)"
```

---

## Task 3: Add OpenCC Conversion to ChinesePersonRecognizer

**Files:**
- Modify: `src/pii_desensitizer/recognizers/person_ner.py`

**Step 1: Update the recognizer**

Replace the entire contents of `src/pii_desensitizer/recognizers/person_ner.py` with:

```python
# src/pii_desensitizer/recognizers/person_ner.py
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

    Converts Traditional Chinese to Simplified before NER for better recall
    on HK/Macau text. Offsets remain valid on the original text because
    OpenCC preserves string length (1:1 character mapping).
    """

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
        are valid on the original (Traditional) text.
        """
        if not self._nlp or not self._cc or not text.strip():
            return []

        if "PERSON" not in entities:
            return []

        # Convert Traditional → Simplified (1:1, preserves length)
        simplified_text = self._cc.convert(text)

        # Run NER on Simplified text
        doc = self._nlp(simplified_text)

        # Offsets are valid on the original text because OpenCC preserves length
        results: List[RecognizerResult] = []
        for ent in doc.ents:
            if ent.label_ == "PERSON":
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

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/recognizers/test_person_ner.py -v`

Expected: All tests PASS. Specifically:
- `test_detects_traditional_chinese_name` ✅ (was failing before)
- `test_detects_traditional_chinese_name_with_context` ✅ (was failing before)
- `test_detects_multiple_traditional_chinese_names` ✅ (was failing before)
- `test_offsets_point_to_original_traditional_text` ✅ (critical offset test)
- `test_mixed_chinese_english_text` ✅ (was failing before)

**Step 3: Run full test suite to verify no regressions**

Run: `uv run pytest -v`

Expected: All tests PASS (77 existing + any new tests, no regressions).

**Step 4: Commit**

```bash
git add src/pii_desensitizer/recognizers/person_ner.py
git commit -m "feat: add OpenCC Traditional→Simplified conversion for Chinese person name NER"
```

---

## Task 4: Add Integration Test for Traditional Chinese Round-Trip

**Files:**
- Modify: `tests/test_integration.py`

Add a test that verifies the full desensitize→restore cycle preserves Traditional Chinese text. This is the end-to-end proof that OpenCC integration works correctly: the desensitized text contains placeholders, the mapping stores Traditional Chinese values, and restore returns Traditional Chinese.

**Step 1: Add the test**

Add the following test class to the end of `tests/test_integration.py`:

```python
class TestTraditionalChineseRoundTrip:
    """Test that Traditional Chinese names survive the full desensitize→restore cycle.

    This verifies:
    1. Traditional Chinese names are detected (via OpenCC conversion)
    2. The mapping stores the original Traditional text (not Simplified)
    3. Restore returns the original Traditional text
    """

    def test_traditional_chinese_name_round_trip(self, desensitize_engine, restore_engine):
        original = "我是陳大文，請聯絡我"
        system_id = "test_sys"

        # 1. Desensitize
        d_result = desensitize_engine.desensitize(
            text=original, system_id=system_id, session_id=None
        )
        assert "陳大文" not in d_result.text
        assert "{{PERSON_0}}" in d_result.text or "{{PERSON_" in d_result.text

        # 2. Simulate LLM response with placeholder
        llm_response = d_result.text  # echo back

        # 3. Restore
        r_result = restore_engine.restore(
            text=llm_response, system_id=system_id, session_id=d_result.session_id
        )

        # 4. Restored text must contain Traditional Chinese (not Simplified)
        assert "陳大文" in r_result.text
        assert "陈大文" not in r_result.text  # Must NOT be Simplified

    def test_traditional_chinese_with_other_pii_round_trip(
        self, desensitize_engine, restore_engine
    ):
        original = "聯絡人黃志偉，HKID A123456(7)，email john@test.com"
        system_id = "test_sys"

        # 1. Desensitize
        d_result = desensitize_engine.desensitize(
            text=original, system_id=system_id, session_id=None
        )

        # Verify Traditional Chinese name was replaced
        assert "黃志偉" not in d_result.text
        assert "{{PERSON_" in d_result.text
        # Verify other PII was also replaced
        assert "A123456(7)" not in d_result.text
        assert "john@test.com" not in d_result.text

        # 2. Restore
        r_result = restore_engine.restore(
            text=d_result.text, system_id=system_id, session_id=d_result.session_id
        )

        # 3. All values restored, Traditional Chinese preserved
        assert "黃志偉" in r_result.text
        assert "黄志伟" not in r_result.text  # NOT Simplified
        assert "A123456(7)" in r_result.text
        assert "john@test.com" in r_result.text
```

**Step 2: Run integration tests to verify they pass**

Run: `uv run pytest tests/test_integration.py -v`

Expected: All integration tests PASS, including the 2 new Traditional Chinese round-trip tests.

**Step 3: Run full test suite**

Run: `uv run pytest -v`

Expected: All tests PASS, no regressions.

**Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add Traditional Chinese desensitize→restore round-trip integration tests"
```

---

## Task 5: Update README

**Files:**
- Modify: `README.md`

Update the Known Limitations section and Tech Stack to reflect OpenCC integration.

**Step 1: Update the Known Limitations section**

Find the current Known Limitations section:

```markdown
### Known Limitations

- **Traditional Chinese NER** — `zh_core_web_sm` is trained on Simplified Chinese (OntoNotes 5); Traditional Chinese (HK/Macau) has lower recall. Future: add OpenCC conversion.
- **Address detection** — heuristic keyword + regex; may miss non-standard addresses. Future: add LLM fallback.
- **Redis restart** — in-progress restore calls fail if Redis restarts (acceptable: LLM processing window is short).
```

Replace with:

```markdown
### Known Limitations

- **Compound surnames** — Chinese compound surnames (歐陽, 司徒, 司馬) may still be missed by NER even after OpenCC conversion; this is a spaCy segmenter limitation.
- **Address detection** — heuristic keyword + regex; may miss non-standard addresses. Future: add LLM fallback.
- **Redis restart** — in-progress restore calls fail if Redis restarts (acceptable: LLM processing window is short).
```

**Step 2: Update the Tech Stack section**

Find:

```markdown
## Tech Stack

- **Python 3.12** + **FastAPI** + **uvicorn**
- **Microsoft Presidio** (presidio-analyzer + presidio-anonymizer)
- **spaCy** (`en_core_web_sm` + `zh_core_web_sm`)
- **Redis 7** (in-memory, no persistence)
- **Docker Compose** for deployment
```

Replace with:

```markdown
## Tech Stack

- **Python 3.12** + **FastAPI** + **uvicorn**
- **Microsoft Presidio** (presidio-analyzer + presidio-anonymizer)
- **spaCy** (`en_core_web_sm` + `zh_core_web_sm`)
- **OpenCC** (`opencc-python-reimplemented`) — Traditional→Simplified conversion before Chinese NER
- **Redis 7** (in-memory, no persistence)
- **Docker Compose** for deployment
```

**Step 3: Commit**

```bash
git add README.md
git commit -m "docs: update README to reflect OpenCC Traditional Chinese support"
```

---

## Summary

| Task | What | Files | Tests |
|---|---|---|---|
| 1 | Add `opencc-python-reimplemented` dependency | `pyproject.toml` | Import check |
| 2 | Rewrite tests to assert Traditional Chinese detection | `tests/recognizers/test_person_ner.py` | 10 tests (was 6) |
| 3 | Add OpenCC conversion to `ChinesePersonRecognizer` | `src/pii_desensitizer/recognizers/person_ner.py` | All recognizer tests pass |
| 4 | Add Traditional Chinese round-trip integration tests | `tests/test_integration.py` | 2 new e2e tests |
| 5 | Update README limitations and tech stack | `README.md` | — |
