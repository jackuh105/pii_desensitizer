# Low-Risk False Positive Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 7 of 10 failing test cases by addressing 4 low/zero-risk root causes in the PII desensitizer. Defers 3 medium-risk root causes (re.IGNORECASE override, context-aware number filtering) for separate review.

**Architecture:** Three of four fixes modify `EnglishPersonRecognizer` and `ChinesePersonRecognizer` in `person_ner.py` — expanding the existing CJK filter, adding an English stopword list, and adding pure-digit / Portuguese-address-prefix rejection. The fourth fix corrects a placeholder counting bug in the test runner `run_tests.py`. No new dependencies, no new files, no architecture changes.

**Tech Stack:** Python 3.12, Presidio, spaCy (en_core_web_sm + zh_core_web_sm), pytest, httpx (test runner)

---

## Root Cause Summary

| Root Cause | Risk | Cases Fixed | Task |
|---|---|---|---|
| F — Test script counts duplicate placeholders as FP | Zero | `desensitize_04`, `case_01` (partial) | Task 1 |
| B — CJK punctuation (U+3000–U+303F) not covered by CJK filter | Extremely low | `case_01` (partial) | Task 2 |
| A — spaCy NER tags English common words as PERSON | Low | `integration_01`, `desensitize_07`, `contact_20`, `temporal_01` (partial) | Task 3 |
| D — spaCy NER tags pure digits and Portuguese addresses as PERSON | Low | `case_08`, `address_12` | Task 4 |

### Deferred (medium risk, separate review)

| Root Cause | Risk | Cases | Reason |
|---|---|---|---|
| C — Presidio `re.IGNORECASE` makes `[A-Z]` match lowercase | Medium | `temporal_01` (partial) | Requires overriding `global_regex_flags` on multiple recognizers; broad blast radius |
| E — Number recognizers lack anti-context awareness | Medium | `contact_17`, `identity_11` | Requires negative-context heuristics; risk of false negatives on real PII |

### Expected Outcome After This Plan

| Case | Before | After | Notes |
|---|---|---|---|
| `desensitize_04` | FAIL (FP=1) | PASS | Task 1 fixes counting bug |
| `case_01` | FAIL (FP=3) | PASS | Task 1 removes 2 counting FPs, Task 2 removes `」` FP |
| `integration_01` | FAIL (FP=1) | PASS | Task 3 filters "for" |
| `desensitize_07` | FAIL (FP=1) | PASS | Task 3 filters "Email" |
| `contact_20` | FAIL (FP=1) | PASS | Task 3 filters "out" |
| `case_08` | FAIL (FP=1, FN=1) | PASS | Task 4 filters "66111111" as PERSON, leaving PHONE_NUMBER |
| `address_12` | FAIL (FP=1, FN=1) | PASS | Task 4 filters "Edifício Comercial Teste" as PERSON, leaving ADDRESS |
| `temporal_01` | FAIL (FP=3) | FAIL (FP=2→1) | Task 3 removes "Born" FP; license plate FP (root cause C) remains deferred |
| `contact_17` | FAIL (FP=2) | FAIL | Deferred (root cause E) |
| `identity_11` | FAIL (FP=2) | FAIL | Deferred (root cause E) |

**Net result: 7 cases fully fixed, 1 partially improved, 2 deferred.** Failing count drops from 10 → 3.

---

## Background

### Root Cause F: Test Script Counting Bug

`run_tests.py:1346` computes `extra_placeholders = max(0, total_placeholders - tp)`. The `total_placeholders` counts **all** placeholder occurrences in the desensitized text, including duplicates. When the same PII value appears twice in the input (e.g. `"Email john@test.com twice: john@test.com"`), both occurrences are replaced by the same `{{EMAIL_0}}`, producing 2 placeholder occurrences. The formula then counts the second occurrence as a false positive.

**Fix:** Count unique `(type, index)` pairs instead of raw occurrences.

### Root Cause B: CJK Punctuation Not Filtered

