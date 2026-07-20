# tests/recognizers/test_address.py
"""Tests for address recognizer (heuristic)."""

from pii_desensitizer.recognizers.address import AddressRecognizer


class TestAddressRecognizer:
    def test_detects_chinese_address_with_street_keyword(self):
        rec = AddressRecognizer()
        text = "地址是中環德輔道中1號"
        results = rec.analyze(text=text, entities=["ADDRESS"], nlp_artifacts=None)
        assert len(results) >= 1
        assert "德輔道" in text[results[0].start:results[0].end]

    def test_detects_english_address_with_road_keyword(self):
        rec = AddressRecognizer()
        text = "Office at 1 Des Voeux Rd, Central"
        results = rec.analyze(text=text, entities=["ADDRESS"], nlp_artifacts=None)
        assert len(results) >= 1

    def test_detects_building_name(self):
        rec = AddressRecognizer()
        text = "住在太古城中心"
        results = rec.analyze(text=text, entities=["ADDRESS"], nlp_artifacts=None)
        assert len(results) >= 1

    def test_no_false_positive_on_common_text(self):
        rec = AddressRecognizer()
        text = "The road is long"
        results = rec.analyze(text=text, entities=["ADDRESS"], nlp_artifacts=None)
        assert len(results) == 0

    def test_no_false_positive_on_long_paragraph_with_platform(self):
        rec = AddressRecognizer()
        text = (
            "現時許多手機應用程式和網站均設有類似聯絡資訊欄，"
            "而「一戶通」作爲市民常用的服務平臺，亦應具備此功能，"
            "藉以整合各政府部門的聯絡資訊，為市民提供更便捷的服務。"
        )
        results = rec.analyze(text=text, entities=["ADDRESS"], nlp_artifacts=None)
        assert len(results) == 0

    def test_no_false_positive_on_platform_keyword(self):
        rec = AddressRecognizer()
        results = rec.analyze(
            text="此系統是一個線上服務平臺，提供市民查詢功能",
            entities=["ADDRESS"],
            nlp_artifacts=None,
        )
        assert len(results) == 0

    def test_detects_address_with_tai_and_number(self):
        rec = AddressRecognizer()
        text = "富裕臺8號"
        results = rec.analyze(text=text, entities=["ADDRESS"], nlp_artifacts=None)
        assert len(results) == 1
        assert "富裕臺" in text[results[0].start:results[0].end]

    def test_no_match_span_exceeds_15_chars(self):
        rec = AddressRecognizer()
        text = (
            "市民透過手機程式辦理部門服務時，往往需要即時聯絡相關部門，"
            "我建議在程式內增設通訊錄欄目，集中列出各部門公開聯絡資料，"
            "包括部門名稱、電話、電郵、地址、辦公時間及官方網站等信息。"
        )
        results = rec.analyze(text=text, entities=["ADDRESS"], nlp_artifacts=None)
        for r in results:
            span_len = r.end - r.start
            assert span_len <= 15, f"Match span {span_len} chars too long: {text[r.start:r.end]!r}"

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
        text = "This project is almost done"
        results = rec.analyze(text=text, entities=["ADDRESS"], nlp_artifacts=None)
        assert len(results) == 0
