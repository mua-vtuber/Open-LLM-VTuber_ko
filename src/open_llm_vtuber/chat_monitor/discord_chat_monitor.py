"""
Discord chat monitor for text channel integration.
"""

from __future__ import annotations

import asyncio
from typing import Callable, List, Optional, Dict, Any

from loguru import logger

from .chat_monitor_interface import ChatMonitorInterface, ChatMessage
from ..visitor_profiles import ProfileManager
from ..discord import DiscordCommunityManager

# Discord import is optional
try:
    import discord
    from discord.ext import commands

    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False
    discord = None  # type: ignore
    commands = None  # type: ignore
    logger.warning(
        "[Discord] discord.py not installed. Install with: pip install discord.py"
    )


class DiscordChatMonitor(ChatMonitorInterface):
    """Discord text channel chat monitor."""

    def __init__(
        self,
        bot_token: str,
        guild_id: int,
        text_channel_ids: List[int],
        message_callback: Callable[[ChatMessage], None],
        respond_to_mentions: bool = True,
        respond_to_all: bool = False,
        command_prefix: str = "!",
        max_retries: int = 10,
        retry_interval: int = 60,
        # Community management options
        community_management: bool = False,
        welcome_channel_id: int = 0,
        welcome_message: str = "환영합니다 {member}님!",
        moderation_enabled: bool = False,
        blocked_words: Optional[List[str]] = None,
        # AI welcome
        ai_welcome: bool = False,
        # FAQ settings
        faq_channel_id: int = 0,
        faq_entries: Optional[Dict[str, str]] = None,
        # Profile management
        profile_manager: Optional[ProfileManager] = None,
        enable_profiles: bool = True,
        # AI callback for community manager
        ai_callback: Optional[Callable[[str], str]] = None,
    ):
        """
        Initialize Discord chat monitor.

        Args:
            bot_token: Discord bot token
            guild_id: Discord server (guild) ID
            text_channel_ids: List of text channel IDs to monitor
            message_callback: Callback function for received messages
            respond_to_mentions: Respond when bot is mentioned
            respond_to_all: Respond to all messages in monitored channels
            command_prefix: Command prefix for bot commands
            max_retries: Maximum reconnection attempts
            retry_interval: Interval between retries in seconds
            community_management: Enable community management features
            welcome_channel_id: Channel ID for welcome messages
            welcome_message: Welcome message template
            moderation_enabled: Enable message moderation
            blocked_words: List of blocked words for moderation
            ai_welcome: Use AI to generate personalized welcome messages
            faq_channel_id: Channel ID for FAQ responses (0 = all channels)
            faq_entries: FAQ keyword-response pairs
            profile_manager: Optional ProfileManager instance for visitor tracking
            enable_profiles: Enable visitor profile tracking
            ai_callback: Optional AI text generation callback for community features
        """
        if not DISCORD_AVAILABLE:
            raise RuntimeError(
                "discord.py is not installed. Install with: pip install discord.py"
            )

        super().__init__(message_callback, max_retries, retry_interval)

        self.bot_token = bot_token
        self.guild_id = guild_id
        self.text_channel_ids = text_channel_ids
        self.respond_to_mentions = respond_to_mentions
        self.respond_to_all = respond_to_all
        self.command_prefix = command_prefix

        # Community management settings
        self.community_management = community_management
        self.welcome_channel_id = welcome_channel_id
        self.welcome_message = welcome_message
        self.moderation_enabled = moderation_enabled
        self.blocked_words = blocked_words or []
        self.ai_welcome = ai_welcome
        self.faq_channel_id = faq_channel_id
        self.faq_entries = faq_entries or {}
        self.ai_callback = ai_callback

        # Community manager will be initialized after bot is ready
        self._community_manager: Optional[DiscordCommunityManager] = None

        # Profile management
        self.enable_profiles = enable_profiles
        if enable_profiles:
            self.profile_manager = profile_manager or ProfileManager()
        else:
            self.profile_manager = None

        # Internal state
        self._bot: Optional[commands.Bot] = None
        self._connected = False
        self._monitoring_task: Optional[asyncio.Task] = None
        self._response_queue: asyncio.Queue = asyncio.Queue()

    async def start_monitoring(self) -> bool:
        """Start Discord bot and begin monitoring."""
        if not DISCORD_AVAILABLE:
            logger.error("[Discord] discord.py is not available")
            return False

        try:
            # Setup intents
            intents = discord.Intents.default()
            intents.message_content = True
            intents.members = True
            intents.guilds = True

            self._bot = commands.Bot(
                command_prefix=self.command_prefix, intents=intents
            )

            # Setup event handlers
            self._setup_event_handlers()

            # Start bot in background task
            self._monitoring_task = asyncio.create_task(self._run_bot())

            # Wait for connection (max 30 seconds)
            for _ in range(30):
                if self._connected:
                    self.is_running = True
                    logger.success(
                        f"[Discord] Bot connected successfully. "
                        f"Monitoring {len(self.text_channel_ids)} channel(s)"
                    )
                    return True
                await asyncio.sleep(1)

            logger.error("[Discord] Connection timeout")
            return False

        except Exception as e:
            logger.error(f"[Discord] Failed to start monitoring: {e}")
            return False

    async def _run_bot(self) -> None:
        """Run the Discord bot."""
        try:
            await self._bot.start(self.bot_token)
        except discord.LoginFailure as e:
            logger.error(f"[Discord] Login failed - check your bot token: {e}")
        except Exception as e:
            logger.error(f"[Discord] Bot error: {e}")
        finally:
            self._connected = False

    async def stop_monitoring(self) -> None:
        """Stop Discord bot."""
        self.is_running = False

        if self._bot and not self._bot.is_closed():
            await self._bot.close()

        if self._monitoring_task and not self._monitoring_task.done():
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        self._connected = False
        logger.info("[Discord] Bot stopped")

    def is_connected(self) -> bool:
        """Check if bot is connected."""
        return self._connected and self._bot is not None and not self._bot.is_closed()

    def _setup_event_handlers(self) -> None:
        """Setup Discord event handlers."""

        @self._bot.event
        async def on_ready():
            self._connected = True
            logger.info(f"[Discord] Logged in as {self._bot.user}")
            logger.info(f"[Discord] Guild ID: {self.guild_id}")
            logger.info(f"[Discord] Monitoring channels: {self.text_channel_ids}")

            # Initialize CommunityManager if community management is enabled
            if self.community_management:
                self._init_community_manager()

        @self._bot.event
        async def on_message(message: discord.Message):
            await self._handle_message(message)

        @self._bot.event
        async def on_member_join(member: discord.Member):
            if self._community_manager:
                await self._community_manager.on_member_join(member)

        @self._bot.event
        async def on_disconnect():
            logger.warning("[Discord] Bot disconnected")

        @self._bot.event
        async def on_resumed():
            logger.info("[Discord] Bot reconnected")

    def _init_community_manager(self) -> None:
        """Initialize the CommunityManager after bot is ready."""
        config = {
            "welcome_channel_id": self.welcome_channel_id,
            "welcome_message": self.welcome_message,
            "ai_welcome": self.ai_welcome,
            "moderation_enabled": self.moderation_enabled,
            "blocked_words": self.blocked_words,
            "faq_channel_id": self.faq_channel_id,
            "faq_entries": self.faq_entries,
        }

        self._community_manager = DiscordCommunityManager(
            bot=self._bot,
            config=config,
            ai_callback=self.ai_callback,
        )

        logger.info("[Discord] CommunityManager initialized")

    async def _handle_message(self, message: discord.Message) -> None:
        """Handle incoming Discord message."""
        # Ignore bot's own messages
        if message.author == self._bot.user:
            return

        # Ignore DMs (only process guild messages)
        if not message.guild:
            return

        # Check if message is in monitored channels
        if message.channel.id not in self.text_channel_ids:
            return

        # Use CommunityManager for moderation and FAQ if available
        if self._community_manager:
            # Moderation check
            if not await self._community_manager.check_moderation(message):
                return  # Message was blocked

            # Check FAQ auto-response
            if await self._community_manager.check_faq(message):
                return  # FAQ was handled, no further processing needed
        else:
            # Fallback to basic moderation
            if self.moderation_enabled:
                if not await self._check_moderation(message):
                    return  # Message was blocked

        # Check if we should respond
        if not self._should_respond(message):
            return

        try:
            # Update visitor profile
            profile_context = ""
            if self.profile_manager:
                user_id = str(message.author.id)
                guild_id = str(message.guild.id) if message.guild else None

                # Update visit and get profile
                profile = self.profile_manager.update_visit(
                    platform="discord",
                    user_id=user_id,
                    identifier=message.author.display_name,
                    guild_id=guild_id,
                )

                # Record message
                self.profile_manager.record_message("discord", user_id)

                # Get profile context for AI
                profile_context = self.profile_manager.get_context_for_ai(
                    "discord", user_id
                )

                # Log profile info
                if profile.visit_count == 1:
                    logger.info(f"[Discord] New visitor: {message.author.display_name}")
                else:
                    logger.debug(
                        f"[Discord] Returning visitor: {message.author.display_name} "
                        f"(visit #{profile.visit_count})"
                    )

            # Create ChatMessage with profile context
            chat_message = self._create_chat_message(message, profile_context)

            logger.debug(
                f"[Discord] Message from {message.author.display_name}: "
                f"{message.content[:50]}..."
            )

            # Call message callback
            if asyncio.iscoroutinefunction(self.message_callback):
                await self.message_callback(chat_message)
            else:
                await asyncio.to_thread(self.message_callback, chat_message)

        except Exception as e:
            logger.error(f"[Discord] Error handling message: {e}")

    def _should_respond(self, message: discord.Message) -> bool:
        """Determine if bot should respond to this message."""
        # Respond to all messages in monitored channels
        if self.respond_to_all:
            return True

        # Respond to mentions
        if self.respond_to_mentions and self._bot.user in message.mentions:
            return True

        # Respond to command prefix
        if message.content.startswith(self.command_prefix):
            return True

        return False

    def _create_chat_message(
        self, message: discord.Message, profile_context: str = ""
    ) -> ChatMessage:
        """Convert Discord message to ChatMessage format."""
        # Determine user roles/permissions
        is_owner = False
        is_moderator = False

        if message.guild:
            is_owner = message.guild.owner_id == message.author.id
            if hasattr(message.author, "guild_permissions"):
                is_moderator = message.author.guild_permissions.moderate_members

        # Extract badges/roles
        badges = self._extract_badges(message)

        # Add profile context to badges for downstream processing
        if profile_context:
            badges["profile_context"] = profile_context

        # Determine priority
        priority = self._determine_priority(
            is_owner=is_owner,
            is_moderator=is_moderator,
            is_member=True,  # All users in channel are members
            badges=badges,
        )

        # Clean message content (remove bot mentions)
        clean_content = self._clean_message_content(message)

        return ChatMessage(
            platform="discord",
            author=message.author.display_name,
            message=clean_content,
            timestamp=message.created_at.isoformat(),
            user_id=str(message.author.id),
            is_moderator=is_moderator,
            is_owner=is_owner,
            is_member=True,
            badges=badges,
            priority=priority,
        )

    def _clean_message_content(self, message: discord.Message) -> str:
        """Remove bot mentions from message content."""
        content = message.content

        if self._bot and self._bot.user:
            # Remove direct mention
            content = content.replace(f"<@{self._bot.user.id}>", "").strip()
            # Remove nickname mention
            content = content.replace(f"<@!{self._bot.user.id}>", "").strip()

        return content

    def _extract_badges(self, message: discord.Message) -> Dict[str, Any]:
        """Extract badge information from Discord message."""
        badges = {}
        author = message.author

        # Check for Nitro
        if hasattr(author, "premium_since") and author.premium_since:
            badges["nitro"] = True

        # Check if bot
        if author.bot:
            badges["bot"] = True

        # Check for server booster
        if hasattr(author, "premium_since") and author.premium_since:
            badges["booster"] = True

        # Get role names
        if hasattr(author, "roles"):
            role_names = [
                role.name for role in author.roles if role.name != "@everyone"
            ]
            if role_names:
                badges["roles"] = role_names

        return badges

    async def _check_moderation(self, message: discord.Message) -> bool:
        """Check message against moderation rules."""
        if not self.blocked_words:
            return True

        content_lower = message.content.lower()

        for word in self.blocked_words:
            if word.lower() in content_lower:
                try:
                    await message.delete()
                    await message.channel.send(
                        f"{message.author.mention} 부적절한 내용이 감지되어 삭제되었습니다.",
                        delete_after=5,
                    )
                    logger.info(
                        f"[Discord] Deleted message from {message.author}: "
                        f"blocked word '{word}'"
                    )
                    return False
                except discord.Forbidden:
                    logger.warning("[Discord] Missing permissions to delete message")
                except Exception as e:
                    logger.error(f"[Discord] Failed to delete message: {e}")

        return True

    async def _handle_member_join(self, member: discord.Member) -> None:
        """Handle new member joining the server."""
        if not self.welcome_channel_id:
            return

        try:
            channel = self._bot.get_channel(self.welcome_channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                return

            # Format welcome message
            welcome_msg = self.welcome_message.format(member=member.mention)
            await channel.send(welcome_msg)

            logger.info(f"[Discord] Welcomed new member: {member.display_name}")

        except Exception as e:
            logger.error(f"[Discord] Failed to send welcome message: {e}")

    async def send_response(
        self,
        channel_id: int,
        content: str,
        reply_to_message_id: Optional[int] = None,
    ) -> bool:
        """
        Send a response message to a Discord channel.

        Args:
            channel_id: Target channel ID
            content: Message content
            reply_to_message_id: Optional message ID to reply to

        Returns:
            bool: True if message was sent successfully
        """
        if not self.is_connected():
            logger.warning("[Discord] Cannot send response - bot is not connected")
            return False

        try:
            channel = self._bot.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                logger.error(
                    f"[Discord] Channel {channel_id} not found or not a text channel"
                )
                return False

            if reply_to_message_id:
                try:
                    original_message = await channel.fetch_message(reply_to_message_id)
                    await original_message.reply(content)
                except discord.NotFound:
                    await channel.send(content)
            else:
                await channel.send(content)

            return True

        except discord.Forbidden:
            logger.error("[Discord] Missing permissions to send message")
            return False
        except Exception as e:
            logger.error(f"[Discord] Failed to send response: {e}")
            return False

    def get_bot(self) -> Optional[commands.Bot]:
        """Get the Discord bot instance for external use."""
        return self._bot
