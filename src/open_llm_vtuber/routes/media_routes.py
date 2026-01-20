"""Media processing routes (ASR, TTS)."""

import json
from uuid import uuid4
from datetime import datetime

import numpy as np
from fastapi import APIRouter, WebSocket, UploadFile, File, Response
from starlette.websockets import WebSocketDisconnect
from loguru import logger

from ..service_context import ServiceContext
from ..constants.audio import WAV_HEADER_SIZE_BYTES, INT16_TO_FLOAT32_DIVISOR


def init_media_routes(default_context_cache: ServiceContext) -> APIRouter:
    """
    Create routes for media processing (ASR, TTS).

    Args:
        default_context_cache: Default service context cache.

    Returns:
        APIRouter: Router with media processing endpoints.
    """
    router = APIRouter()

    @router.post("/asr")
    async def transcribe_audio(file: UploadFile = File(...)):
        """Endpoint for transcribing audio using the ASR engine."""
        logger.info(f"Received audio file for transcription: {file.filename}")

        try:
            contents = await file.read()

            if len(contents) < WAV_HEADER_SIZE_BYTES:
                raise ValueError("Invalid WAV file: File too small")

            audio_data = contents[WAV_HEADER_SIZE_BYTES:]

            if len(audio_data) % 2 != 0:
                raise ValueError("Invalid audio data: Buffer size must be even")

            try:
                audio_array = (
                    np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
                    / INT16_TO_FLOAT32_DIVISOR
                )
            except ValueError as e:
                raise ValueError(
                    f"Audio format error: {str(e)}. Please ensure the file is 16-bit PCM WAV format."
                )

            if len(audio_array) == 0:
                raise ValueError("Empty audio data")

            text = await default_context_cache.asr_engine.async_transcribe_np(
                audio_array
            )
            logger.info(f"Transcription result: {text}")
            return {"text": text}

        except ValueError as e:
            logger.error(f"Audio format error: {e}")
            return Response(
                content=json.dumps({"error": str(e)}),
                status_code=400,
                media_type="application/json",
            )
        except Exception as e:
            logger.error(f"Error during transcription: {e}")
            return Response(
                content=json.dumps(
                    {"error": "Internal server error during transcription"}
                ),
                status_code=500,
                media_type="application/json",
            )

    @router.websocket("/tts-ws")
    async def tts_endpoint(websocket: WebSocket):
        """WebSocket endpoint for TTS generation."""
        await websocket.accept()
        logger.info("TTS WebSocket connection established")

        try:
            while True:
                data = await websocket.receive_json()
                text = data.get("text")
                if not text:
                    continue

                logger.info(f"Received text for TTS: {text}")

                sentences = [s.strip() for s in text.split(".") if s.strip()]

                try:
                    for sentence in sentences:
                        sentence = sentence + "."
                        file_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid4())[:8]}"
                        audio_path = (
                            await default_context_cache.tts_engine.async_generate_audio(
                                text=sentence, file_name_no_ext=file_name
                            )
                        )
                        logger.info(
                            f"Generated audio for sentence: {sentence} at: {audio_path}"
                        )

                        await websocket.send_json(
                            {
                                "status": "partial",
                                "audioPath": audio_path,
                                "text": sentence,
                            }
                        )

                    await websocket.send_json({"status": "complete"})

                except Exception as e:
                    logger.error(f"Error generating TTS: {e}")
                    await websocket.send_json({"status": "error", "message": str(e)})

        except WebSocketDisconnect:
            logger.info("TTS WebSocket client disconnected")
        except Exception as e:
            logger.error(f"Error in TTS WebSocket connection: {e}")
            await websocket.close()

    return router
