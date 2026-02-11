"""
Discord integration module.

Provides:
- Community management, FAQ auto-response, and moderation features
- Voice channel integration with STT/TTS
"""

from .community_manager import DiscordCommunityManager
from .voice_handler import (
    DiscordVoiceHandler,
    DiscordVoiceIntegration,
    VoiceInteraction,
)

__all__ = [
    "DiscordCommunityManager",
    "DiscordVoiceHandler",
    "DiscordVoiceIntegration",
    "VoiceInteraction",
]
