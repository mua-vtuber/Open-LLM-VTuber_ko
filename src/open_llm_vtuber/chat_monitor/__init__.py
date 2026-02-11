"""
Chat monitoring module for live streaming platforms.

This module provides real-time chat monitoring for YouTube, Chzzk, and Discord platforms,
integrating with the Open-LLM-VTuber conversation system.
"""

from .chat_monitor_interface import ChatMonitorInterface, ChatMessage
from .chat_monitor_manager import ChatMonitorManager
from .discord_chat_monitor import DiscordChatMonitor, DISCORD_AVAILABLE
from .discord_voice_monitor import (
    DiscordVoiceMonitor,
    VoiceActivity,
    DISCORD_VOICE_AVAILABLE,
)

__all__ = [
    "ChatMonitorInterface",
    "ChatMessage",
    "ChatMonitorManager",
    "DiscordChatMonitor",
    "DISCORD_AVAILABLE",
    "DiscordVoiceMonitor",
    "VoiceActivity",
    "DISCORD_VOICE_AVAILABLE",
]
