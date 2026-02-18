from fastapi import FastAPI, Request, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import StreamingResponse, FileResponse
from pathlib import Path
import shutil
import tempfile
import os

from app.services.parser import FileParser
from app.services.scraper import WebScraper
from app.services.tts_service import TTSService
from app.services.audio_exporter import AudioExporter

app = FastAPI(title="Vietnamese TTS Ebook Reader")

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

# Temporary storage for uploaded/parsed books (simplified for this demo)
# In a real app, use a database or session.
BOOK_STORAGE = {}

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/reader")
async def reader_page(request: Request):
    return templates.TemplateResponse("reader.html", {"request": request, "voices": TTSService.get_voices(), "book": BOOK_STORAGE.get("current_book")})

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        # Save uploaded file temporarily
        suffix = Path(file.filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name
        
        # Parse text
        text = FileParser.extract_text(tmp_path)
        
        # Store in memory (for demo purposes, single user)
        BOOK_STORAGE["current_book"] = {
            "title": file.filename,
            "content": text,
            "filename": file.filename
        }
        
        os.unlink(tmp_path) # Clean up upload
        return {"status": "success", "title": file.filename}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/read-url")
async def read_url(url: str = Form(...)):
    try:
        data = WebScraper.fetch_content(url)
        BOOK_STORAGE["current_book"] = {
            "title": data["title"],
            "content": data["content"],
            "url": url
        }
        return {"status": "success", "title": data["title"]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/tts/stream")
async def tts_stream(text: str, voice: str, rate: str = "+0%", pitch: str = "+0Hz"):
    """
    Stream audio directly to client.
    """
    return StreamingResponse(
        TTSService.stream_audio(text, voice),
        media_type="audio/mpeg"
    )

@app.post("/api/export")
async def export_audio(
    background_tasks: BackgroundTasks,
    text: str = Form(...),
    voice: str = Form(...),
    title: str = Form("Audiobook"),
    rate: str = Form("+0%")
):
    """
    Generate MP3 file in background.
    """
    # Create a temp file path to write to initially
    # For simplicity, we'll write to a 'exports' dir in static
    export_dir = Path("app/static/exports")
    export_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f"{title}_{voice}.mp3".replace(" ", "_")
    output_path = export_dir / filename
    
    # We can't await validly in background tasks easily without more logic, 
    # but Edge-TTS is async. For this prototype, we will run the generation efficiently.
    # Note: BackgroundTasks in FastAPI run *after* response. 
    # We might want to return a "Job Started" status.
    
    # Actually, let's keep it simple: simpler to await it for short texts, 
    # or just return the path if we want to download.
    # For a full book, we really need a queue. 
    # Let's just generate it now for the demo.
    
    await TTSService.generate_audio_file(text[:5000], voice, str(output_path), rate=rate) # Limit to 5000 chars for demo speed
    
    # Optional: Tag it
    # AudioExporter.convert_and_tag(str(output_path), str(output_path), title=title) 
    
    return {"status": "completed", "download_url": f"/static/exports/{filename}"}

@app.get("/api/voices")
def get_voices():
    return TTSService.get_voices()
