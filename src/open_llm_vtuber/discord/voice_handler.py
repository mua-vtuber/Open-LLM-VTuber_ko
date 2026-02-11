"""
Discord voice handler for STT/TTS integration.

This module bridges Discord voice with the AI system:
- Receives voice data from DiscordVoiceMonitor
- Converts to text using ASR (STT)
- Sends to AI for response
- Converts response to audio using TTS
- Plays back in voice channel
"""

from __future__ import annotations

import asyncio
import io
import wave
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

from loguru import logger

from ..chat_monitor.discord_voice_monitor import (
    DiscordVoiceMonitor,
    VoiceActivity,
    DISCORD_VOICE_AVAILABLE,
)
from ..chat_monitor.chat_monitor_interface import ChatMessage
from ..visitor_profiles import ProfileManager


@dataclass
class VoiceInteraction:
    """Record of a voice interaction."""

    user_id: str
    user_name: str
    input_text: str
    response_text: str
    timestamp: datetime
    input_duration: float
    processing_time: float


class DiscordVoiceHandler:
    """
    Handles Discord voice interactions with AI.

    Flow:
    1. Receive voice data from DiscordVoiceMonitor
    2. Convert to WAV format for ASR
    3. Run STT to get transcription
    4. Create ChatMessage and send to AI
    5. Get AI response
    6. Run TTS to generate audio
    7. Play audio in voice channel
    """

    # Audio format for ASR (most ASR models expect 16kHz mono)
    ASR_SAMPLE_RATE = 16000
    ASR_CHANNELS = 1

    def __init__(
        self,
        voice_monitor: DiscordVoiceMonitor,
        asr_engine: Any,  # ASRInterface
        tts_engine: Any,  # TTSInterface
        message_callback: Callable[[ChatMessage], str],
        profile_manager: Optional[ProfileManager] = None,
        enable_profiles: bool = True,
    ):
        """
        Initialize voice handler.

        Args:
            voice_monitor: Discord voice monitor instance
            asr_engine: ASR engine for speech-to-text
            tts_engine: TTS engine for text-to-speech
            message_callback: Callback to process message and get AI response
            profile_manager: Optional profile manager for visitor tracking
            enable_profiles: Enable visitor profile tracking
        """
        self.voice_monitor = voice_monitor
        self.asr_engine = asr_engine
        self.tts_engine = tts_engine
        self.message_callback = message_callback

        # Profile management
        self.enable_profiles = enable_profiles
        if enable_profiles:
            self.profile_manager = profile_manager or ProfileManager()
        else:
            self.profile_manager = None

        # State
        self._processing = False
        self._interaction_history: list[VoiceInteraction] = []

        # Set up the voice monitor callback
        self.voice_monitor.speech_callback = self.on_speech_received

    async def on_speech_received(self, activity: VoiceActivity) -> None:
        """
        Handle received speech from voice channel.

        Args:
            activity: Voice activity data
        """
        if self._processing:
            logger.debug("[VoiceHandler] Already processing, queuing...")
            # Could implement a queue here for multiple speakers
            return

        self._processing = True
        start_time = datetime.now()

        try:
            logger.info(
                f"[VoiceHandler] Processing speech from {activity.user_name} "
                f"({activity.duration_seconds:.2f}s)"
            )

            # 1. Convert audio format for ASR
            wav_data = self._convert_to_wav(
                activity.audio_data,
                source_rate=48000,  # Discord uses 48kHz
                source_channels=2,  # Discord uses stereo
                target_rate=self.ASR_SAMPLE_RATE,
                target_channels=self.ASR_CHANNELS,
            )

            if not wav_data:
                logger.warning("[VoiceHandler] Failed to convert audio format")
                return

            # 2. Run STT
            transcription = await self._run_stt(wav_data)

            if not transcription or transcription.strip() == "":
                logger.debug("[VoiceHandler] Empty transcription, ignoring")
                return

            logger.info(f"[VoiceHandler] Transcription: {transcription}")

            # 3. Update visitor profile
            profile_context = ""
            if self.profile_manager:
                user_id = str(activity.user_id)
                self.profile_manager.update_visit(
                    platform="discord_voice",
                    user_id=user_id,
                    identifier=activity.user_name,
                )
                self.profile_manager.record_message("discord_voice", user_id)
                profile_context = self.profile_manager.get_context_for_ai(
                    "discord_voice", user_id
                )

            # 4. Create ChatMessage
            chat_message = ChatMessage(
                platform="discord_voice",
                author=activity.user_name,
                message=transcription,
                timestamp=activity.timestamp.isoformat(),
                user_id=str(activity.user_id),
                is_moderator=False,
                is_owner=False,
                is_member=True,
                badges={"profile_context": profile_context} if profile_context else {},
                priority=5,  # Normal priority for voice
            )

            # 5. Get AI response
            response_text = await self._get_ai_response(chat_message)

            if not response_text:
                logger.warning("[VoiceHandler] No response from AI")
                return

            logger.info(f"[VoiceHandler] AI response: {response_text[:100]}...")

            # 6. Run TTS
            audio_data = await self._run_tts(response_text)

            if not audio_data:
                logger.warning("[VoiceHandler] Failed to generate TTS audio")
                return

            # 7. Play audio in voice channel
            await self.voice_monitor.play_audio(audio_data)

            # Record interaction
            processing_time = (datetime.now() - start_time).total_seconds()
            interaction = VoiceInteraction(
                user_id=str(activity.user_id),
                user_name=activity.user_name,
                input_text=transcription,
                response_text=response_text,
                timestamp=activity.timestamp,
                input_duration=activity.duration_seconds,
                processing_time=processing_time,
            )
            self._interaction_history.append(interaction)

            # Keep only last 100 interactions
            if len(self._interaction_history) > 100:
                self._interaction_history = self._interaction_history[-100:]

            logger.info(
                f"[VoiceHandler] Completed voice interaction "
                f"(processing time: {processing_time:.2f}s)"
            )

        except Exception as e:
            logger.error(f"[VoiceHandler] Error processing speech: {e}")
        finally:
            self._processing = False

    def _convert_to_wav(
        self,
        pcm_data: bytes,
        source_rate: int,
        source_channels: int,
        target_rate: int,
        target_channels: int,
    ) -> Optional[bytes]:
        """
        Convert PCM audio to WAV format for ASR.

        Args:
            pcm_data: Raw PCM audio data
            source_rate: Source sample rate
            source_channels: Source channel count
            target_rate: Target sample rate
            target_channels: Target channel count

        Returns:
            WAV audio data or None on error
        """
        try:
            # For now, just wrap in WAV header
            # In production, you'd want to use scipy or librosa for resampling
            buffer = io.BytesIO()

            with wave.open(buffer, "wb") as wav_file:
                wav_file.setnchannels(source_channels)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(source_rate)
                wav_file.writeframes(pcm_data)

            return buffer.getvalue()

        except Exception as e:
            logger.error(f"[VoiceHandler] Audio conversion error: {e}")
            return None

    async def _run_stt(self, audio_data: bytes) -> Optional[str]:
        """
        Run speech-to-text on audio data.

        Args:
            audio_data: WAV audio data

        Returns:
            Transcribed text or None
        """
        try:
            if hasattr(self.asr_engine, "transcribe_bytes"):
                # If ASR supports byte input
                if asyncio.iscoroutinefunction(self.asr_engine.transcribe_bytes):
                    result = await self.asr_engine.transcribe_bytes(audio_data)
                else:
                    result = await asyncio.to_thread(
                        self.asr_engine.transcribe_bytes, audio_data
                    )
            elif hasattr(self.asr_engine, "transcribe"):
                # Standard transcribe method
                if asyncio.iscoroutinefunction(self.asr_engine.transcribe):
                    result = await self.asr_engine.transcribe(audio_data)
                else:
                    result = await asyncio.to_thread(
                        self.asr_engine.transcribe, audio_data
                    )
            else:
                logger.error("[VoiceHandler] ASR engine has no transcribe method")
                return None

            return result

        except Exception as e:
            logger.error(f"[VoiceHandler] STT error: {e}")
            return None

    async def _get_ai_response(self, message: ChatMessage) -> Optional[str]:
        """
        Get AI response for a message.

        Args:
            message: Chat message to process

        Returns:
            AI response text or None
        """
        try:
            if asyncio.iscoroutinefunction(self.message_callback):
                return await self.message_callback(message)
            else:
                return await asyncio.to_thread(self.message_callback, message)

        except Exception as e:
            logger.error(f"[VoiceHandler] AI response error: {e}")
            return None

    async def _run_tts(self, text: str) -> Optional[bytes]:
        """
        Run text-to-speech on text.

        Args:
            text: Text to convert to speech

        Returns:
            Audio data or None
        """
        try:
            if hasattr(self.tts_engine, "synthesize"):
                if asyncio.iscoroutinefunction(self.tts_engine.synthesize):
                    result = await self.tts_engine.synthesize(text)
                else:
                    result = await asyncio.to_thread(self.tts_engine.synthesize, text)
                return result

            elif hasattr(self.tts_engine, "generate_audio"):
                if asyncio.iscoroutinefunction(self.tts_engine.generate_audio):
                    result = await self.tts_engine.generate_audio(text)
                else:
                    result = await asyncio.to_thread(
                        self.tts_engine.generate_audio, text
                    )
                return result

            else:
                logger.error("[VoiceHandler] TTS engine has no synthesis method")
                return None

        except Exception as e:
            logger.error(f"[VoiceHandler] TTS error: {e}")
            return None

    def get_interaction_history(self) -> list[VoiceInteraction]:
        """Get voice interaction history."""
        return self._interaction_history.copy()

    def get_statistics(self) -> dict:
        """Get voice handler statistics."""
        if not self._interaction_history:
            return {
                "total_interactions": 0,
                "average_processing_time": 0,
                "average_input_duration": 0,
            }

        return {
            "total_interactions": len(self._interaction_history),
            "average_processing_time": sum(
                i.processing_time for i in self._interaction_history
            )
            / len(self._interaction_history),
            "average_input_duration": sum(
                i.input_duration for i in self._interaction_history
            )
            / len(self._interaction_history),
        }


