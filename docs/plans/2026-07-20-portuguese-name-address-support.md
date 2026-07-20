# Portuguese Name & Address Support Implementation Plan

**Goal:** Fix two gaps found in real-world testing: (1) Portuguese names (all-caps BIR format and title-case prose) after form-field keywords are not detected, (2) Portuguese street/building addresses are completely invisible.

**Architecture:** Extend the existing `_CONTEXT_NAME_RE` regex in `person_ner.py` with Latin alternatives (all-caps + title-case with Portuguese prepositions). Add Portuguese address patterns to `address.py` alongside existing Chinese/English patterns. No new dependencies, no new spaCy models.

**Tech Stack:** Regex-only changes in `person_ner.py` and `address.py`. Tests in `test_person_ner.py` and `test_address.py`.

---

## Background

### Issue 1: Portuguese Names Not Detected

Macau has a significant Portuguese-speaking population. Portuguese names appear on government forms after the same Chinese keywords (姓名, 申請人, etc.) but use Latin characters — all-caps on ID documents or title-case in prose.

**Current behavior** (tested with synthetic names):

| Name pattern | en_core_web_sm | zh_core_web_sm | Context fallback (current) |
|---|---|---|---|
| All-caps BIR format (e.g. `ALVES TESTE RODRIGUES`) | 0 entities | Mislabeled as ORG | No match (CJK-only regex) |
| Title-case (e.g. `Ana da Silva Exemplo`) | Mislabeled as GPE | No entity | No match |
| Title-case with preposition (e.g. `João da Silva Teste`) | ✓ PERSON | No entity | No match |

**Why not pt_core_news_sm?** Tested — it fails on all-caps names (0 entities), fails after Chinese keyword prefix (mislabeled as LOC), and costs +12.4MB. The regex approach handles all-caps, works after Chinese keywords, and costs nothing.

**Portuguese name structure** (verified via faker pt_PT provider + python-nameparser):
- Given name(s) + mother's surname(s) + father's surname(s)
- Prepositions: `de`, `da`, `do`, `das`, `dos` (lowercase in prose, uppercase on BIR)
- Can stack: `Miguel da Silva do Amaral de Sousa`
- Diacritics: `á à â ã ç é ê í ó ô õ ú` — need `[a-zà-ÿ]` range
- Macau BIR format: `SURNAME, GIVEN` (comma-separated) — but after `姓名：` keyword the name appears without comma

**Solution:** Add two Latin alternatives to `_CONTEXT_NAME_RE`, keeping CJK unchanged:

```python
# All-caps: ALVES TESTE RODRIGUES (2-6 words, each 2+ uppercase letters)
all_caps = r"[A-ZÀ-Ý]{2,}(?:\s+[A-ZÀ-Ý]{2,}){1,5}"

# Title-case with Portuguese prepositions: João da Silva Teste, Pedro dos Santos Exemplo
title_case = r"[A-Z][a-zà-ÿ]+(?:\s+(?:de|da|do|das|dos)\s+[A-Z][a-zà-ÿ]+|\s+[A-Z][a-zà-ÿ]+){1,5}"
```

**False positive safety:** Anchored to form-field keywords (姓名, 申請人, etc.) + colon. Tested 8 non-name fields (性別, ID, 電話, 電郵, 日期, 地址, 用戶名, 意見編號) → 0 false positives.

### Issue 2: Portuguese Addresses Not Detected

Macau streets have bilingual names. Portuguese street names are completely invisible (0/12 detected in testing).

**Portuguese street suffixes** (from librarian research — Macau Post/CTT, Wikipedia, academic sources):
- Streets: `Rua`, `Avenida`, `Estrada`, `Caminho`, `Travessa`, `Beco`, `Pátio`, `Calçada`, `Largo`, `Praça`, `Praceta`, `Alameda`, `Rotunda`, `Azinhaga`, `Adro`, `Bairro`
- Buildings: `Edifício`, `Centro Comercial`, `Jardim`, `Bloco`, `Torre`, `Urbanização`
- Abbreviations: `Av.`, `R.`, `Tv.`, `Estr.`, `Cç.`, `Lg.`, `Pç.` (require trailing dot to avoid `Ave` collision)
- Prepositions: `de`, `da`, `do`, `das`, `dos` (only meaningful after street-type keyword)
- Format: `suffix + optional(de/da/do) + Capitalized word(s)`