`EnglishPersonRecognizer` filters PERSON spans containing CJK characters via `_CJK_RE = re.compile(r"[\u4e00-\u9fff]")`. This range covers CJK Unified Ideographs but **not** CJK Symbols and Punctuation (U+3000–U+303F), which includes `「`」『』【】《》… — the corner brackets and quotation marks common in Chinese text. `en_core_web_sm` occasionally tags these as PERSON.

**Evidence:** `」` (U+300D) in `case_01` text `"為「澳門公共服務一戶通」"` was tagged PERSON by `en_core_web_sm`, producing `{{PERSON_2}}` in the output.

**Fix:** Expand the regex to `[\u3000-\u303f\u4e00-\u9fff]`.

### Root Cause A: spaCy NER Tags English Common Words as PERSON

Both `en_core_web_sm` and `zh_core_web_sm` occasionally tag common English words as PERSON when processing mixed-language or short texts.

**Evidence (via `analyzer.analyze()`):**

| Text | Word | Recognizer | Score |
|---|---|---|---|
| `Please contact john@example.com for details` | `for` | ChinesePersonRecognizer (zh NER) | 0.85 |
| `Email: alice@test.com` | `Email` | EnglishPersonRecognizer (en NER) | 0.85 |
| `Version 1.2.3 is out` | `out` | ChinesePersonRecognizer (zh NER) | 0.85 |
| `Born on 1990-01-15` | `Born` | ChinesePersonRecognizer (zh NER) | 0.85 |

**Key finding:** "for", "out", "Born" come from **ChinesePersonRecognizer** (zh_core_web_sm running on English text), NOT from EnglishPersonRecognizer. "Email" comes from EnglishPersonRecognizer. The stopword filter must be applied in **both** recognizers.

**Fix:** Add a frozenset of common English words that spaCy mislabels as PERSON. Filter any PERSON span that is a single ASCII-only word (no spaces) and appears in the stopword set (case-insensitive). Only filter single-word spans — multi-word spans like "John Smith" or "ALVES TESTE RODRIGUES" are never filtered.

### Root Cause D: spaCy NER Tags Digits and Portuguese Addresses as PERSON

`en_core_web_sm` tags pure digit strings and Portuguese building names as PERSON with score 0.85, which overrides the correct entity type (PHONE_NUMBER at 0.75, ADDRESS at 0.60) in Presidio's conflict resolution.

**Evidence:**

| Text | Span | Correct Type | Correct Score | PERSON Score | Result |
|---|---|---|---|---|---|
| `電話：66111111` | `66111111` | PHONE_NUMBER | 0.75 | 0.85 (en NER) | PERSON wins → type error |
| `Edifício Comercial Teste` | `Edifício Comercial Teste` | ADDRESS | 0.60 | 0.85 (en NER) | PERSON wins → type error |

**Fix:** Add two filters to `EnglishPersonRecognizer`:
1. **Pure digits filter:** Reject PERSON spans that are entirely digits/separators (digits are never person names).
2. **Portuguese address prefix filter:** Reject PERSON spans starting with known Portuguese building/street suffixes (Edifício, Centro, Jardins, etc.).

---

## Task 1: Fix Test Script Placeholder Counting Bug

**Root cause:** F (zero risk)

**Files:**
- Modify: `run_tests.py:1293-1297, 1343-1347`

**Step 1: Read the current `evaluate_case` function**

Verify lines 1293–1297 and 1343–1347 match the expected code:

```python
# Line 1293-1296
placeholders = extract_placeholders(desensitized_text)
placeholder_types = [pt for pt, _ in placeholders]
total_placeholders = len(placeholders)

# Line 1343-1347
# 4. Additional false positives:
#    extra_placeholders = max(0, total_placeholders - TP)
#    Add extra_placeholders to FP count
extra_placeholders = max(0, total_placeholders - tp)
fp += extra_placeholders
```

**Step 2: Fix `extra_placeholders` to use unique placeholders**

Replace lines 1293–1296:

```python
# 1. Extract all placeholders from desensitized text
placeholders = extract_placeholders(desensitized_text)
placeholder_types = [pt for pt, _ in placeholders]
total_placeholders = len(placeholders)
# Unique placeholder count: same PII value appearing multiple times
# in the text produces the same {{TYPE_N}} placeholder each time.
# Only count unique (type, index) pairs to avoid false FP.
unique_placeholders = len(set(placeholders))
```

