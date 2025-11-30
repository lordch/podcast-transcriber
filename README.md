# Podcast Transcriber API

Webhook-triggered API service that transcribes YouTube videos and Apple Podcasts, saving transcripts to Notion pages. Designed for deployment on Railway.

## Architecture

```
User adds URL to Notion Database
    ↓
Notion Automation triggers webhook
    ↓
Railway API receives webhook
    ↓
YouTube: Extract subtitles via yt-dlp
Apple Podcast: Extract audio URL → Whisper API
    ↓
Update Notion page with transcript
    ↓
Status changed to "Completed"
```

## Features

- **YouTube Transcripts**: Extracts existing subtitles/captions (no API cost)
- **Apple Podcast Transcripts**: Transcribes audio via OpenAI Whisper API
- **Notion Integration**: Automatically updates pages with transcripts
- **Background Processing**: Webhook returns immediately, processes async

## Quick Start (Railway Deployment)

### 1. Deploy to Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template)

Or manually:
1. Push this repo to GitHub
2. Connect Railway to your GitHub repo
3. Railway will auto-detect the Python app and deploy

### 2. Set Environment Variables in Railway

```
NOTION_API_KEY=secret_xxxxxxxxxxxxx
NOTION_DATABASE_ID=xxxxxxxxxxxxx
OPENAI_API_KEY=sk-xxxxxxxxxxxxx
```

### 3. Get Your Webhook URL

After deployment, Railway provides a URL like:
```
https://your-app-name.up.railway.app
```

Your webhook endpoint is:
```
https://your-app-name.up.railway.app/webhook
```

## Notion Setup

### Database Schema

Create a Notion database with these properties:

| Property | Type | Description |
|----------|------|-------------|
| Title | Title | Episode/video title (auto-filled) |
| URL | URL | YouTube or Apple Podcasts link |
| Status | Select | Options: "Pending", "Processing", "Completed", "Error" |
| Error Log | Text | Error messages (auto-filled on failure) |

### Notion Integration Setup

1. Go to [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Create a new integration named "Podcast Transcriber"
3. Copy the "Internal Integration Token" → use as `NOTION_API_KEY`
4. Share your database with the integration:
   - Open database → "..." → "Connections" → Add your integration

### Notion Automation Setup

1. In your database, click "..." → "Automations" → "New automation"
2. **Trigger**: "When URL is not empty" or "When page is created"
3. **Action**: "Send webhook"
4. **URL**: `https://your-app.up.railway.app/webhook`
5. **Body** (Custom JSON):

```json
{
  "page_id": "{{page.id}}",
  "url": "{{page.URL}}"
}
```

## API Endpoints

### Health Check
```
GET /health
```

### Webhook (Notion Integration)
```
POST /webhook
Content-Type: application/json

{
  "page_id": "notion-page-id",
  "url": "https://youtube.com/watch?v=... or https://podcasts.apple.com/..."
}
```

### Direct Transcript (Testing)
```
POST /transcript
Content-Type: application/json

{
  "url": "https://youtube.com/watch?v=..."
}
```

Response:
```json
{
  "title": "Video Title",
  "transcript": "Full transcript text...",
  "source_type": "YouTube"
}
```

## Local Development

### Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -e .

# Copy environment template
cp .env.example .env
# Edit .env with your API keys
```

### Run Locally

```bash
# Run the API server
python -m app.main

# Or with uvicorn directly
uvicorn app.main:app --reload --port 8000
```

### Test Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Test YouTube transcript
curl -X POST http://localhost:8000/transcript \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'

# Test webhook (simulates Notion)
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"page_id": "test-page-id", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```

## CLI Tools (Legacy)

The original CLI tools are still available:

### Download YouTube Transcript
```bash
python download_youtube_transcripts.py "https://youtube.com/watch?v=..."
```

### Transcribe Audio File
```bash
python transcribe.py <podcast_url>
```

## Cost Estimation

- **YouTube**: FREE (extracts existing subtitles)
- **Apple Podcasts**: ~$0.006/minute via Whisper API
  - 1-hour podcast ≈ $0.36
- **Railway**: ~$5/month for low-traffic usage

## Troubleshooting

### "No subtitles available"
- Some YouTube videos don't have captions
- Try videos with CC icon or auto-generated captions

### "Audio file exceeds 25MB limit"
- Whisper API has 25MB limit
- Long podcasts (2+ hours) may need chunking (not implemented)

### "Forbidden" from Notion
- Verify `NOTION_API_KEY` is correct
- Ensure integration is shared with the database

### Webhook not triggering
- Check Notion automation is enabled
- Verify webhook URL is correct (include `/webhook` path)
- Check Railway logs for errors

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `NOTION_API_KEY` | Yes | Notion integration token |
| `NOTION_DATABASE_ID` | No | Default database ID |
| `OPENAI_API_KEY` | Yes* | Required for Apple Podcasts |
| `WEBHOOK_SECRET` | No | For webhook validation |
| `PORT` | No | Server port (default: 8000) |

*Only required if transcribing Apple Podcasts

## License

MIT
