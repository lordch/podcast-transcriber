"""
Content Transcriber API - Railway Deployment

Webhook-triggered service for transcribing YouTube videos, Apple Podcasts,
and extracting article content, saving to Notion pages.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel
from typing import Optional

from app.config import get_settings
from app.notion_client import notion_client
from app.youtube_service import is_youtube_url, get_youtube_transcript
from app.podcast_service import is_apple_podcast_url, get_podcast_transcript
from app.article_service import fetch_article_content, is_audio_url
from app.content_detector import detect_content_type, find_content_url

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info("Starting Content Transcriber API")
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
    logger.info("Shutting down Content Transcriber API")


app = FastAPI(
    title="Content Transcriber API",
    description="Transcribe YouTube videos, Apple Podcasts, and extract articles. Save to Notion.",
    version="2.0.0",
    lifespan=lifespan,
)


# Request/Response Models
class WebhookPayload(BaseModel):
    """Payload from Notion webhook automation."""

    page_id: str
    url: Optional[str] = ""  # URL field (may be empty)
    title: Optional[str] = ""  # Name/Title field (URL might be here)
    content_type: Optional[str] = ""  # Optional content type hint
    database_id: Optional[str] = None


class TranscriptRequest(BaseModel):
    """Direct transcript request (without Notion integration)."""

    url: str
    content_type: Optional[str] = None  # Optional: "YouTube", "Podcast", "Article"


class TranscriptResponse(BaseModel):
    """Response with transcript data."""

    title: str
    transcript: str
    source_type: str  # "YouTube", "Podcast", or "Article"
    success: bool = True


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str


async def process_content(url: str, content_type: Optional[str] = None) -> dict:
    """
    Process content URL and return transcript/content.

    Args:
        url: Content URL
        content_type: Optional hint for content type

    Returns:
        dict with 'title', 'transcript', 'source_type' keys
    """
    # Auto-detect content type if not specified
    if not content_type or content_type in ("", "Unknown"):
        content_type = detect_content_type(url)

    logger.info(f"Processing {content_type} content: {url}")

    if content_type == "YouTube" or is_youtube_url(url):
        result = await get_youtube_transcript(url)
        return {**result, "source_type": "YouTube"}

    elif content_type == "Podcast" or is_apple_podcast_url(url) or is_audio_url(url):
        result = await get_podcast_transcript(url)
        return {**result, "source_type": "Podcast"}

    else:  # Article or unknown
        result = await fetch_article_content(url)
        return {**result, "source_type": "Article"}


async def process_transcript_task(
    page_id: str,
    content_url: str,
    content_type: Optional[str] = None,
    url_was_in_title: bool = False,
):
    """
    Background task to process content and update Notion page.

    This runs asynchronously after the webhook returns 200 OK,
    allowing Notion automation to complete without timeout.
    """
    try:
        logger.info(f"Processing content for page {page_id}: {content_url}")

        # Update status to Processing
        await notion_client.update_page_status(page_id, "Processing")

        # Process the content
        result = await process_content(content_url, content_type)

        # Update Notion page with transcript
        await notion_client.update_page_with_transcript(
            page_id=page_id,
            transcript=result["transcript"],
            title=result.get("title"),
            source_type=result["source_type"],
        )

        # If URL was in title field, also populate the URL field
        if url_was_in_title:
            await notion_client.update_url_field(page_id, content_url)

        logger.info(f"Successfully processed {result['source_type']} for page {page_id}")

    except Exception as e:
        logger.error(f"Error processing content for page {page_id}: {e}")
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
    return HealthResponse(status="healthy", version="2.0.0")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for Railway."""
    return HealthResponse(status="healthy", version="2.0.0")


@app.post("/webhook")
async def notion_webhook(payload: WebhookPayload, background_tasks: BackgroundTasks):
    """
    Webhook endpoint for Notion automations.

    Handles URLs in both the URL field and the Name/Title field.
    When sharing to Notion, the URL can end up in either place depending
    on the sharing method used.

    Expected payload:
    {
        "page_id": "notion-page-id",
        "url": "{{page.URL}}",
        "title": "{{page.Name}}",
        "content_type": "{{page.Content Type}}"
    }
    """
    logger.info(f"Received webhook for page {payload.page_id}")
    logger.info(f"URL field: {payload.url}")
    logger.info(f"Title field: {payload.title}")
    logger.info(f"Content type: {payload.content_type}")

    # Find URL from either field
    url_field = (payload.url or "").strip()
    title_field = (payload.title or "").strip()

    content_url = find_content_url(url_field, title_field)

    if not content_url:
        error_msg = "No URL found in either URL field or Title field"
        logger.error(error_msg)
        # Try to update the page with error
        try:
            await notion_client.update_page_status(
                payload.page_id, "Error", error_message=error_msg
            )
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=error_msg)

    # Check if URL was in title (so we can populate URL field later)
    url_was_in_title = not url_field.startswith("http") and title_field.startswith("http")

    logger.info(f"Found content URL: {content_url}")
    logger.info(f"URL was in title field: {url_was_in_title}")

    # Queue background task
    background_tasks.add_task(
        process_transcript_task,
        payload.page_id,
        content_url,
        payload.content_type,
        url_was_in_title,
    )

    # Return immediately so Notion doesn't timeout
    return {
        "status": "accepted",
        "message": "Content processing started",
        "page_id": payload.page_id,
        "content_url": content_url,
        "detected_type": detect_content_type(content_url),
    }


@app.post("/transcript", response_model=TranscriptResponse)
async def get_transcript(request: TranscriptRequest):
    """
    Direct transcript endpoint (without Notion integration).

    Use this to test transcription or get transcripts without saving to Notion.
    Supports YouTube, Apple Podcasts, and articles.
    """
    try:
        result = await process_content(request.url, request.content_type)

        return TranscriptResponse(
            title=result.get("title", "Untitled"),
            transcript=result["transcript"],
            source_type=result["source_type"],
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
    Attempts to find page_id and url from various payload formats.
    """
    try:
        body = await request.json()
        logger.info(f"Raw webhook received: {body}")

        # Try to extract page_id from various formats
        page_id = (
            body.get("page_id")
            or body.get("pageId")
            or body.get("id")
        )

        # Try to extract URL from various formats
        url_field = (
            body.get("url")
            or body.get("URL")
            or body.get("YouTube URL")
            or body.get("Podcast URL")
            or ""
        )

        title_field = (
            body.get("title")
            or body.get("Title")
            or body.get("Name")
            or body.get("name")
            or ""
        )

        content_type = (
            body.get("content_type")
            or body.get("Content Type")
            or body.get("contentType")
            or ""
        )

        # Find URL from either field
        content_url = find_content_url(url_field, title_field)

        if page_id and content_url:
            url_was_in_title = not str(url_field).startswith("http") and str(title_field).startswith("http")

            background_tasks.add_task(
                process_transcript_task,
                page_id,
                content_url,
                content_type,
                url_was_in_title,
            )

            return {
                "status": "accepted",
                "page_id": page_id,
                "content_url": content_url,
                "detected_type": detect_content_type(content_url),
            }

        return {
            "status": "received",
            "message": "Payload logged. Could not extract page_id and url for processing.",
            "received_keys": list(body.keys()),
            "found_page_id": page_id,
            "found_url": content_url,
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
