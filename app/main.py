"""
Podcast Transcriber API - Railway Deployment

Webhook-triggered service for transcribing YouTube videos and Apple Podcasts,
saving transcripts to Notion pages.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel, HttpUrl
from typing import Optional

from app.config import get_settings
from app.notion_client import notion_client
from app.youtube_service import is_youtube_url, get_youtube_transcript
from app.podcast_service import is_apple_podcast_url, get_podcast_transcript

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info("Starting Podcast Transcriber API")
    settings = get_settings()

    # Validate required settings
    missing = []
    if not settings.notion_api_key:
        missing.append("NOTION_API_KEY")
    if not settings.openai_api_key:
        missing.append("OPENAI_API_KEY")

    if missing:
        logger.warning(f"Missing environment variables: {', '.join(missing)}")

    yield
    logger.info("Shutting down Podcast Transcriber API")


app = FastAPI(
    title="Podcast Transcriber API",
    description="Transcribe YouTube videos and Apple Podcasts, save to Notion",
    version="1.0.0",
    lifespan=lifespan,
)


# Request/Response Models
class WebhookPayload(BaseModel):
    """Payload from Notion webhook automation."""

    page_id: str
    url: str  # YouTube URL or Apple Podcast URL
    database_id: Optional[str] = None


class TranscriptRequest(BaseModel):
    """Direct transcript request (without Notion integration)."""

    url: str


class TranscriptResponse(BaseModel):
    """Response with transcript data."""

    title: str
    transcript: str
    source_type: str  # "YouTube" or "Apple Podcast"
    success: bool = True


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str


# Background task for processing transcripts
async def process_transcript_task(page_id: str, url: str):
    """
    Background task to process transcript and update Notion page.

    This runs asynchronously after the webhook returns 200 OK,
    allowing Notion automation to complete without timeout.
    """
    try:
        logger.info(f"Processing transcript for page {page_id}: {url}")

        # Update status to Processing
        await notion_client.update_page_status(page_id, "Processing")

        # Determine source type and get transcript
        if is_youtube_url(url):
            result = await get_youtube_transcript(url)
            source_type = "YouTube"
        elif is_apple_podcast_url(url):
            result = await get_podcast_transcript(url)
            source_type = "Apple Podcast"
        else:
            raise ValueError(f"Unsupported URL type: {url}")

        # Update Notion page with transcript
        await notion_client.update_page_with_transcript(
            page_id=page_id,
            transcript=result["transcript"],
            title=result["title"],
            source_type=source_type,
        )

        logger.info(f"Successfully processed transcript for page {page_id}")

    except Exception as e:
        logger.error(f"Error processing transcript for page {page_id}: {e}")
        try:
            await notion_client.update_page_status(
                page_id, "Error", error_message=str(e)
            )
        except Exception as update_error:
            logger.error(f"Failed to update error status: {update_error}")


# API Endpoints
@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint - health check."""
    return HealthResponse(status="healthy", version="1.0.0")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for Railway."""
    return HealthResponse(status="healthy", version="1.0.0")


@app.post("/webhook")
async def notion_webhook(payload: WebhookPayload, background_tasks: BackgroundTasks):
    """
    Webhook endpoint for Notion automations.

    When a page is created/updated in Notion with a YouTube or Apple Podcast URL,
    this endpoint receives the webhook and processes the transcript in the background.

    Expected payload:
    {
        "page_id": "notion-page-id",
        "url": "https://youtube.com/watch?v=... or https://podcasts.apple.com/...",
        "database_id": "optional-database-id"
    }
    """
    logger.info(f"Received webhook for page {payload.page_id}")

    # Validate URL type
    if not is_youtube_url(payload.url) and not is_apple_podcast_url(payload.url):
        raise HTTPException(
            status_code=400,
            detail=f"URL must be a YouTube or Apple Podcasts link: {payload.url}",
        )

    # Queue background task
    background_tasks.add_task(process_transcript_task, payload.page_id, payload.url)

    # Return immediately so Notion doesn't timeout
    return {
        "status": "accepted",
        "message": "Transcript processing started",
        "page_id": payload.page_id,
    }


@app.post("/transcript", response_model=TranscriptResponse)
async def get_transcript(request: TranscriptRequest):
    """
    Direct transcript endpoint (without Notion integration).

    Use this to test transcription or get transcripts without saving to Notion.
    """
    url = request.url

    try:
        if is_youtube_url(url):
            result = await get_youtube_transcript(url)
            source_type = "YouTube"
        elif is_apple_podcast_url(url):
            result = await get_podcast_transcript(url)
            source_type = "Apple Podcast"
        else:
            raise HTTPException(
                status_code=400,
                detail=f"URL must be a YouTube or Apple Podcasts link: {url}",
            )

        return TranscriptResponse(
            title=result["title"],
            transcript=result["transcript"],
            source_type=source_type,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting transcript: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhook/raw")
async def raw_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Raw webhook endpoint for debugging.

    Accepts any JSON payload and logs it for debugging Notion automation setup.
    """
    try:
        body = await request.json()
        logger.info(f"Raw webhook received: {body}")

        # Try to extract page_id and url from various payload formats
        page_id = body.get("page_id") or body.get("pageId") or body.get("id")
        url = (
            body.get("url")
            or body.get("YouTube URL")
            or body.get("URL")
            or body.get("Podcast URL")
        )

        if page_id and url:
            background_tasks.add_task(process_transcript_task, page_id, url)
            return {"status": "accepted", "page_id": page_id, "url": url}

        return {
            "status": "received",
            "message": "Payload logged. Missing page_id or url for processing.",
            "received_keys": list(body.keys()),
        }

    except Exception as e:
        logger.error(f"Error parsing raw webhook: {e}")
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
