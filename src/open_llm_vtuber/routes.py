import os
import json
from uuid import uuid4
import numpy as np
from datetime import datetime
from fastapi import APIRouter, WebSocket, UploadFile, File, Response
from starlette.responses import JSONResponse
from starlette.websockets import WebSocketDisconnect
from loguru import logger
from .service_context import ServiceContext
from .websocket_handler import WebSocketHandler
from .proxy_handler import ProxyHandler
from .i18n_manager import I18nManager
from .chat_monitor.chzzk_oauth_manager import ChzzkOAuthManager
from starlette.responses import RedirectResponse, HTMLResponse
from .constants.audio import WAV_HEADER_SIZE_BYTES, INT16_TO_FLOAT32_DIVISOR


def init_client_ws_route(default_context_cache: ServiceContext) -> APIRouter:
    """
    Create and return API routes for handling the `/client-ws` WebSocket connections.

    Args:
        default_context_cache: Default service context cache for new sessions.

    Returns:
        APIRouter: Configured router with WebSocket endpoint.
    """

    router = APIRouter()
    ws_handler = WebSocketHandler(default_context_cache)

    @router.websocket("/client-ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket endpoint for client connections"""
        await websocket.accept()
        client_uid = str(uuid4())

        try:
            await ws_handler.handle_new_connection(websocket, client_uid)
            await ws_handler.handle_websocket_communication(websocket, client_uid)
        except WebSocketDisconnect:
            await ws_handler.handle_disconnect(client_uid)
        except Exception as e:
            logger.error(f"Error in WebSocket connection: {e}")
            await ws_handler.handle_disconnect(client_uid)
            raise

    return router


def init_proxy_route(server_url: str) -> APIRouter:
    """
    Create and return API routes for handling proxy connections.

    Args:
        server_url: The WebSocket URL of the actual server

    Returns:
        APIRouter: Configured router with proxy WebSocket endpoint
    """
    router = APIRouter()
    proxy_handler = ProxyHandler(server_url)

    @router.websocket("/proxy-ws")
    async def proxy_endpoint(websocket: WebSocket):
        """WebSocket endpoint for proxy connections"""
        try:
            await proxy_handler.handle_client_connection(websocket)
        except Exception as e:
            logger.error(f"Error in proxy connection: {e}")
            raise

    return router


def init_webtool_routes(default_context_cache: ServiceContext) -> APIRouter:
    """
    Create and return API routes for handling web tool interactions.

    Args:
        default_context_cache: Default service context cache for new sessions.

    Returns:
        APIRouter: Configured router with WebSocket endpoint.
    """

    router = APIRouter()

    @router.get("/web-tool")
    async def web_tool_redirect():
        """Redirect /web-tool to /web_tool/index.html"""
        return Response(status_code=302, headers={"Location": "/web-tool/index.html"})

    @router.get("/web_tool")
    async def web_tool_redirect_alt():
        """Redirect /web_tool to /web_tool/index.html"""
        return Response(status_code=302, headers={"Location": "/web-tool/index.html"})

    @router.get("/api/languages")
    async def get_available_languages():
        """
        Get list of available languages from i18n system.

        Returns language codes with their native display labels.

        Example response:
        {
            "type": "available_languages",
            "count": 3,
            "languages": [
                {"code": "en", "label": "English"},
                {"code": "zh", "label": "中文"},
                {"code": "ko", "label": "한국어"}
            ]
        }
        """
        try:
            languages = I18nManager.get_available_languages_with_labels()
            return JSONResponse(
                {
                    "type": "available_languages",
                    "count": len(languages),
                    "languages": languages,
                }
            )
        except Exception as e:
            logger.error(f"Error getting available languages: {e}")
            return JSONResponse(
                {"error": "Failed to get available languages"}, status_code=500
            )

    @router.get("/chzzk/auth")
    async def chzzk_auth_init():
        """
        Initiate Chzzk OAuth authorization flow.

        Returns a redirect to Chzzk's authorization page where the user can grant permissions.
        """
        try:
            # Get Chzzk config from default context
            chzzk_config = default_context_cache.config.live_config.chat_monitor.chzzk

            if not chzzk_config.client_id or not chzzk_config.client_secret:
                return HTMLResponse(
                    content="<h1>Error</h1><p>Chzzk OAuth credentials not configured. "
                    "Please set client_id and client_secret in conf.yaml</p>",
                    status_code=400,
                )

            # Create OAuth manager
            oauth_manager = ChzzkOAuthManager(
                client_id=chzzk_config.client_id,
                client_secret=chzzk_config.client_secret,
                redirect_uri=chzzk_config.redirect_uri,
            )

            # Generate authorization URL
            auth_url = oauth_manager.generate_auth_url()

            logger.info(f"[Chzzk] Redirecting to authorization URL: {auth_url}")

            # Redirect user to Chzzk authorization page
            return RedirectResponse(url=auth_url)

        except Exception as e:
            logger.error(f"[Chzzk] Error initiating OAuth: {e}")
            return HTMLResponse(
                content=f"<h1>Error</h1><p>Failed to initiate OAuth: {str(e)}</p>",
                status_code=500,
            )

    @router.get("/chzzk/callback")
    async def chzzk_auth_callback(code: str, state: str = None):
        """
        Handle Chzzk OAuth callback.

        Args:
            code: Authorization code from Chzzk
            state: Optional state parameter for CSRF protection

        Returns:
            Success or error message
        """
        try:
            # Get Chzzk config from default context
            chzzk_config = default_context_cache.config.live_config.chat_monitor.chzzk

            if not chzzk_config.client_id or not chzzk_config.client_secret:
                return HTMLResponse(
                    content="<h1>Error</h1><p>Chzzk OAuth credentials not configured.</p>",
                    status_code=400,
                )

            # Create OAuth manager
            oauth_manager = ChzzkOAuthManager(
                client_id=chzzk_config.client_id,
                client_secret=chzzk_config.client_secret,
                redirect_uri=chzzk_config.redirect_uri,
            )

            # Exchange code for tokens
            logger.info("[Chzzk] Exchanging authorization code for tokens...")
            await oauth_manager.exchange_code(code)

            logger.success(
                "[Chzzk] OAuth authentication successful! Tokens have been saved to cache/chzzk_tokens.json"
            )

            # Return success message with instructions
            return HTMLResponse(
                content="""
                <html>
                <head>
                    <title>Chzzk OAuth Success</title>
                    <style>
                        body {
                            font-family: Arial, sans-serif;
                            max-width: 600px;
                            margin: 50px auto;
                            padding: 20px;
                            background-color: #f5f5f5;
                        }
                        .success {
                            background-color: #d4edda;
                            border: 1px solid #c3e6cb;
                            color: #155724;
                            padding: 20px;
                            border-radius: 5px;
                        }
                        h1 { margin-top: 0; }
                        code {
                            background-color: #f8f9fa;
                            padding: 2px 6px;
                            border-radius: 3px;
                            font-family: monospace;
                        }
                        .next-steps {
                            margin-top: 20px;
                            padding: 15px;
                            background-color: white;
                            border-radius: 5px;
                        }
                    </style>
                </head>
                <body>
                    <div class="success">
                        <h1>✅ Chzzk OAuth Authentication Successful!</h1>
                        <p>Your OAuth tokens have been saved successfully.</p>

                        <div class="next-steps">
                            <h2>Next Steps:</h2>
                            <ol>
                                <li>The tokens are saved in <code>cache/chzzk_tokens.json</code></li>
                                <li>Make sure <code>chat_monitor.chzzk.enabled</code> is set to <code>true</code> in <code>conf.yaml</code></li>
                                <li>Restart the Open-LLM-VTuber server if it's running</li>
                                <li>Chzzk chat monitoring will start automatically when you begin streaming</li>
                            </ol>
                        </div>

                        <p style="margin-top: 20px;">
                            <strong>Note:</strong> If the tokens expire, you can re-authenticate by visiting
                            <code>/chzzk/auth</code> again.
                        </p>
                    </div>
                </body>
                </html>
                """,
                status_code=200,
            )

        except Exception as e:
            logger.error(f"[Chzzk] OAuth callback error: {e}")
            return HTMLResponse(
                content=f"""
                <html>
                <head>
                    <title>Chzzk OAuth Error</title>
                    <style>
                        body {{
                            font-family: Arial, sans-serif;
                            max-width: 600px;
                            margin: 50px auto;
                            padding: 20px;
                            background-color: #f5f5f5;
                        }}
                        .error {{
                            background-color: #f8d7da;
                            border: 1px solid #f5c6cb;
                            color: #721c24;
                            padding: 20px;
                            border-radius: 5px;
                        }}
                    </style>
                </head>
                <body>
                    <div class="error">
                        <h1>❌ OAuth Authentication Failed</h1>
                        <p><strong>Error:</strong> {str(e)}</p>
                        <p>Please try again by visiting <code>/chzzk/auth</code></p>
                    </div>
                </body>
                </html>
                """,
                status_code=500,
            )

    @router.get("/live2d-models/info")
    async def get_live2d_folder_info():
        """Get information about available Live2D models"""
        live2d_dir = "live2d-models"
        if not os.path.exists(live2d_dir):
            return JSONResponse(
                {"error": "Live2D models directory not found"}, status_code=404
            )

        valid_characters = []
        supported_extensions = [".png", ".jpg", ".jpeg"]

        for entry in os.scandir(live2d_dir):
            if entry.is_dir():
                folder_name = entry.name.replace("\\", "/")
                model3_file = os.path.join(
                    live2d_dir, folder_name, f"{folder_name}.model3.json"
                ).replace("\\", "/")

                if os.path.isfile(model3_file):
                    # Find avatar file if it exists
                    avatar_file = None
                    for ext in supported_extensions:
                        avatar_path = os.path.join(
                            live2d_dir, folder_name, f"{folder_name}{ext}"
                        )
                        if os.path.isfile(avatar_path):
                            avatar_file = avatar_path.replace("\\", "/")
                            break

                    valid_characters.append(
                        {
                            "name": folder_name,
                            "avatar": avatar_file,
                            "model_path": model3_file,
                        }
                    )
        return JSONResponse(
            {
                "type": "live2d-models/info",
                "count": len(valid_characters),
                "characters": valid_characters,
            }
        )

    @router.post("/asr")
    async def transcribe_audio(file: UploadFile = File(...)):
        """
        Endpoint for transcribing audio using the ASR engine
        """
        logger.info(f"Received audio file for transcription: {file.filename}")

        try:
            contents = await file.read()

            # Validate minimum file size
            if len(contents) < WAV_HEADER_SIZE_BYTES:
                raise ValueError("Invalid WAV file: File too small")

            # Decode the WAV header and get actual audio data
            wav_header_size = WAV_HEADER_SIZE_BYTES
            audio_data = contents[wav_header_size:]

            # Validate audio data size
            if len(audio_data) % 2 != 0:
                raise ValueError("Invalid audio data: Buffer size must be even")

            # Convert to 16-bit PCM samples to float32
            try:
                audio_array = (
                    np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
                    / INT16_TO_FLOAT32_DIVISOR
                )
            except ValueError as e:
                raise ValueError(
                    f"Audio format error: {str(e)}. Please ensure the file is 16-bit PCM WAV format."
                )

            # Validate audio data
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
        """WebSocket endpoint for TTS generation"""
        await websocket.accept()
        logger.info("TTS WebSocket connection established")

        try:
            while True:
                data = await websocket.receive_json()
                text = data.get("text")
                if not text:
                    continue

                logger.info(f"Received text for TTS: {text}")

                # Split text into sentences
                sentences = [s.strip() for s in text.split(".") if s.strip()]

                try:
                    # Generate and send audio for each sentence
                    for sentence in sentences:
                        sentence = sentence + "."  # Add back the period
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

                    # Send completion signal
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
