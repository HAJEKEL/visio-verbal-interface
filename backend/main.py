# uvicorn main:app  # uvicorn main:app --reload
# audio format: wav
import ffmpeg
# 
import os

os.environ["VOSK_LOG_LEVEL"] = "-1"  # Disable all Vosk logs


# main imports
from fastapi.responses import FileResponse
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from decouple import config

# Custom function imports
from functions.vosk_stt import speech_to_text
from functions.openai_response_tts import get_gpt_response, text_to_speech
from functions.database import update_conversation_history, reset_conversation_history
from functions.tts_play_directly import text_to_speech_play_directly
from functions.openai_vlm import get_gpt_response_vlm
from functions.database import update_conversation_history_vlm
# Make a static folder to send images to openai
from fastapi.staticfiles import StaticFiles
# For unique file names
from uuid import uuid4



# Initiate app
app = FastAPI()
# CORS origins that are allowed to connect to this server
origins = [
    "http://localhost:5173", # React dev server
    "http://localhost:5174", # React dev server second
    "http://localhost:4173", # React deploy server
    "http://localhost:4174", # React deploy server second
    "http://localhost:3000",
    "http://127.0.0.1:5174", # Add 127.0.0.1 for browser's localhost interpretation
    "http://127.0.0.1:5173",  # Add 127.0.0.1 as another dev server
    "http://127.0.0.1:8001",
    "http://localhost:8001",
    "https://summary-sunbird-dashing.ngrok-free.app",
    "https://images-sunbird-dashing.ngrok-free.app",
    "https://frontend-example.ngrok-free.app"] # General frontend application server

# Add CORS middleware to the app
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files from the "static" folder
app.mount("/images", StaticFiles(directory="images"), name="images")
# Serve images on a separate static route
@app.get("/get_image/{image_name}")
async def get_image(image_name: str):
    file_path = f"images/{image_name}"
    
    # Check if the file exists
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Image not found")

    # Return the image as a response
    return FileResponse(file_path, media_type="image/jpeg")  # Adjust media_type if needed

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/health")
async def check_health():
    return {"status": "ok"}

@app.get("/reset")
async def reset():
    return reset_conversation_history()

@app.get("/get_audio")
async def get_audio():
    # Get saved audio file
    audio_file = "data/voice.wav"
    transcript = speech_to_text(audio_file)
    print(transcript)
    # guard message decoded
    if transcript is None:
        raise HTTPException(status_code=500, detail="Error decoding audio")
    response = get_gpt_response(transcript)
    print(response)
    if response is None:
        raise HTTPException(status_code=500, detail="Error fetching gpt response")
    update_conversation_history(transcript, response)
    text_to_speech_play_directly(response)
    # if audio is None:
    #     raise HTTPException(status_code=500, detail="Error generating audio response")
    # return "Done"


@app.post("/post_audio")
async def post_audio(file: UploadFile = File(...), image_url: str = Form(None)):
    try:
        # Image URL will now correctly be included from the form
        print(f"Received image URL: {image_url}")

        # Audio processing code remains the same
        original_file_path = f"data/{file.filename}"
        converted_file_path = f"data/converted_{file.filename}"

        with open(original_file_path, "wb") as buffer:
            buffer.write(await file.read())

        ffmpeg.input(original_file_path).output(converted_file_path, ac=1, ar=16000).global_args('-loglevel', 'error', '-hide_banner').run()


        transcript = speech_to_text(converted_file_path)
        if transcript is None:
            raise HTTPException(status_code=500, detail="Error decoding audio")

        # Use the multimodal response if image_url exists
        if image_url:
            print("Using multimodal response")
            response = get_gpt_response_vlm(transcript,image_url)
        else:
            print("Using text-only response")
            response = get_gpt_response(transcript)

        if response is None:
            raise HTTPException(status_code=500, detail="Error fetching GPT response")

        # Update conversation history with or without image
        if image_url:
            update_conversation_history_vlm(transcript, image_url, response)
        else:
            update_conversation_history(transcript, response)

        audio_file_path = text_to_speech(response)
        if not audio_file_path or not os.path.exists(audio_file_path):
            raise HTTPException(status_code=400, detail="Failed to generate audio")

        def iterfile():
            with open(audio_file_path, mode="rb") as file_like:
                yield from file_like
        return StreamingResponse(iterfile(), media_type="audio/mpeg")

    except Exception as e:
        # Print the exception to the console to help debug
        print(f"Error occurred: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        if os.path.exists(original_file_path):
            os.remove(original_file_path)
        if os.path.exists(converted_file_path):
            os.remove(converted_file_path)


@app.post("/upload_image")
async def upload_image(file: UploadFile = File(...)):
    try:
        if not os.path.exists("images"):
            os.makedirs("images")
        # Generate a unique filename
        file_extension = file.filename.split(".")[-1]
        unique_filename = f"{uuid4()}.{file_extension}"
        file_path = f"images/{unique_filename}"
        # Save the file to the static/images folder
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())
        # Generate the file URL using your ngrok domain
        file_url = f"https://images-sunbird-dashing.ngrok-free.app/images/{unique_filename}"
        print(file_url)
        return file_url

    except Exception as e:
        # Print the exception to the console to help debug
        print(f"Error occurred: {e}")
        raise HTTPException(status_code=500, detail=str(e))
