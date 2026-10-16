import pytest

from app.article import extract_article_text, extract_claim_sentence


def test_article_url_extractor_rejects_loopback():
    with pytest.raises(ValueError, match="public address"):
        extract_article_text("http://127.0.0.1/private")


def test_article_claim_extraction_selects_sentence_excerpt():
    text = (
        "This is a short introduction. "
        "A sufficiently detailed factual sentence about a reported event appears here. "
        "Another sufficiently detailed sentence offers further background and context."
    )

    assert extract_claim_sentence(text) == (
        "A sufficiently detailed factual sentence about a reported event appears here."
    )
