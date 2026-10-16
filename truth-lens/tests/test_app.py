import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.main import app, get_db


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_free_news_search_returns_sources_without_claiming_verification(client, monkeypatch):
    class FakeResponse:
        content = b"""<?xml version="1.0"?>
        <rss><channel><item>
          <title>Report on a sample claim</title>
          <link>https://news.example.org/report</link>
          <pubDate>Thu, 15 Oct 2026 10:00:00 GMT</pubDate>
          <source>The Example Times</source>
        </item></channel></rss>"""

        def raise_for_status(self):
            return None

    monkeypatch.setattr("app.fact_check.httpx.get", lambda *_args, **_kwargs: FakeResponse())
    monkeypatch.delenv("GOOGLE_FACT_CHECK_API_KEY", raising=False)
    response = client.post("/api/analyze", json={"claim": "A sample claim for the demo."})

    assert response.status_code == 200
    result = response.json()
    assert result["mode"] == "news_search"
    assert result["verdict"] == "inconclusive"
    assert result["sources"][0]["url"] == "https://news.example.org/report"
    assert result["sources"][0]["source_type"] == "news"
    assert result["sources"][0]["rating"] == "News result — not a fact-check"
    assert "not fact-checking" in result["summary"]


def test_free_news_search_failure_is_reported(client, monkeypatch):
    def fail_search(*_args, **_kwargs):
        raise httpx.ConnectError("search provider unavailable")

    monkeypatch.setattr("app.fact_check.httpx.get", fail_search)
    monkeypatch.delenv("GOOGLE_FACT_CHECK_API_KEY", raising=False)
    response = client.post("/api/analyze", json={"claim": "A sample claim."})

    assert response.status_code == 502
    assert "temporarily unavailable" in response.json()["detail"]


def test_history_persists_analysis(client, monkeypatch):
    monkeypatch.setattr(
        "app.fact_check.httpx.get",
        lambda *_args, **_kwargs: type("Response", (), {
            "content": b"<rss><channel/></rss>",
            "raise_for_status": lambda self: None,
        })(),
    )
    monkeypatch.delenv("GOOGLE_FACT_CHECK_API_KEY", raising=False)
    created = client.post("/api/analyze", json={"claim": "History persistence test claim."}).json()

    response = client.get("/api/history")

    assert response.status_code == 200
    assert response.json()[0]["id"] == created["id"]
    assert response.json()[0]["claim"] == "History persistence test claim."


@pytest.mark.parametrize(
    "body",
    [{}, {"claim": "   "}, {"claim": "x" * 6001}],
)
def test_invalid_claims_are_rejected(client, body):
    response = client.post("/api/analyze", json=body)

    assert response.status_code == 422


def test_history_detail_not_found(client):
    response = client.get("/api/history/999")

    assert response.status_code == 404


def test_no_matching_reviews_is_inconclusive(client, monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"claims": []}

    def fake_get(*_args, **_kwargs):
        return FakeResponse()

    monkeypatch.setenv("GOOGLE_FACT_CHECK_API_KEY", "test-key")
    monkeypatch.setattr("app.fact_check.httpx.get", fake_get)
    response = client.post("/api/analyze", json={"claim": "A claim without reviews."})

    assert response.status_code == 200
    assert response.json()["mode"] == "live"
    assert response.json()["verdict"] == "inconclusive"
    assert response.json()["sources"] == []


def test_live_reviews_are_returned_as_sources(client, monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "claims": [
                    {
                        "text": "A sample claim.",
                        "claimReview": [
                            {
                                "url": "https://review.example.org/check",
                                "textualRating": "False",
                                "reviewDate": "2025-02-03",
                                "publisher": {"name": "Example Fact Check"},
                            }
                        ],
                    }
                ]
            }

    monkeypatch.setenv("GOOGLE_FACT_CHECK_API_KEY", "test-key")
    monkeypatch.setattr("app.fact_check.httpx.get", lambda *_args, **_kwargs: FakeResponse())
    response = client.post("/api/analyze", json={"claim": "A sample claim."})

    assert response.status_code == 200
    result = response.json()
    assert result["verdict"] == "contradicted"
    assert result["sources"] == [
        {
            "title": "A sample claim.",
            "publisher": "Example Fact Check",
            "url": "https://review.example.org/check",
            "rating": "False",
            "review_date": "2025-02-03",
            "source_type": "fact_check",
        }
    ]
    reopened = client.get(f"/api/history/{result['id']}")
    assert reopened.json()["keywords"] == result["keywords"]
