"""FastAPI entry point.

Run (from the backend folder):  uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from config import Settings, settings as default_settings
from models.schemas import AnalyzeRequest, JobAccepted, JobView
from scraper.exceptions import ScraperError
from scraper.profile_validator import validate_profile_url
from services.analyzer import default_client_factory, run_analysis
from services.job_manager import JobManager
from services.json_generator import resolve_download

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("lcpa")


def create_app(settings: Settings = default_settings, client_factory=default_client_factory) -> FastAPI:
    jobs = JobManager()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        settings.output_dir.mkdir(parents=True, exist_ok=True)
        yield
        jobs.shutdown()

    app = FastAPI(title="LeetCode Profile Analyzer API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["GET", "POST"], allow_headers=["*"]
    )

    @app.exception_handler(ScraperError)
    async def scraper_error_handler(_, exc: ScraperError):
        return JSONResponse(status_code=exc.http_status, content={"error": exc.to_dict()})

    @app.get("/api/health")
    def health():
        return {"status": "ok", "output_dir_writable": settings.output_dir.exists()}

    @app.post("/api/analyze", status_code=202, response_model=JobAccepted)
    def analyze(body: AnalyzeRequest):
        """Validate the URL immediately, then scrape in the background. Poll status_url."""
        profile = validate_profile_url(body.profile_url)  # raises InvalidProfileURL -> 400
        job_id = jobs.submit(
            profile.username,
            lambda progress: run_analysis(profile, settings, progress, client_factory),
        )
        log.info("Queued job %s for %s", job_id, profile.username)
        return JobAccepted(job_id=job_id, username=profile.username, status_url=f"/api/jobs/{job_id}")

    @app.post("/api/validate")
    def validate(body: AnalyzeRequest):
        profile = validate_profile_url(body.profile_url)
        return {"username": profile.username, "profile_url": profile.profile_url}

    @app.get("/api/jobs/{job_id}", response_model=JobView)
    def job_status(job_id: str):
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="No such job. It may have expired; start a new analysis.")
        return job

    @app.get("/api/download/{filename}")
    def download(filename: str):
        path = resolve_download(settings.output_dir, filename)
        if path is None:
            raise HTTPException(status_code=404, detail="File not found. Run the analysis again to regenerate it.")
        return FileResponse(path, media_type="application/json; charset=utf-8", filename=filename)

    return app


app = create_app()
