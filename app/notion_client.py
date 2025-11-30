"""Notion API client for updating pages with transcripts."""

import httpx
from typing import Optional

from app.config import get_settings

NOTION_VERSION = "2022-06-28"
NOTION_API_BASE = "https://api.notion.com/v1"


class NotionClient:
    """Client for interacting with Notion API."""

    def __init__(self):
        settings = get_settings()
        self.api_key = settings.notion_api_key
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    async def update_page_status(
        self,
        page_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> dict:
        """Update the status property of a Notion page."""
        url = f"{NOTION_API_BASE}/pages/{page_id}"

        data = {"properties": {"Status": {"select": {"name": status}}}}

        if error_message:
            data["properties"]["Error Log"] = {
                "rich_text": [{"text": {"content": error_message[:2000]}}]
            }

        async with httpx.AsyncClient() as client:
            response = await client.patch(url, headers=self.headers, json=data)
            response.raise_for_status()
            return response.json()

    async def update_page_with_transcript(
        self,
        page_id: str,
        transcript: str,
        title: Optional[str] = None,
        source_type: str = "YouTube",
    ) -> dict:
        """Update a Notion page with transcript content."""
        # First, update properties
        url = f"{NOTION_API_BASE}/pages/{page_id}"

        properties = {"Status": {"select": {"name": "Completed"}}}

        if title:
            properties["Title"] = {"title": [{"text": {"content": title}}]}

        data = {"properties": properties}

        async with httpx.AsyncClient() as client:
            response = await client.patch(url, headers=self.headers, json=data)
            response.raise_for_status()

        # Then, append transcript as page content blocks
        await self._append_transcript_blocks(page_id, transcript, source_type)

        return {"status": "success", "page_id": page_id}

    async def _append_transcript_blocks(
        self, page_id: str, transcript: str, source_type: str
    ) -> None:
        """Append transcript content as blocks to the page."""
        url = f"{NOTION_API_BASE}/blocks/{page_id}/children"

        # Split transcript into chunks (Notion has 2000 char limit per rich text)
        chunks = self._split_text(transcript, max_length=2000)

        blocks = [
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [
                        {"type": "text", "text": {"content": f"{source_type} Transcript"}}
                    ]
                },
            },
            {
                "object": "block",
                "type": "divider",
                "divider": {},
            },
        ]

        # Add transcript paragraphs
        for chunk in chunks:
            blocks.append(
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": chunk}}]
                    },
                }
            )

        # Notion limits to 100 blocks per request
        for i in range(0, len(blocks), 100):
            batch = blocks[i : i + 100]
            async with httpx.AsyncClient() as client:
                response = await client.patch(
                    url, headers=self.headers, json={"children": batch}
                )
                response.raise_for_status()

    async def update_url_field(self, page_id: str, url: str) -> None:
        """
        Update the URL field if it was empty and URL was in title.

        Tries common URL property names used in Notion databases.
        """
        api_url = f"{NOTION_API_BASE}/pages/{page_id}"

        # Try different property names for URL field
        url_property_names = ["URL", "url", "Link", "link", "Source", "source"]

        for prop_name in url_property_names:
            try:
                data = {"properties": {prop_name: {"url": url}}}
                async with httpx.AsyncClient() as client:
                    response = await client.patch(api_url, headers=self.headers, json=data)
                    if response.status_code == 200:
                        return  # Success
            except Exception:
                continue  # Try next property name

    def _split_text(self, text: str, max_length: int = 2000) -> list[str]:
        """Split text into chunks respecting word boundaries."""
        if len(text) <= max_length:
            return [text]

        chunks = []
        current_chunk = ""

        for paragraph in text.split("\n\n"):
            if len(current_chunk) + len(paragraph) + 2 <= max_length:
                if current_chunk:
                    current_chunk += "\n\n"
                current_chunk += paragraph
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                # Handle paragraphs longer than max_length
                if len(paragraph) > max_length:
                    words = paragraph.split()
                    current_chunk = ""
                    for word in words:
                        if len(current_chunk) + len(word) + 1 <= max_length:
                            if current_chunk:
                                current_chunk += " "
                            current_chunk += word
                        else:
                            if current_chunk:
                                chunks.append(current_chunk)
                            current_chunk = word
                else:
                    current_chunk = paragraph

        if current_chunk:
            chunks.append(current_chunk)

        return chunks


notion_client = NotionClient()
