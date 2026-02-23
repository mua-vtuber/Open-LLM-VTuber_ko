"""Media processing routes (ASR, TTS).

오디오/미디어 처리를 위한 API 라우트.
ASR(음성 인식) 및 TTS(음성 합성) 기능을 제공합니다.
"""

import json
from uuid import uuid4
from datetime import datetime

import numpy as np
from fastapi import APIRouter, WebSocket, UploadFile, File, Response
from starlette.websockets import WebSocketDisconnect
from loguru import logger

from ..service_context import ServiceContext
from ..constants.audio import WAV_HEADER_SIZE_BYTES, INT16_TO_FLOAT32_DIVISOR
from ..schemas.api import TranscriptionResponse, ErrorResponse


def init_media_routes(default_context_cache: ServiceContext) -> APIRouter:
    """
    Create routes for media processing (ASR, TTS).

    Args:
        default_context_cache: Default service context cache.

    Returns:
        APIRouter: Router with media processing endpoints.
    """
    router = APIRouter()

    @router.post(
        "/asr",
        tags=["media"],
        summary="음성 인식 (ASR)",
        description=(
            "오디오 파일을 텍스트로 변환합니다. "
            "16-bit PCM WAV 형식의 파일을 지원합니다."
        ),
        response_model=TranscriptionResponse,
        responses={
            200: {"description": "음성 인식 성공", "model": TranscriptionResponse},
            400: {"description": "오디오 형식 오류", "model": ErrorResponse},
            500: {"description": "서버 오류", "model": ErrorResponse},
        },
    )
    async def transcribe_audio(
        file: UploadFile = File(..., description="변환할 WAV 오디오 파일"),
    ):
        """
        오디오 파일을 텍스트로 변환합니다.

        지원 형식: 16-bit PCM WAV

        Args:
            file: WAV 형식의 오디오 파일

        Returns:
            JSONResponse: 인식된 텍스트
        """
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
                content=json.dumps(
                    {
                        "error": "Invalid audio format. Please ensure the file is 16-bit PCM WAV format."
                    }
                ),
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

    @router.websocket(
        "/tts-ws",
        name="tts_websocket",
    )
    async def tts_endpoint(websocket: WebSocket):
        """
        TTS(음성 합성) WebSocket 엔드포인트.

        WebSocket을 통해 텍스트를 실시간으로 음성으로 변환합니다.
        문장 단위로 분할하여 점진적으로 오디오를 전송합니다.

        ## 요청 형식
        ```json
        {"text": "변환할 텍스트"}
        ```

        ## 응답 형식
        - 부분 응답: `{"status": "partial", "audioPath": "/cache/...", "text": "..."}`
        - 완료 응답: `{"status": "complete"}`
        - 오류 응답: `{"status": "error", "message": "..."}`

        Tags:
            media: 오디오/미디어 처리
        """
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
