import json
from contextlib import asynccontextmanager
from datetime import timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from .article import extract_article_text, extract_claim_sentence
from .db import Base, SessionLocal, engine
from .fact_check import VERDICT_LABELS, analyze_claim
from .models import Analysis
from .schemas import AnalysisRequest, AnalysisResponse, Source

ROOT_DIR = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    columns = {column["name"] for column in inspect(engine).get_columns("analyses")}
    if "keywords_json" not in columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE analyses ADD COLUMN keywords_json TEXT NOT NULL DEFAULT '[]'")
            )
    yield


app = FastAPI(
    title="Truth Lens API",
    description="Transparent claim analysis using published fact-check reviews.",
    version="1.0.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=ROOT_DIR / "static"), name="static")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def serialize_analysis(record: Analysis) -> AnalysisResponse:
    sources = [Source.model_validate(source) for source in json.loads(record.sources_json)]
    created_at = record.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return AnalysisResponse(
        id=record.id,
        claim=record.claim,
        article_url=record.article_url,
        verdict=record.verdict,
        verdict_label=VERDICT_LABELS[record.verdict],
        summary=record.summary,
        mode=record.mode,
        sources=sources,
        keywords=json.loads(record.keywords_json),
        created_at=created_at.isoformat(),
    )


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(ROOT_DIR / "static" / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalysisResponse)
def create_analysis(payload: AnalysisRequest, db: Session = Depends(get_db)):
    article_url = str(payload.article_url) if payload.article_url else None
    claim = payload.claim
    extracted_from_article = bool(article_url and not claim)
    if article_url:
        try:
            article_text = extract_article_text(article_url)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not claim:
            claim = extract_claim_sentence(article_text)
        elif len(claim) > 6000:
            raise HTTPException(status_code=422, detail="Claim text must be 6,000 characters or fewer.")
    if not claim:
        raise HTTPException(status_code=422, detail="Enter a claim or provide an article URL.")

    try:
        result = analyze_claim(claim)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if extracted_from_article:
        result["summary"] = (
            "The claim shown is a sentence excerpt selected from the article, not a verified "
            "AI-generated summary. Check the surrounding article context. "
            + result["summary"]
        )

    record = Analysis(
        claim=claim[:6000],
        article_url=article_url,
        verdict=result["verdict"],
        summary=result["summary"],
        mode=result["mode"],
        sources_json=json.dumps(result["sources"]),
        keywords_json=json.dumps(result["keywords"]),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return serialize_analysis(record)


@app.get("/api/history", response_model=list[AnalysisResponse])
def get_history(limit: int = 20, db: Session = Depends(get_db)):
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 100.")
    records = db.scalars(
        select(Analysis).order_by(Analysis.created_at.desc(), Analysis.id.desc()).limit(limit)
    ).all()
    return [serialize_analysis(record) for record in records]


@app.get("/api/history/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(analysis_id: int, db: Session = Depends(get_db)):
    record = db.get(Analysis, analysis_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return serialize_analysis(record)
