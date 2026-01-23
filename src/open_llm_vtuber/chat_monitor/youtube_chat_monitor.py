"""
YouTube Live Chat monitoring implementation.

Uses YouTube Data API v3 to monitor live chat messages in real-time.
"""

import asyncio
from typing import Optional, Callable
import httpx
from loguru import logger

from .chat_monitor_interface import ChatMonitorInterface, ChatMessage


class YouTubeChatMonitor(ChatMonitorInterface):
    """
    YouTube Live Chat monitor using YouTube Data API v3.
    """

    def __init__(
        self,
        api_key: str,
        channel_id: str,
        message_callback: Callable[[ChatMessage], None],
        max_retries: int = 10,
        retry_interval: int = 60,
    ):
        """
        Initialize YouTube chat monitor.

        Args:
            api_key: YouTube Data API v3 key
            channel_id: YouTube channel ID to monitor
            message_callback: Function to call when a new message is received
            max_retries: Maximum number of reconnection attempts
            retry_interval: Interval between retry attempts in seconds
        """
        super().__init__(message_callback, max_retries, retry_interval)
        self.api_key = api_key
        self.channel_id = channel_id
        self.live_chat_id: Optional[str] = None
        self.next_page_token: Optional[str] = None
        self.last_message_time: Optional[str] = None
        self._monitoring_task: Optional[asyncio.Task] = None
        self._connected = False

    async def _get_live_stream_id(self) -> Optional[str]:
        """
        Get the current live stream video ID.

        Returns:
            Optional[str]: Video ID if a live stream is active, None otherwise
        """
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "id",
            "channelId": self.channel_id,
            "type": "video",
            "eventType": "live",
            "key": self.api_key,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=10.0)
                response.raise_for_status()
                data = response.json()

                if data.get("items"):
                    video_id = data["items"][0]["id"]["videoId"]
                    logger.info(f"[YouTube] Live stream found: {video_id}")
                    return video_id
                else:
                    logger.debug("[YouTube] No active live stream found")
                    return None

        except httpx.HTTPStatusError as e:
            logger.error(
                f"[YouTube] HTTP error getting live stream: {e.response.status_code}"
            )
            return None
        except Exception as e:
            logger.error(f"[YouTube] Error getting live stream: {e}")
            return None

    async def _get_live_chat_id(self, video_id: str) -> Optional[str]:
        """
        Get the live chat ID for a video.

        Args:
            video_id: YouTube video ID

        Returns:
            Optional[str]: Live chat ID if available, None otherwise
        """
        url = "https://www.googleapis.com/youtube/v3/videos"
        params = {"part": "liveStreamingDetails", "id": video_id, "key": self.api_key}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=10.0)
                response.raise_for_status()
                data = response.json()

                if data.get("items") and "liveStreamingDetails" in data["items"][0]:
                    chat_id = data["items"][0]["liveStreamingDetails"].get(
                        "activeLiveChatId"
                    )
                    if chat_id:
                        logger.info(f"[YouTube] Live chat ID: {chat_id}")
                        return chat_id
                    else:
                        logger.warning("[YouTube] No active live chat found")
                        return None
                else:
                    logger.warning("[YouTube] No live streaming details found")
                    return None

        except httpx.HTTPStatusError as e:
            logger.error(
                f"[YouTube] HTTP error getting chat ID: {e.response.status_code}"
            )
            return None
        except Exception as e:
            logger.error(f"[YouTube] Error getting chat ID: {e}")
            return None

    async def _fetch_chat_messages(self) -> list[ChatMessage]:
        """
        Fetch new chat messages from the live chat.

        Returns:
            list[ChatMessage]: List of new chat messages
        """
        if not self.live_chat_id:
            return []

        url = "https://www.googleapis.com/youtube/v3/liveChat/messages"
        params = {
            "part": "snippet,authorDetails",
            "liveChatId": self.live_chat_id,
            "key": self.api_key,
        }

        if self.next_page_token:
            params["pageToken"] = self.next_page_token

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=10.0)
                response.raise_for_status()
                data = response.json()

                # Update next page token
                self.next_page_token = data.get("nextPageToken")

                messages = []
                for item in data.get("items", []):
                    snippet = item["snippet"]
                    author = item["authorDetails"]

                    message_time = snippet["publishedAt"]

                    # Skip already processed messages
                    if (
                        self.last_message_time
                        and message_time <= self.last_message_time
                    ):
                        continue

                    # 슈퍼챗 정보 확인
                    badges = {}
                    message_type = snippet.get("type", "textMessageEvent")

                    if message_type == "superChatEvent":
                        badges["super_chat"] = True
                        # 슈퍼챗 금액 정보 (있으면 추가)
                        if "superChatDetails" in snippet:
                            badges["super_chat_amount"] = snippet["superChatDetails"].get("amountDisplayString", "")
                    elif message_type == "superStickerEvent":
                        badges["super_sticker"] = True
                        # 슈퍼 스티커 금액 정보 (있으면 추가)
                        if "superStickerDetails" in snippet:
                            badges["super_sticker_amount"] = snippet["superStickerDetails"].get("amountDisplayString", "")

                    message = self.format_message(
                        platform="youtube",
                        author=author["displayName"],
                        message=snippet["displayMessage"],
                        timestamp=message_time,
                        user_id=author.get("channelId", ""),
                        is_moderator=author.get("isChatModerator", False),
                        is_owner=author.get("isChatOwner", False),
                        is_member=author.get("isChatSponsor", False),
                        badges=badges,
                    )

                    messages.append(message)

                # Update last message time
                if messages:
                    self.last_message_time = messages[-1]["timestamp"]

                return messages

        except httpx.HTTPStatusError as e:
            if e.response.status_code in [401, 403, 404]:
                logger.warning(
                    f"[YouTube] Chat access error (status {e.response.status_code}), "
                    "stream may have ended"
                )
                self.live_chat_id = None
                self._connected = False
            else:
                logger.error(
                    f"[YouTube] HTTP error fetching messages: {e.response.status_code}"
                )
            return []
        except Exception as e:
            logger.error(f"[YouTube] Error fetching messages: {e}")
            return []

    async def _monitoring_loop(self) -> None:
        """Main monitoring loop that continuously fetches chat messages."""
        logger.info("[YouTube] Starting monitoring loop")

        while self.is_running:
            try:
                # If not connected, try to connect
                if not self.live_chat_id:
                    video_id = await self._get_live_stream_id()
                    if video_id:
                        self.live_chat_id = await self._get_live_chat_id(video_id)
                        if self.live_chat_id:
                            self._connected = True
                            self.retry_count = 0
                            logger.success("[YouTube] Connected to live chat")

                            # Skip initial messages
                            initial_messages = await self._fetch_chat_messages()
                            if initial_messages:
                                logger.info(
                                    f"[YouTube] Skipped {len(initial_messages)} initial messages"
                                )
                        else:
                            self.retry_count += 1
                    else:
                        self.retry_count += 1

                    # Check retry limit
                    if self.retry_count >= self.max_retries:
                        logger.error(
                            f"[YouTube] Max retries ({self.max_retries}) reached, stopping monitor"
                        )
                        self.is_running = False
                        break

                    # Wait before retry
                    if not self.live_chat_id:
                        logger.debug(
                            f"[YouTube] Retry {self.retry_count}/{self.max_retries} "
                            f"in {self.retry_interval}s"
                        )
                        await asyncio.sleep(self.retry_interval)
                        continue

                # Fetch new messages
                messages = await self._fetch_chat_messages()

                # Process new messages
                for message in messages:
                    logger.info(f"[YouTube] {message['author']}: {message['message']}")
                    try:
                        self.message_callback(message)
                    except Exception as e:
                        logger.error(f"[YouTube] Error in message callback: {e}")

                # Wait before next poll (2 seconds as per YouTube API recommendations)
                await asyncio.sleep(2)

            except asyncio.CancelledError:
                logger.info("[YouTube] Monitoring loop cancelled")
                break
            except Exception as e:
                logger.error(f"[YouTube] Error in monitoring loop: {e}")
                await asyncio.sleep(5)

        logger.info("[YouTube] Monitoring loop stopped")

    async def start_monitoring(self) -> bool:
        """
        Start monitoring YouTube chat messages.

        Returns:
            bool: True if monitoring started successfully
        """
        if self.is_running:
            logger.warning("[YouTube] Monitor is already running")
            return True

        logger.info("=" * 60)
        logger.info("[YouTube] Starting chat monitor")
        logger.info(f"[YouTube] Channel ID: {self.channel_id}")
        logger.info("=" * 60)

        self.is_running = True
        self.retry_count = 0
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())

        return True

    async def stop_monitoring(self) -> None:
        """Stop monitoring YouTube chat messages."""
        logger.info("[YouTube] Stopping chat monitor")
        self.is_running = False
        self._connected = False

        if self._monitoring_task and not self._monitoring_task.done():
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        logger.info("[YouTube] Chat monitor stopped")

    def is_connected(self) -> bool:
        """
        Check if the monitor is currently connected.

        Returns:
            bool: True if connected, False otherwise
        """
        return self._connected and self.live_chat_id is not None
