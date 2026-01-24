"""
Discord voice channel monitor for real-time voice interaction.

This module provides voice channel integration including:
- Voice activity detection (VAD)
- Audio reception from multiple speakers
- Audio playback for AI responses
"""

from __future__ import annotations

import asyncio
import io
import struct
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

# Discord imports are optional
try:
    import discord

    DISCORD_VOICE_AVAILABLE = True
except ImportError:
    DISCORD_VOICE_AVAILABLE = False
    discord = None  # type: ignore
    logger.warning(
        "[Discord Voice] discord.py not installed. Install with: pip install discord.py[voice]"
    )


@dataclass
class VoiceActivity:
    """Voice activity information from a speaker."""

    user_id: int
    user_name: str
    audio_data: bytes
    timestamp: datetime
    duration_seconds: float
    rms_level: float


@dataclass
class SpeakerState:
    """State tracking for a speaker in voice channel."""

    user_id: int
    user_name: str
    is_speaking: bool = False
    speech_start: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    audio_buffer: List[bytes] = field(default_factory=list)
    total_samples: int = 0


class DiscordVoiceMonitor:
    """
    Discord voice channel monitor with VAD and audio processing.

    Features:
    - Connect to voice channels
    - Detect voice activity per speaker
    - Buffer and process speech segments
    - Play audio responses
    """

    # Audio settings (Discord uses 48kHz, 16-bit, stereo)
    SAMPLE_RATE = 48000
    CHANNELS = 2
    SAMPLE_WIDTH = 2  # 16-bit

    # VAD settings
    SILENCE_THRESHOLD = 500  # RMS threshold for silence detection
    SPEECH_TIMEOUT = 1.5  # Seconds of silence before speech ends
    MIN_SPEECH_DURATION = 0.3  # Minimum speech duration to process
    MAX_SPEECH_DURATION = 30.0  # Maximum speech duration (prevent infinite buffer)

    def __init__(
        self,
        bot: Any,  # discord.Client or commands.Bot
        voice_channel_id: int,
        speech_callback: Callable[[VoiceActivity], None],
        silence_threshold: int = 500,
        speech_timeout: float = 1.5,
        min_speech_duration: float = 0.3,
    ):
        """
        Initialize voice monitor.

        Args:
            bot: Discord bot instance
            voice_channel_id: Voice channel ID to join
            speech_callback: Callback when speech is detected (receives VoiceActivity)
            silence_threshold: RMS threshold for silence detection
            speech_timeout: Seconds of silence before speech ends
            min_speech_duration: Minimum speech duration to process
        """
        if not DISCORD_VOICE_AVAILABLE:
            raise RuntimeError(
                "discord.py[voice] is not installed. "
                "Install with: pip install discord.py[voice]"
            )

        self.bot = bot
        self.voice_channel_id = voice_channel_id
        self.speech_callback = speech_callback

        # VAD settings
        self.SILENCE_THRESHOLD = silence_threshold
        self.SPEECH_TIMEOUT = speech_timeout
        self.MIN_SPEECH_DURATION = min_speech_duration

        # State
        self._voice_client: Optional[discord.VoiceClient] = None
        self._connected = False
        self._speakers: Dict[int, SpeakerState] = {}
        self._silence_check_task: Optional[asyncio.Task] = None
        self._is_playing = False

    async def connect(self) -> bool:
        """
        Connect to the voice channel.

        Returns:
            True if connection successful
        """
        try:
            channel = self.bot.get_channel(self.voice_channel_id)

            if not channel:
                logger.error(
                    f"[Discord Voice] Channel {self.voice_channel_id} not found"
                )
                return False

            if not isinstance(channel, discord.VoiceChannel):
                logger.error(
                    f"[Discord Voice] Channel {self.voice_channel_id} is not a voice channel"
                )
                return False

            # Connect to voice channel
            self._voice_client = await channel.connect()

            # Start listening for voice data
            self._setup_voice_receive()

            # Start silence check task
            self._silence_check_task = asyncio.create_task(self._check_silence_loop())

            self._connected = True
            logger.info(f"[Discord Voice] Connected to {channel.name}")
            return True

        except discord.ClientException as e:
            logger.error(f"[Discord Voice] Already connected or error: {e}")
            return False
        except Exception as e:
            logger.error(f"[Discord Voice] Failed to connect: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from voice channel."""
        if self._silence_check_task:
            self._silence_check_task.cancel()
            try:
                await self._silence_check_task
            except asyncio.CancelledError:
                pass

        if self._voice_client and self._voice_client.is_connected():
            await self._voice_client.disconnect()

        self._connected = False
        self._speakers.clear()
        logger.info("[Discord Voice] Disconnected from voice channel")

    def is_connected(self) -> bool:
        """Check if connected to voice channel."""
        return (
            self._connected
            and self._voice_client is not None
            and self._voice_client.is_connected()
        )

    def _setup_voice_receive(self) -> None:
        """Setup voice receive callback."""
        if not self._voice_client:
            return

        # Note: discord.py requires additional setup for voice receive
        # Using a custom sink for audio reception
        # This requires discord-ext-voice-recv or similar extension

        # For now, we'll use the basic approach with on_voice_state_update
        # Full voice receive requires additional dependencies
        logger.info("[Discord Voice] Voice receive setup - using event-based detection")

    async def _check_silence_loop(self) -> None:
        """Background task to check for speech end by silence."""
        while self._connected:
            try:
                await asyncio.sleep(0.1)  # Check every 100ms

                now = datetime.now()
                speakers_to_process = []

                for user_id, state in list(self._speakers.items()):
                    if not state.is_speaking:
                        continue

                    if state.last_activity is None:
                        continue

                    silence_duration = (now - state.last_activity).total_seconds()

                    # Check for speech timeout
                    if silence_duration > self.SPEECH_TIMEOUT:
                        speakers_to_process.append(user_id)

                # Process completed speeches
                for user_id in speakers_to_process:
                    await self._process_speech_end(user_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Discord Voice] Silence check error: {e}")

    def on_voice_receive(self, user: Any, data: bytes) -> None:
        """
        Handle received voice data.

        Args:
            user: Discord user who sent the audio
            data: PCM audio data
        """
        # Ignore bot's own audio
        if user.id == self.bot.user.id:
            return

        # Ignore if we're playing audio (prevent feedback)
        if self._is_playing:
            return

        user_id = user.id
        user_name = user.display_name if hasattr(user, "display_name") else str(user)

        # Calculate RMS level
        rms = self._calculate_rms(data)

        now = datetime.now()

        # Get or create speaker state
        if user_id not in self._speakers:
            self._speakers[user_id] = SpeakerState(
                user_id=user_id,
                user_name=user_name,
            )

        state = self._speakers[user_id]

        # Voice activity detection
        if rms > self.SILENCE_THRESHOLD:
            # Speech detected
            if not state.is_speaking:
                # Speech start
                state.is_speaking = True
                state.speech_start = now
                state.audio_buffer = []
                state.total_samples = 0
                logger.debug(f"[Discord Voice] {user_name} started speaking")

            # Add audio to buffer
            state.audio_buffer.append(data)
            state.total_samples += len(data) // (self.SAMPLE_WIDTH * self.CHANNELS)
            state.last_activity = now

            # Check for max duration
            if state.speech_start:
                duration = (now - state.speech_start).total_seconds()
                if duration > self.MAX_SPEECH_DURATION:
                    logger.warning(
                        f"[Discord Voice] {user_name} exceeded max speech duration"
                    )
                    asyncio.create_task(self._process_speech_end(user_id))

        else:
            # Silence - update last activity for timeout check
            if state.is_speaking:
                state.last_activity = now

    async def _process_speech_end(self, user_id: int) -> None:
        """Process end of speech for a user."""
        if user_id not in self._speakers:
            return

        state = self._speakers[user_id]

        if not state.is_speaking or not state.speech_start:
            return

        # Calculate duration
        duration = (datetime.now() - state.speech_start).total_seconds()

        # Reset state
        state.is_speaking = False
        audio_data = b"".join(state.audio_buffer)
        state.audio_buffer = []

        # Check minimum duration
        if duration < self.MIN_SPEECH_DURATION:
            logger.debug(
                f"[Discord Voice] {state.user_name} speech too short "
                f"({duration:.2f}s), ignoring"
            )
            return

        if not audio_data:
            return

        logger.info(
            f"[Discord Voice] {state.user_name} finished speaking "
            f"(duration: {duration:.2f}s, size: {len(audio_data)} bytes)"
        )

        # Create voice activity
        activity = VoiceActivity(
            user_id=user_id,
            user_name=state.user_name,
            audio_data=audio_data,
            timestamp=state.speech_start,
            duration_seconds=duration,
            rms_level=self._calculate_rms(audio_data),
        )

        # Call speech callback
        try:
            if asyncio.iscoroutinefunction(self.speech_callback):
                await self.speech_callback(activity)
            else:
                await asyncio.to_thread(self.speech_callback, activity)
        except Exception as e:
            logger.error(f"[Discord Voice] Speech callback error: {e}")

    def _calculate_rms(self, audio_data: bytes) -> float:
        """
        Calculate RMS (Root Mean Square) level of audio data.

        Args:
            audio_data: PCM audio data (16-bit, stereo)

        Returns:
            RMS level
        """
        if len(audio_data) < 4:
            return 0.0

        try:
            # Unpack as 16-bit signed integers
            num_samples = len(audio_data) // 2
            samples = struct.unpack(f"<{num_samples}h", audio_data)

            if not samples:
                return 0.0

            # Calculate RMS
            sum_squares = sum(s * s for s in samples)
            rms = (sum_squares / len(samples)) ** 0.5

            return rms
        except Exception:
            return 0.0

    async def play_audio(
        self,
        audio_data: bytes,
        sample_rate: int = 48000,
        channels: int = 2,
    ) -> bool:
        """
        Play audio in the voice channel.

        Args:
            audio_data: PCM audio data
            sample_rate: Audio sample rate (default 48000 for Discord)
            channels: Number of audio channels (default 2 for stereo)

        Returns:
            True if audio was played successfully
        """
        if not self.is_connected():
            logger.warning("[Discord Voice] Cannot play audio - not connected")
            return False

        if self._voice_client.is_playing():
            logger.debug("[Discord Voice] Already playing audio, waiting...")
            while self._voice_client.is_playing():
                await asyncio.sleep(0.1)

        try:
            self._is_playing = True

            # Create audio source from PCM data
            audio_source = discord.PCMAudio(io.BytesIO(audio_data))

            # Play audio
            self._voice_client.play(
                audio_source,
                after=lambda e: self._on_play_complete(e),
            )

            # Wait for playback to complete
            while self._voice_client.is_playing():
                await asyncio.sleep(0.1)

            return True

        except Exception as e:
            logger.error(f"[Discord Voice] Failed to play audio: {e}")
            return False
        finally:
            self._is_playing = False

    def _on_play_complete(self, error: Optional[Exception]) -> None:
        """Callback when audio playback completes."""
        self._is_playing = False
        if error:
            logger.error(f"[Discord Voice] Playback error: {error}")

    async def play_file(self, file_path: str) -> bool:
        """
        Play an audio file in the voice channel.

        Args:
            file_path: Path to audio file (supports formats FFmpeg can decode)

        Returns:
            True if audio was played successfully
        """
        if not self.is_connected():
            logger.warning("[Discord Voice] Cannot play file - not connected")
            return False

        if self._voice_client.is_playing():
            logger.debug("[Discord Voice] Already playing audio, waiting...")
            while self._voice_client.is_playing():
                await asyncio.sleep(0.1)

        try:
            self._is_playing = True

            # Create FFmpeg audio source
            audio_source = discord.FFmpegPCMAudio(file_path)

            # Play audio
            self._voice_client.play(
                audio_source,
                after=lambda e: self._on_play_complete(e),
            )

            # Wait for playback to complete
            while self._voice_client.is_playing():
                await asyncio.sleep(0.1)

            return True

        except Exception as e:
            logger.error(f"[Discord Voice] Failed to play file: {e}")
            return False
        finally:
            self._is_playing = False

    def stop_playback(self) -> None:
        """Stop current audio playback."""
        if self._voice_client and self._voice_client.is_playing():
            self._voice_client.stop()
            self._is_playing = False

    def get_active_speakers(self) -> List[str]:
        """Get list of currently speaking users."""
        return [
            state.user_name for state in self._speakers.values() if state.is_speaking
        ]

    def get_connected_users(self) -> List[Dict[str, Any]]:
        """Get list of users in the voice channel."""
        if not self._voice_client or not self._voice_client.channel:
            return []

        return [
            {
                "id": member.id,
                "name": member.display_name,
                "is_bot": member.bot,
            }
            for member in self._voice_client.channel.members
        ]
