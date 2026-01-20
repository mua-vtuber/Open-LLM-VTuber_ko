"""
Chat monitor manager for coordinating multiple platform monitors.
"""

import asyncio
from typing import Optional, Callable, Dict
from loguru import logger

from ..config_manager import ChatMonitorConfig, YouTubeChatConfig, ChzzkChatConfig
from .chat_monitor_interface import ChatMonitorInterface, ChatMessage
from .youtube_chat_monitor import YouTubeChatMonitor
from .chzzk_chat_monitor import ChzzkChatMonitor


class ChatMonitorManager:
    """
    Manager class that coordinates multiple chat monitors across different platforms.

    This class handles initialization, lifecycle management, and message routing
    for YouTube and Chzzk chat monitors.
    """

    def __init__(
        self, config: ChatMonitorConfig, message_callback: Callable[[ChatMessage], None]
    ):
        """
        Initialize the chat monitor manager.

        Args:
            config: Chat monitoring configuration
            message_callback: Function to call when a new message is received from any platform
        """
        self.config = config
        self.message_callback = message_callback
        self.monitors: Dict[str, ChatMonitorInterface] = {}
        self.is_running = False
        self._monitor_tasks: Dict[str, asyncio.Task] = {}

    def _create_youtube_monitor(
        self, youtube_config: YouTubeChatConfig
    ) -> Optional[YouTubeChatMonitor]:
        """
        Create a YouTube chat monitor instance.

        Args:
            youtube_config: YouTube configuration

        Returns:
            Optional[YouTubeChatMonitor]: Monitor instance or None if configuration is invalid
        """
        if not youtube_config.enabled:
            logger.debug("[ChatMonitor] YouTube monitoring is disabled")
            return None

        if not youtube_config.api_key or not youtube_config.channel_id:
            logger.warning(
                "[ChatMonitor] YouTube API key or channel ID not configured, skipping YouTube monitor"
            )
            return None

        try:
            monitor = YouTubeChatMonitor(
                api_key=youtube_config.api_key,
                channel_id=youtube_config.channel_id,
                message_callback=self.message_callback,
                max_retries=self.config.max_retries,
                retry_interval=self.config.retry_interval,
            )
            logger.info("[ChatMonitor] YouTube monitor created")
            return monitor
        except Exception as e:
            logger.error(f"[ChatMonitor] Failed to create YouTube monitor: {e}")
            return None

    def _create_chzzk_monitor(
        self, chzzk_config: ChzzkChatConfig
    ) -> Optional[ChzzkChatMonitor]:
        """
        Create a Chzzk chat monitor instance with OAuth2 authentication.

        Args:
            chzzk_config: Chzzk configuration

        Returns:
            Optional[ChzzkChatMonitor]: Monitor instance or None if configuration is invalid
        """
        if not chzzk_config.enabled:
            logger.debug("[ChatMonitor] Chzzk monitoring is disabled")
            return None

        if not chzzk_config.channel_id:
            logger.warning(
                "[ChatMonitor] Chzzk channel ID not configured, skipping Chzzk monitor"
            )
            return None

        if not chzzk_config.client_id or not chzzk_config.client_secret:
            logger.warning(
                "[ChatMonitor] Chzzk OAuth credentials not configured, skipping Chzzk monitor"
            )
            return None

        try:
            monitor = ChzzkChatMonitor(
                channel_id=chzzk_config.channel_id,
                client_id=chzzk_config.client_id,
                client_secret=chzzk_config.client_secret,
                redirect_uri=chzzk_config.redirect_uri,
                access_token=chzzk_config.access_token
                if chzzk_config.access_token
                else None,
                refresh_token=chzzk_config.refresh_token
                if chzzk_config.refresh_token
                else None,
                message_callback=self.message_callback,
                max_retries=self.config.max_retries,
                retry_interval=self.config.retry_interval,
            )
            logger.info("[ChatMonitor] Chzzk monitor created")
            return monitor
        except RuntimeError as e:
            # Python version error
            logger.error(f"[ChatMonitor] {e}")
            return None
        except Exception as e:
            logger.error(f"[ChatMonitor] Failed to create Chzzk monitor: {e}")
            return None

    async def initialize(self) -> bool:
        """
        Initialize all configured chat monitors.

        Returns:
            bool: True if at least one monitor was initialized successfully
        """
        if not self.config.enabled:
            logger.info("[ChatMonitor] Chat monitoring is disabled in configuration")
            return False

        logger.info("=" * 60)
        logger.info("[ChatMonitor] Initializing chat monitoring system")
        logger.info("=" * 60)

        # Create YouTube monitor
        youtube_monitor = self._create_youtube_monitor(self.config.youtube)
        if youtube_monitor:
            self.monitors["youtube"] = youtube_monitor

        # Create Chzzk monitor
        chzzk_monitor = self._create_chzzk_monitor(self.config.chzzk)
        if chzzk_monitor:
            self.monitors["chzzk"] = chzzk_monitor

        if not self.monitors:
            logger.warning("[ChatMonitor] No monitors were initialized")
            return False

        logger.info(
            f"[ChatMonitor] Initialized {len(self.monitors)} monitor(s): {list(self.monitors.keys())}"
        )
        return True

    async def start_monitoring(self) -> bool:
        """
        Start all initialized monitors.

        Returns:
            bool: True if at least one monitor started successfully
        """
        if self.is_running:
            logger.warning("[ChatMonitor] Manager is already running")
            return True

        if not self.monitors:
            logger.error("[ChatMonitor] No monitors to start. Call initialize() first.")
            return False

        logger.info("[ChatMonitor] Starting all monitors...")
        self.is_running = True
        started_count = 0

        for platform, monitor in self.monitors.items():
            try:
                success = await monitor.start_monitoring()
                if success:
                    started_count += 1
                    logger.info(f"[ChatMonitor] Started {platform} monitor")
                else:
                    logger.warning(f"[ChatMonitor] Failed to start {platform} monitor")
            except Exception as e:
                logger.error(f"[ChatMonitor] Error starting {platform} monitor: {e}")

        if started_count == 0:
            logger.error("[ChatMonitor] Failed to start any monitors")
            self.is_running = False
            return False

        logger.success(
            f"[ChatMonitor] Successfully started {started_count}/{len(self.monitors)} monitor(s)"
        )
        return True

    async def stop_monitoring(self) -> None:
        """Stop all running monitors."""
        if not self.is_running:
            logger.debug("[ChatMonitor] Manager is not running")
            return

        logger.info("[ChatMonitor] Stopping all monitors...")
        self.is_running = False

        # Stop all monitors
        stop_tasks = []
        for platform, monitor in self.monitors.items():
            try:
                stop_tasks.append(monitor.stop_monitoring())
            except Exception as e:
                logger.error(f"[ChatMonitor] Error stopping {platform} monitor: {e}")

        # Wait for all monitors to stop
        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)

        logger.info("[ChatMonitor] All monitors stopped")

    def get_status(self) -> Dict[str, bool]:
        """
        Get connection status of all monitors.

        Returns:
            Dict[str, bool]: Dictionary mapping platform names to connection status
        """
        return {
            platform: monitor.is_connected()
            for platform, monitor in self.monitors.items()
        }

    def is_any_connected(self) -> bool:
        """
        Check if any monitor is currently connected.

        Returns:
            bool: True if at least one monitor is connected
        """
        return any(monitor.is_connected() for monitor in self.monitors.values())

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        await self.start_monitoring()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop_monitoring()
