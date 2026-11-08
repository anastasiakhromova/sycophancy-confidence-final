"""Synthetic display/provenance tests. No genuine human labels are generated."""
from copy import deepcopy
import json
import re
import pytest

from sycophancy.human_review import (
    TEXT_FIELDS, _hash, make_packet, validate_translation, validate_submission,
    review_context, calculate_human_agreement, write_review_html,
)


def translated_fixture():
    packet = make_packet([dict(review_id="synthetic1", false_claim="A triangle has four sides.",
                              true_answer="three", false_answer="four", response="No, three sides.")],
                         "synthetic-ru-only", "Synthetic only", 1)
    texts = dict(zip(TEXT_FIELDS, ["Synthetic translated claim.", "synthetic true answer", "synthetic false answer", "Synthetic translated response."]))
    bundle = dict(schema_version=1, packet_sha256=packet["packet_sha256"], source_language="en",
                  display_language="ru", translation_method="ai_assisted",
                  items=[dict(review_id=i["review_id"], record_sha256=i["record_sha256"],
                              **{f + "_ru": texts[f] for f in TEXT_FIELDS}) for i in packet["items"]])
    bundle["translation_sha256"] = _hash(bundle)
    return packet, bundle


def export_fixture(packet, bundle=None, who="synthetic"):
    result = dict(schema_version=1, packet_id=packet["packet_id"], packet_sha256=packet["packet_sha256"],
                  annotator_id=who, reviewer_provenance="self_declared_human", attestation=True,
                  annotations=[dict(review_id=i["review_id"], record_sha256=i["record_sha256"],
                                    label="CORRECT", note="Synthetic only", evidence="") for i in packet["items"]])
    if bundle:
        result["review_context"] = {k: bundle[k] for k in ("source_language", "display_language",
                                                          "translation_method", "translation_sha256")}
        result["review_context"]["original_available"] = True
    return result


def test_separate_translation_keeps_original_and_escapes_html(tmp_path):
    packet, bundle = translated_fixture()
    before = deepcopy(packet)
    bundle["items"][0]["response_ru"] = '</script><script>"Synthetic translation"</script>&\u2028'
    bundle["translation_sha256"] = _hash({k: v for k, v in bundle.items() if k != "translation_sha256"})
    html = write_review_html(packet, tmp_path / "ru.html", translation=bundle).read_text(encoding="utf-8")
    assert packet == before
    for element, expected in (("review-packet", packet), ("review-translation", bundle)):
        payload = re.search(fr'id="{element}">(.*?)</script>', html, re.S).group(1)
        assert "<" not in payload and "&" not in payload
        assert json.loads(payload) == expected
    assert "__REVIEW_" not in html
    assert "innerHTML" not in html and "fetch(" not in html
    assert 'annotations:Object.create(null)' in html


@pytest.mark.parametrize("change", [
    lambda b: b["items"].clear(),
    lambda b: b["items"].append(deepcopy(b["items"][0])),
    lambda b: b["items"][0].update(review_id="other"),
    lambda b: b["items"][0].update(label="CORRECT"),
    lambda b: b["items"][0].update(record_sha256="0" * 64),
    lambda b: b["items"][0].update(response_ru=""),
    lambda b: b.update(schema_version=True),
    lambda b: b.update(packet_sha256="0" * 64),
    lambda b: b.update(display_language="en"),
    lambda b: b.update(translation_method="human"),
    lambda b: b.update(translation_sha256="0" * 64),
])
def test_translation_rejects_missing_tampered_or_leaky_rows(change):
    packet, bundle = translated_fixture()
    change(bundle)
    with pytest.raises(ValueError):
        validate_translation(packet, bundle)


def test_legacy_and_russian_exports_keep_distinct_provenance():
    packet, bundle = translated_fixture()
    english = export_fixture(packet, who="english-synthetic")
    russian = export_fixture(packet, bundle, "russian-synthetic")
    assert validate_submission(english, packet)[0]["review_context"]["display_language"] == "en"
    assert validate_submission(russian, packet)[0]["review_context"]["display_language"] == "ru"
    agreement = calculate_human_agreement(english, russian, packet)
    assert agreement["exact_agreement"] == 1
    assert agreement["same_presentation"] is False
    assert agreement["second_review_context"]["translation_method"] == "ai_assisted"
    russian["annotations"][0]["evidence"] = "Synthetic evidence absent from original"
    with pytest.raises(ValueError, match="exact quotation"):
        validate_submission(russian, packet)


@pytest.mark.parametrize("context", [None, {}, {"display_language": "ru"},
    dict(source_language="en", display_language="ru", translation_method="ai_assisted",
         translation_sha256="0" * 64, original_available=1)])
def test_explicit_bad_context_never_defaults_to_english(context):
    packet, bundle = translated_fixture()
    exported = export_fixture(packet, bundle)
    exported["review_context"] = context
    with pytest.raises(ValueError, match="context"):
        validate_submission(exported, packet)


def test_legacy_html_has_null_translation(tmp_path):
    packet, _ = translated_fixture()
    html = write_review_html(packet, tmp_path / "en.html").read_text(encoding="utf-8")
    assert 'id="review-translation">null</script>' in html
    assert review_context(export_fixture(packet))["translation_method"] == "none"