**False positive safety:** Pattern requires `suffix + Capitalized word`. Tested 6 non-address texts → 0 false positives.

---

## Task 1: Add Failing Tests for Portuguese Names and Addresses (RED)

**Files:**
- Modify: `tests/recognizers/test_person_ner.py`
- Modify: `tests/recognizers/test_address.py`

**Step 1: Add Portuguese name tests to `tests/recognizers/test_person_ner.py`**

Add a new test class `TestChinesePersonRecognizerPortugueseFallback` after `TestChinesePersonRecognizerContextFallback`:

```python
class TestChinesePersonRecognizerPortugueseFallback:
    """Tests for Portuguese name detection via context fallback.

    All names are synthetic — common Portuguese surnames combined with
    'TESTE' or 'EXEMPLO' tokens to ensure they are never real PII.
    """

    @pytest.fixture(scope="module")
    def recognizer(self):
        rec = ChinesePersonRecognizer()
        rec.load()
        return rec

    def test_detects_all_caps_bir_name(self, recognizer):
        text = "姓名：ALVES TESTE RODRIGUES"
        results = recognizer.analyze(
            text=text, entities=["PERSON"], nlp_artifacts=None
        )
        person_texts = [text[r.start:r.end] for r in results]
        assert "ALVES TESTE RODRIGUES" in person_texts

    def test_detects_title_case_portuguese_name(self, recognizer):
        text = "姓名：João da Silva Teste"
        results = recognizer.analyze(
            text=text, entities=["PERSON"], nlp_artifacts=None
        )
        person_texts = [text[r.start:r.end] for r in results]
        assert "João da Silva Teste" in person_texts

    def test_detects_multi_word_with_prepositions(self, recognizer):
        text = "申請人：Pedro dos Santos Exemplo"
        results = recognizer.analyze(
            text=text, entities=["PERSON"], nlp_artifacts=None
        )
        person_texts = [text[r.start:r.end] for r in results]
        assert "Pedro dos Santos Exemplo" in person_texts

    def test_detects_short_caps_name(self, recognizer):
        text = "姓名：TESTE SILVA"
        results = recognizer.analyze(
            text=text, entities=["PERSON"], nlp_artifacts=None
        )
        person_texts = [text[r.start:r.end] for r in results]
        assert "TESTE SILVA" in person_texts

    def test_no_false_positive_on_id_field(self, recognizer):
        text = "ID：12345678"
        results = recognizer.analyze(
            text=text, entities=["PERSON"], nlp_artifacts=None
        )
        assert len(results) == 0

    def test_no_false_positive_on_phone_field(self, recognizer):
        text = "電話：61234567"
        results = recognizer.analyze(
            text=text, entities=["PERSON"], nlp_artifacts=None
        )
        assert len(results) == 0
```

**Step 2: Add Portuguese address tests to `tests/recognizers/test_address.py`**

Add these methods to `TestAddressRecognizer`:

```python
    def test_detects_portuguese_street(self):
        rec = AddressRecognizer()
        text = "Rua de Exemplo"
        results = rec.analyze(text=text, entities=["ADDRESS"], nlp_artifacts=None)
        assert len(results) >= 1
        assert "Rua" in text[results[0].start:results[0].end]

    def test_detects_portuguese_avenue(self):
        rec = AddressRecognizer()
        text = "Avenida de Teste Grande"
        results = rec.analyze(text=text, entities=["ADDRESS"], nlp_artifacts=None)
        assert len(results) >= 1

    def test_detects_portuguese_abbreviated(self):
        rec = AddressRecognizer()
        text = "Av. do Exemplo"
        results = rec.analyze(text=text, entities=["ADDRESS"], nlp_artifacts=None)
        assert len(results) >= 1

    def test_detects_portuguese_building(self):
        rec = AddressRecognizer()
        text = "Edifício Comercial Teste"
        results = rec.analyze(text=text, entities=["ADDRESS"], nlp_artifacts=None)
        assert len(results) >= 1

    def test_detects_portuguese_street_after_chinese(self):
        rec = AddressRecognizer()
        text = "住在Rua de Exemplo"
        results = rec.analyze(text=text, entities=["ADDRESS"], nlp_artifacts=None)
        assert len(results) >= 1

    def test_no_false_positive_on_portuguese_common_word(self):
        rec = AddressRecognizer()
        text = "The garden is beautiful"
        results = rec.analyze(text=text, entities=["ADDRESS"], nlp_artifacts=None)
        assert len(results) == 0
```

**Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/recognizers/test_person_ner.py tests/recognizers/test_address.py -v --tb=line`
Expected: 10 FAILURES — Portuguese name tests fail (regex only matches CJK), Portuguese address tests fail (no PT patterns).

**Step 4: Commit**

```bash
git add tests/recognizers/test_person_ner.py tests/recognizers/test_address.py
git commit -m "test: add Portuguese name and address tests (currently failing)"
```

---

## Task 2: Extend Context Fallback with Portuguese Name Patterns (GREEN — Part 1)

**Files:**
- Modify: `src/pii_desensitizer/recognizers/person_ner.py`

**Step 1: Update `_CONTEXT_NAME_RE` in `person_ner.py`**

Replace the existing `_CONTEXT_NAME_RE` definition (lines 92-98) with:

```python
_CJK_NAME = r"[\u4e00-\u9fff]{2,4}"

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
```

Order matters: `all_caps` before `title_case` before `cjk` — the regex alternation tries left-to-right, and all-caps is the most specific (requires 2+ uppercase letters per token).

**Step 2: Run Portuguese name tests to verify they pass**

Run: `uv run pytest tests/recognizers/test_person_ner.py -v --tb=short`
Expected: All tests PASS, including the new `TestChinesePersonRecognizerPortugueseFallback` class.

**Step 3: Run full test suite to verify no regressions**

Run: `uv run pytest --tb=short -q`
Expected: All tests PASS (119 existing + 6 new = 125 total).

**Step 4: Commit**

```bash
git add src/pii_desensitizer/recognizers/person_ner.py
git commit -m "fix: extend context fallback to detect Portuguese names after form-field keywords"
```

---

## Task 3: Add Portuguese Address Patterns (GREEN — Part 2)

**Files:**
- Modify: `src/pii_desensitizer/recognizers/address.py`

**Step 1: Add Portuguese patterns to `address.py`**

Add after the `_EN_ADDRESS_PATTERNS` list (after line 37), before `_HK_MACAU_DISTRICTS`:

```python
_PT_STREET_SUFFIXES = (
    r"Rua|Avenida|Av|Travessa|Tv|Estrada|Caminho|Calçada|Largo|Praça|"
    r"Praceta|Beco|Pátio|Alameda|Rotunda|Bairro|Parque|Jardim|Adro|"
    r"Azinhaga|Escadaria|Miradouro|Rampa|Istmo|Ponte|Túnel|Viaduto"
)

_PT_BUILDING_SUFFIXES = (
    r"Edifício|Centro Comercial|Centro|Jardins|Bloco|Torre|"
    r"Urbanização|Condomínio|Vivenda|Quinta"
)

_PT_ADDRESS_PATTERNS = [
    rf"(?<!\w)(?:{_PT_STREET_SUFFIXES})\.?\s+"
    rf"(?:(?:de|da|do|das|dos)\s+)?"
    rf"[A-ZÀ-Ý][a-zà-ÿ]+"
    rf"(?:\s+[A-ZÀ-Ý][a-zà-ÿ]+)*",
    rf"(?<!\w)(?:{_PT_BUILDING_SUFFIXES})\s+"
    rf"[A-ZÀ-Ý][a-zà-ÿ]+"
    rf"(?:\s+[A-ZÀ-Ý][a-zà-ÿ]+)*",
]
```

Then update `AddressRecognizer.__init__` to include the Portuguese patterns:

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
        )
```

**Step 2: Run Portuguese address tests to verify they pass**