class DiscordVoiceIntegration:
    """
    High-level integration class for Discord voice functionality.

    Combines DiscordVoiceMonitor and DiscordVoiceHandler
    for easy setup and use.
    """

    def __init__(
        self,
        bot: Any,
        voice_channel_id: int,
        asr_engine: Any,
        tts_engine: Any,
        message_callback: Callable[[ChatMessage], str],
        profile_manager: Optional[ProfileManager] = None,
        silence_threshold: int = 500,
        speech_timeout: float = 1.5,
    ):
        """
        Initialize voice integration.

        Args:
            bot: Discord bot instance
            voice_channel_id: Voice channel ID to join
            asr_engine: ASR engine for speech-to-text
            tts_engine: TTS engine for text-to-speech
            message_callback: Callback to process message and get AI response
            profile_manager: Optional profile manager
            silence_threshold: VAD silence threshold
            speech_timeout: Seconds of silence before speech ends
        """
        if not DISCORD_VOICE_AVAILABLE:
            raise RuntimeError(
                "discord.py[voice] is not installed. "
                "Install with: pip install discord.py[voice]"
            )

        # Create voice monitor
        self.voice_monitor = DiscordVoiceMonitor(
            bot=bot,
            voice_channel_id=voice_channel_id,
            speech_callback=lambda x: None,  # Will be replaced by handler
            silence_threshold=silence_threshold,
            speech_timeout=speech_timeout,
        )

        # Create voice handler
        self.voice_handler = DiscordVoiceHandler(
            voice_monitor=self.voice_monitor,
            asr_engine=asr_engine,
            tts_engine=tts_engine,
            message_callback=message_callback,
            profile_manager=profile_manager,
        )

        self._connected = False

    async def connect(self) -> bool:
        """Connect to voice channel and start processing."""
        success = await self.voice_monitor.connect()
        self._connected = success
        return success

    async def disconnect(self) -> None:
        """Disconnect from voice channel."""
        await self.voice_monitor.disconnect()
        self._connected = False

    def is_connected(self) -> bool:
        """Check if connected to voice channel."""
        return self._connected and self.voice_monitor.is_connected()

    async def play_audio(self, audio_data: bytes) -> bool:
        """Play audio in voice channel."""
        return await self.voice_monitor.play_audio(audio_data)

    async def play_file(self, file_path: str) -> bool:
        """Play audio file in voice channel."""
        return await self.voice_monitor.play_file(file_path)

    def stop_playback(self) -> None:
        """Stop current audio playback."""
        self.voice_monitor.stop_playback()

    def get_statistics(self) -> dict:
        """Get voice handler statistics."""
        return self.voice_handler.get_statistics()