Replace lines 1343–1347:

```python
# 4. Additional false positives:
#    extra_placeholders = unique placeholders not matched to a TP
#    Uses unique count so duplicate placeholders (same PII value
#    appearing multiple times) are not counted as false positives.
extra_placeholders = max(0, unique_placeholders - tp)
fp += extra_placeholders
```

**Step 3: Verify the fix manually**

Run the test script against the live server for the two affected cases:

```bash
# Start server if not running
uv run uvicorn pii_desensitizer.api.app:create_app --factory --reload &

# Run the full suite
uv run python run_tests.py --server-url http://localhost --port 8200 --api-key test-key-a-00000000
```

Expected: `desensitize_04` changes from FAIL to PASS. `case_01` FP count drops from 3 to 1 (the `」` FP remains until Task 2).

**Step 4: Run existing pytest suite to ensure no regressions**

```bash
uv run pytest tests/ -x -q
```

Expected: all 144 tests pass (run_tests.py is not part of pytest).

**Step 5: Commit**

```bash
git add run_tests.py
git commit -m "fix: count unique placeholders in test runner to avoid false FP on duplicate PII"
```

---

## Task 2: Expand CJK Punctuation Filter in EnglishPersonRecognizer

**Root cause:** B (extremely low risk)

**Files:**
- Modify: `src/pii_desensitizer/recognizers/person_ner.py:60`
- Test: `tests/recognizers/test_person_ner.py` (add test to `TestEnglishPersonRecognizerCJKFilter`)

**Step 1: Write the failing test**

Add to `tests/recognizers/test_person_ner.py`, inside `TestEnglishPersonRecognizerCJKFilter` class (after `test_no_cjk_person_on_chinese_text`):

```python
def test_filters_cjk_punctuation_false_positive(self):
    """CJK punctuation (corner brackets, etc.) tagged as PERSON by
    en_core_web_sm should be filtered out.

    U+3000-U+303F (CJK Symbols and Punctuation) includes 「」『』 which
    en_core_web_sm occasionally tags as PERSON. These are not covered by
    the basic CJK ideograph range (U+4E00-U+9FFF).
    """
    import spacy
    from presidio_analyzer.nlp_engine import NlpArtifacts

    nlp = spacy.load("en_core_web_sm")
    rec = EnglishPersonRecognizer()
    # Text where en_core_web_sm tags 」 (U+300D) as PERSON
    text = "為「澳門公共服務一戶通」"
    doc = nlp(text)
    artifacts = NlpArtifacts(
        entities=doc.ents,
        tokens=doc,
        tokens_indices=[t.idx for t in doc],
        lemmas=[t.lemma_ for t in doc],
        nlp_engine=None,
        language="en",
    )
    results = rec.analyze(
        text=text, entities=["PERSON"], nlp_artifacts=artifacts
    )
    # No PERSON results should remain — 」 is CJK punctuation, not a name
    person_spans = [text[r.start:r.end] for r in results]
    assert "」" not in person_spans
    assert "「" not in person_spans
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/recognizers/test_person_ner.py::TestEnglishPersonRecognizerCJKFilter::test_filters_cjk_punctuation_false_positive -v
```

Expected: FAIL — `」` appears in `person_spans` because the current `_CJK_RE` does not cover U+3000–U+303F.

**Step 3: Expand the CJK regex range**

In `src/pii_desensitizer/recognizers/person_ner.py`, line 60, change:

```python
    _CJK_RE = re.compile(r"[\u4e00-\u9fff]")
```

to:

```python
    _CJK_RE = re.compile(r"[\u3000-\u303f\u4e00-\u9fff]")
```