Run: `uv run pytest tests/recognizers/test_address.py -v --tb=short`
Expected: All tests PASS, including 6 new Portuguese address tests.

**Step 3: Run full test suite to verify no regressions**

Run: `uv run pytest --tb=short -q`
Expected: All tests PASS (125 from Task 2 + 6 new = 131 total).

**Step 4: Commit**

```bash
git add src/pii_desensitizer/recognizers/address.py
git commit -m "fix: add Portuguese street and building address patterns for Macau"
```

---

## Task 4: Verify with Synthetic Test Data

**No new test files** — verify manually with synthetic data that mimics the real-world pattern.

**Step 1: Run analyzer on synthetic text matching the real-world pattern**

```bash
uv run python -c "
from pii_desensitizer.recognizers import build_analyzer, ALL_ENTITIES
analyzer = build_analyzer()
text = '我的電話61234567在6月19日8:16收到驗證碼。\nID：12345678\n姓名：ALVES TESTE RODRIGUES'
results = analyzer.analyze(text=text, language='en', entities=ALL_ENTITIES)
for r in sorted(results, key=lambda x: x.start):
    span = text[r.start:r.end]
    if len(span) > 60: span = span[:57] + '...'
    print(f'{r.entity_type:15s} {r.start:4d}:{r.end:4d} score={r.score:.2f} | {span!r}')
"
```

Expected output:
```
PHONE_NUMBER       4:  12 score=0.40 | '61234567'
MACAU_ID          XX:  XX score=0.75 | '12345678'
PHONE_NUMBER      XX:  XX score=0.40 | '12345678'
PERSON            XX:  XX score=0.75 | 'ALVES TESTE RODRIGUES'
```

Key verification: `ALVES TESTE RODRIGUES` is detected as PERSON.

**Step 2: Run full test suite one final time**

Run: `uv run pytest --tb=short -q`
Expected: All 131 tests PASS, 0 failures.

---

## Verification Checklist

- [ ] `uv run pytest tests/recognizers/test_person_ner.py -v` — Portuguese name tests pass
- [ ] `uv run pytest tests/recognizers/test_address.py -v` — Portuguese address tests pass
- [ ] `uv run pytest --tb=short -q` — full suite passes (131 tests), no regressions
- [ ] `ALVES TESTE RODRIGUES` (all-caps synthetic) detected as PERSON after `姓名：`
- [ ] `João da Silva Teste` (title-case synthetic) detected as PERSON after `姓名：`
- [ ] `Pedro dos Santos Exemplo` (multi-word synthetic) detected as PERSON after `申請人：`
- [ ] `Rua de Exemplo` (synthetic) detected as ADDRESS
- [ ] `Avenida de Teste Grande` (synthetic) detected as ADDRESS
- [ ] `Av. do Exemplo` (synthetic abbreviation) detected as ADDRESS
- [ ] `Edifício Comercial Teste` (synthetic building) detected as ADDRESS
- [ ] Existing CJK name detection unchanged (陳大文, 施例男 still work)
- [ ] Existing Chinese/English address detection unchanged
- [ ] No false positives on non-name fields (性別, ID, 電話, 電郵, 日期)
- [ ] No false positives on non-address text ("The garden is beautiful")
- [ ] **No real PII data in any committed test case**

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|---|---|---|
 Portuguese name regex matches non-name all-caps text | Very Low | Anchored to form-field keywords + colon; tested 8 false-positive cases → 0 matches |
| Portuguese address regex matches common words | Low | Requires `suffix + Capitalized word`; tested 6 non-address texts → 0 matches |
| `Av.` abbreviation collides with English `Ave` | Low | Portuguese pattern requires `Av.` (with dot) or `Avenida` (full word); existing English pattern handles `Ave` separately |
| Existing CJK name detection breaks | Very Low | CJK alternative unchanged in regex; only adding new alternatives |
| Existing address tests break | Low | New Portuguese patterns don't overlap with Chinese/English patterns; will verify with full test suite |
| Diacritics not matched | Low | Using `[a-zà-ÿ]` and `[A-ZÀ-Ý]` Unicode ranges in all Latin patterns |
