"""
Chzzk (치지직) Live Chat monitoring implementation using official OAuth API.

Uses chzzkpy v2 official API with OAuth2 authentication.
"""

import asyncio
import sys
from typing import Optional, Callable
from loguru import logger

from .chat_monitor_interface import ChatMonitorInterface, ChatMessage
from .chzzk_oauth_manager import ChzzkOAuthManager


class ChzzkChatMonitor(ChatMonitorInterface):
    """
    Chzzk Live Chat monitor using official chzzkpy API with OAuth2.

    Note: Requires Python 3.11+
    """

    def __init__(
        self,
        channel_id: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        message_callback: Callable[[ChatMessage], None],
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        max_retries: int = 10,
        retry_interval: int = 60,
    ):
        """
        Initialize Chzzk chat monitor with OAuth2 authentication.

        Args:
            channel_id: Chzzk channel ID to monitor
            client_id: OAuth2 client ID from CHZZK Developer Center
            client_secret: OAuth2 client secret
            redirect_uri: OAuth2 redirect URI
            message_callback: Function to call when a new message is received
            access_token: OAuth2 access token (if already authenticated)
            refresh_token: OAuth2 refresh token (for token refresh)
            max_retries: Maximum number of reconnection attempts
            retry_interval: Interval between retry attempts in seconds
        """
        super().__init__(message_callback, max_retries, retry_interval)
        self.channel_id = channel_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.access_token = access_token
        self.refresh_token = refresh_token

        self._oauth_manager = ChzzkOAuthManager(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
        )
        self._user_client = None
        self._chat_client = None
        self._connected = False
        self._monitoring_task: Optional[asyncio.Task] = None

        # Check Python version
        if sys.version_info < (3, 11):
            logger.error(
                f"[Chzzk] Python 3.11+ required (current: {sys.version_info.major}.{sys.version_info.minor})"
            )
            raise RuntimeError("Python 3.11+ required for chzzkpy")

    async def _ensure_authenticated(self) -> bool:
        """
        Ensure OAuth authentication is valid.

        Returns:
            bool: True if authenticated successfully
        """
        try:
            # Check if we have tokens
            if not self.access_token or not self.refresh_token:
                # Try to load from file
                tokens = self._oauth_manager.load_tokens()
                if tokens:
                    self.access_token = tokens.get("access_token")
                    self.refresh_token = tokens.get("refresh_token")
                    logger.info("[Chzzk] Loaded tokens from cache")
                else:
                    logger.warning(
                        "[Chzzk] No tokens available. Please authenticate via OAuth."
                    )
                    return False

            # Get user client
            self._user_client = await self._oauth_manager.get_user_client(
                access_token=self.access_token, refresh_token=self.refresh_token
            )

            logger.success("[Chzzk] Authentication successful")
            return True

        except Exception as e:
            logger.error(f"[Chzzk] Authentication failed: {e}")
            return False

    async def _on_chat_message(self, message) -> None:
        """
        Internal handler for chat messages from chzzkpy.

        Args:
            message: ChatMessage object from chzzkpy
        """
        try:
            # Extract message information
            # Note: Adjust field names based on actual chzzkpy v2 API structure
            chat_message = self.format_message(
                platform="chzzk",
                author=getattr(message, "nickname", "Unknown"),
                message=getattr(message, "content", ""),
                user_id=getattr(message, "user_id", ""),
                is_moderator=getattr(message, "is_moderator", False),
                is_owner=getattr(message, "is_streamer", False),
            )

            logger.info(f"[Chzzk] {chat_message['author']}: {chat_message['message']}")

            # Call the message callback
            try:
                self.message_callback(chat_message)
            except Exception as e:
                logger.error(f"[Chzzk] Error in message callback: {e}")

        except Exception as e:
            logger.error(f"[Chzzk] Error processing chat message: {e}")

    async def _on_donation(self, donation) -> None:
        """
        Internal handler for donation events.

        Args:
            donation: Donation object from chzzkpy
        """
        try:
            # Format donation as special chat message
            amount = getattr(donation, "amount", 0)
            donor = getattr(donation, "nickname", "Anonymous")
            donation_message = getattr(donation, "message", "")

            formatted_message = (
                f"💝 {amount}원 후원! {donation_message}"
                if donation_message
                else f"💝 {amount}원 후원!"
            )

            chat_message = self.format_message(
                platform="chzzk",
                author=donor,
                message=formatted_message,
                user_id=getattr(donation, "user_id", ""),
            )

            logger.info(f"[Chzzk] Donation from {donor}: {amount}원")

            # Call the message callback
            try:
                self.message_callback(chat_message)
            except Exception as e:
                logger.error(f"[Chzzk] Error in donation callback: {e}")

        except Exception as e:
            logger.error(f"[Chzzk] Error processing donation: {e}")

    async def _monitoring_loop(self) -> None:
        """Main monitoring loop that handles connection and reconnection."""
        logger.info("[Chzzk] Starting monitoring loop")

        while self.is_running:
            try:
                # Import chzzkpy here to avoid import errors if Python < 3.11
                try:
                    from chzzkpy import UserPermission
                except ImportError as e:
                    logger.error(
                        "[Chzzk] Failed to import chzzkpy. "
                        "Please install: pip install chzzkpy"
                    )
                    logger.error(f"[Chzzk] Import error: {e}")
                    self.is_running = False
                    break

                # Ensure authentication
                if not await self._ensure_authenticated():
                    logger.error("[Chzzk] Authentication required. Stopping monitor.")
                    self.is_running = False
                    break

                logger.info("[Chzzk] Connecting to chat...")

                # Connect to chat with user permissions
                # Request chat and donation permissions
                permissions = [
                    UserPermission.CHAT_READ,
                    UserPermission.CHAT_SEND,
                    UserPermission.DONATION_READ,
                ]

                # Subscribe to events
                @self._user_client.event
                async def on_chat(message):
                    await self._on_chat_message(message)

                @self._user_client.event
                async def on_donation(donation):
                    await self._on_donation(donation)

                # Connect and start receiving events
                await self._user_client.connect(permissions=permissions)

                # If we reach here, connection was successful
                self._connected = True
                self.retry_count = 0
                logger.success("[Chzzk] Connected to live chat")

                # The connect() method blocks until disconnected
                # When it returns, the connection has been lost

            except asyncio.CancelledError:
                logger.info("[Chzzk] Monitoring loop cancelled")
                break
            except Exception as e:
                logger.error(f"[Chzzk] Error in monitoring loop: {e}")
                self._connected = False
                self.retry_count += 1

                # Check retry limit
                if self.retry_count >= self.max_retries:
                    logger.error(
                        f"[Chzzk] Max retries ({self.max_retries}) reached, stopping monitor"
                    )
                    self.is_running = False
                    break

                # Wait before retry
                logger.debug(
                    f"[Chzzk] Retry {self.retry_count}/{self.max_retries} "
                    f"in {self.retry_interval}s"
                )
                await asyncio.sleep(self.retry_interval)

            finally:
                # Clean up client
                if self._user_client:
                    try:
                        await self._user_client.disconnect()
                    except Exception:
                        pass

        logger.info("[Chzzk] Monitoring loop stopped")

    async def start_monitoring(self) -> bool:
        """
        Start monitoring Chzzk chat messages.

        Returns:
            bool: True if monitoring started successfully
        """
        if self.is_running:
            logger.warning("[Chzzk] Monitor is already running")
            return True

        logger.info("=" * 60)
        logger.info("[Chzzk] Starting chat monitor (Official OAuth API)")
        logger.info(f"[Chzzk] Channel ID: {self.channel_id}")
        logger.info(f"[Chzzk] Client ID: {self.client_id}")
        logger.info("=" * 60)

        self.is_running = True
        self.retry_count = 0
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())

        return True

    async def stop_monitoring(self) -> None:
        """Stop monitoring Chzzk chat messages."""
        logger.info("[Chzzk] Stopping chat monitor")
        self.is_running = False
        self._connected = False

        # Disconnect user client
        if self._user_client:
            try:
                await self._user_client.disconnect()
            except Exception as e:
                logger.debug(f"[Chzzk] Error disconnecting client: {e}")
            self._user_client = None

        # Cancel the monitoring task
        if self._monitoring_task and not self._monitoring_task.done():
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        logger.info("[Chzzk] Chat monitor stopped")

    def is_connected(self) -> bool:
        """
        Check if the monitor is currently connected.

        Returns:
            bool: True if connected, False otherwise
        """
        return self._connected

    def get_auth_url(self) -> str:
        """
        Get OAuth2 authorization URL for user authentication.

        Returns:
            str: Authorization URL
        """
        return self._oauth_manager.generate_auth_url()

    async def complete_auth(self, code: str) -> bool:
        """
        Complete OAuth2 authentication with authorization code.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            bool: True if authentication successful
        """
        try:
            tokens = await self._oauth_manager.exchange_code(code)
            self.access_token = tokens["access_token"]
            self.refresh_token = tokens["refresh_token"]
            logger.success("[Chzzk] OAuth authentication completed")
            return True
        except Exception as e:
            logger.error(f"[Chzzk] OAuth authentication failed: {e}")
            return False