This adds the CJK Symbols and Punctuation block (U+3000–U+303F) which includes:
- U+3000–U+3003: Ideographic spaces and commas
- U+3008–U+300F: Angle brackets `〈〉《》「」『』`
- U+3010–U+3017: Brackets `【】〒〓`
- U+301C–U+301F: Wave dash and reverse corner brackets

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/recognizers/test_person_ner.py::TestEnglishPersonRecognizerCJKFilter -v
```

Expected: both `test_no_cjk_person_on_chinese_text` and `test_filters_cjk_punctuation_false_positive` PASS.

**Step 5: Run full test suite**

```bash
uv run pytest tests/ -x -q
```

Expected: all 145 tests pass (144 existing + 1 new).

**Step 6: Commit**

```bash
git add src/pii_desensitizer/recognizers/person_ner.py tests/recognizers/test_person_ner.py
git commit -m "fix: expand CJK filter to include CJK punctuation (U+3000-U+303F)"
```

---

## Task 3: Add English Stopword Filter to Both Person Recognizers

**Root cause:** A (low risk)

**Files:**
- Modify: `src/pii_desensitizer/recognizers/person_ner.py` — add stopword set, filter in both `EnglishPersonRecognizer.analyze()` and `ChinesePersonRecognizer.analyze()`
- Test: `tests/recognizers/test_person_ner.py` — add tests to `TestEnglishPersonRecognizerCJKFilter` and `TestChinesePersonRecognizer`

**Step 1: Write failing tests for EnglishPersonRecognizer stopword filter**

Add to `tests/recognizers/test_person_ner.py`, inside `TestEnglishPersonRecognizerCJKFilter`:

```python
def test_filters_english_stopword_false_positive(self):
    """en_core_web_sm tags 'Email' as PERSON in 'Email: alice@test.com'.
    Common English words should be filtered out.
    """
    import spacy
    from presidio_analyzer.nlp_engine import NlpArtifacts

    nlp = spacy.load("en_core_web_sm")
    rec = EnglishPersonRecognizer()
    text = "Email: alice@test.com"
    doc = nlp(text)
    artifacts = NlpArtifacts(
        entities=doc.ents,
        tokens=doc,
        tokens_indices=[t.idx for t in doc],
        lemmas=[t.lemma_ for t in doc],
        nlp_engine=None,
        language="en",
    )
    results = rec.analyze(
        text=text, entities=["PERSON"], nlp_artifacts=artifacts
    )
    person_spans = [text[r.start:r.end] for r in results]
    assert "Email" not in person_spans
```

**Step 2: Write failing tests for ChinesePersonRecognizer stopword filter**

Add to `tests/recognizers/test_person_ner.py`, inside `TestChinesePersonRecognizer` (after existing tests, before `TestChinesePersonRecognizerContextFallback`):

```python
def test_filters_zh_ner_english_stopword_false_positive(self, recognizer):
    """zh_core_web_sm tags English common words as PERSON when processing
    English text. These should be filtered out.

    All test words are common English words, never person names.
    """
    test_cases = [
        ("Please contact john@example.com for details", "for"),
        ("Version 1.2.3 is out", "out"),
        ("Born on 1990-01-15", "Born"),
    ]
    for text, stopword in test_cases:
        results = recognizer.analyze(
            text=text, entities=["PERSON"], nlp_artifacts=None
        )
        person_spans = [text[r.start:r.end] for r in results]
        assert stopword not in person_spans, (
            f"Expected '{stopword}' to be filtered, but it appears in "
            f"PERSON results: {person_spans}"
        )
```

**Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/recognizers/test_person_ner.py::TestEnglishPersonRecognizerCJKFilter::test_filters_english_stopword_false_positive tests/recognizers/test_person_ner.py::TestChinesePersonRecognizer::test_filters_zh_ner_english_stopword_false_positive -v
```

Expected: both FAIL — "Email" and "for"/"out"/"Born" appear in PERSON results.

**Step 4: Add stopword set as module-level constant**

In `src/pii_desensitizer/recognizers/person_ner.py`, after the existing `_CJK_NAME` constant (around line 92), add:

```python
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
```

**Step 5: Add stopword filter to EnglishPersonRecognizer**

In `src/pii_desensitizer/recognizers/person_ner.py`, modify `EnglishPersonRecognizer.analyze()` (around line 69–83). Add a `_is_stopword` helper method and call it in the filter:

```python
class EnglishPersonRecognizer(SpacyRecognizer):
    """Wraps SpacyRecognizer to filter CJK from PERSON results.
    ...
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
                )
            )
        ]
```

**Step 6: Add stopword filter to ChinesePersonRecognizer**

In `src/pii_desensitizer/recognizers/person_ner.py`, modify `ChinesePersonRecognizer.analyze()`. After the NER loop (around line 166) and before the context fallback loop (around line 168), add a stopword filter. Reuse the same `_is_stopword` static method:

In the `ChinesePersonRecognizer` class, add a reference to the shared filter:

```python
class ChinesePersonRecognizer(EntityRecognizer):
    """Detect Chinese person names using spaCy zh_core_web_sm NER + context fallback.
    ...
    """

    _PUNCTUATION_CHARS = set("()（）.,，。、；;：:！!？?「」『』\"'`'\"")

    # Reuse the stopword filter from EnglishPersonRecognizer
    _is_stopword = staticmethod(EnglishPersonRecognizer._is_stopword)

    def __init__(self) -> None:
        ...
```

Then in the `analyze()` method, after building `results` from NER (line 166) and before the context fallback loop (line 168), add:

```python
        # Filter English common words that zh_core_web_sm mislabels as PERSON
        # when processing English text (e.g. "for", "out", "Born")
        results = [
            r for r in results
            if not self._is_stopword(text[r.start:r.end])
        ]
```

The full `analyze()` method should look like:

```python
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
```

**Step 7: Run tests to verify they pass**

```bash
uv run pytest tests/recognizers/test_person_ner.py::TestEnglishPersonRecognizerCJKFilter::test_filters_english_stopword_false_positive tests/recognizers/test_person_ner.py::TestChinesePersonRecognizer::test_filters_zh_ner_english_stopword_false_positive -v
```

Expected: both PASS.

**Step 8: Run full test suite to check for regressions**

```bash
uv run pytest tests/ -x -q
```

Expected: all 147 tests pass (145 existing + 2 new). Verify that real person names (John, 陳大文, ALVES TESTE RODRIGUES, João da Silva Teste) are still detected — these are multi-word or non-ASCII, so they bypass the stopword filter.

**Step 9: Commit**

```bash
git add src/pii_desensitizer/recognizers/person_ner.py tests/recognizers/test_person_ner.py
git commit -m "fix: filter English common words mislabeled as PERSON by spaCy NER"
```

---

## Task 4: Add Pure Digits and Portuguese Address Prefix Filter

**Root cause:** D (low risk)

**Files:**
- Modify: `src/pii_desensitizer/recognizers/person_ner.py` — add digit/address regex filters to `EnglishPersonRecognizer`
- Test: `tests/recognizers/test_person_ner.py` — add tests to `TestEnglishPersonRecognizerCJKFilter`

**Step 1: Write failing tests**

Add to `tests/recognizers/test_person_ner.py`, inside `TestEnglishPersonRecognizerCJKFilter`:

```python
def test_filters_pure_digit_person_false_positive(self):
    """en_core_web_sm tags digit strings as PERSON (e.g. phone numbers).
    Pure digits are never person names and should be filtered.
    """
    import spacy
    from presidio_analyzer.nlp_engine import NlpArtifacts

    nlp = spacy.load("en_core_web_sm")
    rec = EnglishPersonRecognizer()
    # Text where en_core_web_sm tags 66111111 as PERSON
    text = "姓名：陳測試\nID：50111111\n電話：66111111"
    doc = nlp(text)
    artifacts = NlpArtifacts(
        entities=doc.ents,
        tokens=doc,
        tokens_indices=[t.idx for t in doc],
        lemmas=[t.lemma_ for t in doc],
        nlp_engine=None,
        language="en",
    )
    results = rec.analyze(
        text=text, entities=["PERSON"], nlp_artifacts=artifacts
    )
    person_spans = [text[r.start:r.end] for r in results]
    # 66111111 should not appear as PERSON (it's a phone number)
    digit_spans = [s for s in person_spans if s.isdigit()]
    assert len(digit_spans) == 0, (
        f"Expected no digit-only PERSON spans, but found: {digit_spans}"
    )


def test_filters_portuguese_address_prefix_false_positive(self):
    """en_core_web_sm tags Portuguese building names as PERSON.
    Spans starting with Portuguese building/street suffixes are addresses,
    not person names, and should be filtered.
    """
    import spacy
    from presidio_analyzer.nlp_engine import NlpArtifacts

    nlp = spacy.load("en_core_web_sm")
    rec = EnglishPersonRecognizer()
    text = "Edifício Comercial Teste"
    doc = nlp(text)
    artifacts = NlpArtifacts(
        entities=doc.ents,
        tokens=doc,
        tokens_indices=[t.idx for t in doc],
        lemmas=[t.lemma_ for t in doc],
        nlp_engine=None,
        language="en",
    )
    results = rec.analyze(
        text=text, entities=["PERSON"], nlp_artifacts=artifacts
    )
    person_spans = [text[r.start:r.end] for r in results]
    # "Edifício Comercial Teste" is an address, not a person name
    assert "Edifício Comercial Teste" not in person_spans
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/recognizers/test_person_ner.py::TestEnglishPersonRecognizerCJKFilter::test_filters_pure_digit_person_false_positive tests/recognizers/test_person_ner.py::TestEnglishPersonRecognizerCJKFilter::test_filters_portuguese_address_prefix_false_positive -v
```

Expected: both FAIL — digit strings and "Edifício Comercial Teste" appear in PERSON results.

**Step 3: Add filter regexes and update EnglishPersonRecognizer.analyze()**

In `src/pii_desensitizer/recognizers/person_ner.py`, after the `_PERSON_STOPWORDS` constant added in Task 3, add:

```python
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
```

Then update `EnglishPersonRecognizer.analyze()` to add the new filters:

```python
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
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/recognizers/test_person_ner.py::TestEnglishPersonRecognizerCJKFilter -v
```

Expected: all tests in the class pass, including the two new ones.

**Step 5: Run full test suite**

```bash
uv run pytest tests/ -x -q
```

Expected: all 149 tests pass (147 existing + 2 new).

**Step 6: Commit**

```bash
git add src/pii_desensitizer/recognizers/person_ner.py tests/recognizers/test_person_ner.py
git commit -m "fix: filter pure-digit and Portuguese-address-prefix PERSON false positives"
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
# Ensure server is running on port 8200 with .env API key
uv run python run_tests.py --server-url http://localhost --port 8200 --api-key test-key-a-00000000
```

Expected outcome:

| Case | Before | After |
|---|---|---|
| `desensitize_04` | FAIL | PASS |
| `case_01` | FAIL (FP=3) | PASS |
| `integration_01` | FAIL | PASS |
| `desensitize_07` | FAIL | PASS |
| `contact_20` | FAIL | PASS |
| `case_08` | FAIL (FP=1, FN=1) | PASS |
| `address_12` | FAIL (FP=1, FN=1) | PASS |
| `temporal_01` | FAIL (FP=3) | FAIL (FP=2) — "Born" fixed, license plate FP deferred |
| `contact_17` | FAIL | FAIL — deferred |
| `identity_11` | FAIL | FAIL — deferred |

Total: **7 cases fixed**, 3 remaining (2 deferred medium-risk, 1 partially improved).

**Step 3: Verify no real PII in test data**

```bash
# Ensure no real names/IDs/phones were added to test cases
grep -rn "real_name_pattern\|real_id_pattern" tests/ docs/plans/
```

Expected: no matches — all test data uses synthetic tokens (施例男, 陳例華, ALVES TESTE RODRIGUES, TESTE SILVA, João da Silva Teste, Pedro dos Santos Exemplo, Exemplo, Teste, etc.).

---

## Constraints

- **NEVER ADD REAL DATA TO TEST CASE** — all test names use synthetic tokens
- All test data uses: `陳大文`, `施例男`, `蔡測試`, `陳測試`, `ALVES TESTE RODRIGUES`, `João da Silva Teste`, `Pedro dos Santos Exemplo`, `TESTE SILVA`, `Exemplo`, `Teste`, and numeric placeholders (`11111111`, `61111111`, `50111111`, `66111111`, `28512345`, `74111111`)
- Use `uv` for all Python commands
- Write a detailed plan before implementing (this document)
- Follow TDD: write failing test → verify it fails → implement → verify it passes → commit
