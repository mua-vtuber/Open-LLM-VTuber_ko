"""
Discord community management module.

Provides:
- AI-powered personalized welcome messages
- FAQ auto-response system
- Message moderation
- Announcements and notifications
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

# Discord import is optional
try:
    import discord

    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False
    discord = None  # type: ignore


@dataclass
class FAQEntry:
    """FAQ entry with keywords and response."""

    keywords: List[str]  # Keywords to match
    response: str  # Response message
    use_embed: bool = False  # Use embed for response
    embed_color: int = 0x3498DB  # Embed color (blue)
    match_mode: str = "any"  # "any" or "all" keywords must match


@dataclass
class ModerationRule:
    """Moderation rule configuration."""

    blocked_words: List[str] = field(default_factory=list)
    blocked_patterns: List[str] = field(default_factory=list)
    warning_message: str = "부적절한 내용이 감지되어 삭제되었습니다."
    delete_message: bool = True
    log_violations: bool = True


class DiscordCommunityManager:
    """
    Discord community management with AI integration.

    Features:
    - Personalized welcome messages (AI-generated or template)
    - FAQ auto-response with keyword matching
    - Message moderation with configurable rules
    - Announcements and stream notifications
    """

    # Anti-spam: minimum time between welcome messages for same user
    WELCOME_COOLDOWN_SECONDS = 30

    def __init__(
        self,
        bot: Any,  # discord.Client or commands.Bot
        config: Dict[str, Any],
        ai_callback: Optional[Callable[[str], str]] = None,
    ):
        """
        Initialize community manager.

        Args:
            bot: Discord bot instance
            config: Configuration dictionary with:
                - welcome_channel_id: Channel ID for welcome messages
                - welcome_message: Template message ({member} placeholder)
                - ai_welcome: Use AI to generate personalized welcomes
                - moderation_enabled: Enable message moderation
                - blocked_words: List of blocked words
                - faq_channel_id: Channel ID for FAQ responses
                - faq_entries: List of FAQ entries
            ai_callback: Optional async function for AI text generation
        """
        if not DISCORD_AVAILABLE:
            raise RuntimeError(
                "discord.py is not installed. Install with: pip install discord.py"
            )

        self.bot = bot
        self.config = config
        self.ai_callback = ai_callback

        # Welcome settings
        self.welcome_channel_id = config.get("welcome_channel_id", 0)
        self.welcome_message_template = config.get(
            "welcome_message", "환영합니다 {member}님!"
        )
        self.ai_welcome_enabled = config.get("ai_welcome", False)

        # Moderation settings
        self.moderation_enabled = config.get("moderation_enabled", False)
        self.moderation_rule = ModerationRule(
            blocked_words=config.get("blocked_words", []),
            blocked_patterns=config.get("blocked_patterns", []),
            warning_message=config.get(
                "moderation_warning", "부적절한 내용이 감지되어 삭제되었습니다."
            ),
        )

        # FAQ settings
        self.faq_channel_id = config.get("faq_channel_id", 0)
        self.faq_entries: List[FAQEntry] = []
        self._load_faq_entries(config.get("faq_entries", {}))

        # State tracking
        self._recent_welcomes: Dict[int, datetime] = {}
        self._compiled_patterns: List[re.Pattern] = []
        self._compile_moderation_patterns()

        logger.info("[CommunityManager] Initialized")

    def _load_faq_entries(self, faq_data: Dict[str, Any]) -> None:
        """Load FAQ entries from configuration."""
        if isinstance(faq_data, dict):
            # Simple format: {"keyword": "response"}
            for keyword, response in faq_data.items():
                self.faq_entries.append(
                    FAQEntry(keywords=[keyword.lower()], response=response)
                )
        elif isinstance(faq_data, list):
            # Advanced format: [{"keywords": [...], "response": "..."}]
            for entry in faq_data:
                if isinstance(entry, dict):
                    keywords = entry.get("keywords", [])
                    if isinstance(keywords, str):
                        keywords = [keywords]
                    self.faq_entries.append(
                        FAQEntry(
                            keywords=[k.lower() for k in keywords],
                            response=entry.get("response", ""),
                            use_embed=entry.get("use_embed", False),
                            match_mode=entry.get("match_mode", "any"),
                        )
                    )

        if self.faq_entries:
            logger.info(
                f"[CommunityManager] Loaded {len(self.faq_entries)} FAQ entries"
            )

    def _compile_moderation_patterns(self) -> None:
        """Compile regex patterns for moderation."""
        for pattern_str in self.moderation_rule.blocked_patterns:
            try:
                compiled = re.compile(pattern_str, re.IGNORECASE)
                self._compiled_patterns.append(compiled)
            except re.error as e:
                logger.warning(
                    f"[CommunityManager] Invalid regex pattern '{pattern_str}': {e}"
                )

    async def on_member_join(self, member: discord.Member) -> bool:
        """
        Handle new member joining the server.

        Args:
            member: Discord member who joined

        Returns:
            True if welcome message was sent
        """
        if not self.welcome_channel_id:
            return False

        # Cooldown check
        if member.id in self._recent_welcomes:
            last_welcome = self._recent_welcomes[member.id]
            if datetime.now() - last_welcome < timedelta(
                seconds=self.WELCOME_COOLDOWN_SECONDS
            ):
                logger.debug(
                    f"[CommunityManager] Skipping welcome for {member.display_name} (cooldown)"
                )
                return False

        try:
            channel = self.bot.get_channel(self.welcome_channel_id)
            if not channel:
                logger.warning(
                    f"[CommunityManager] Welcome channel {self.welcome_channel_id} not found"
                )
                return False

            # Generate welcome message
            if self.ai_welcome_enabled and self.ai_callback:
                welcome_msg = await self._generate_ai_welcome(member)
            else:
                welcome_msg = self.welcome_message_template.format(
                    member=member.mention
                )

            await channel.send(welcome_msg)
            self._recent_welcomes[member.id] = datetime.now()

            logger.info(
                f"[CommunityManager] Welcomed new member: {member.display_name}"
            )
            return True

        except discord.Forbidden:
            logger.error(
                "[CommunityManager] Missing permissions to send welcome message"
            )
            return False
        except Exception as e:
            logger.error(f"[CommunityManager] Failed to welcome member: {e}")
            return False

    async def _generate_ai_welcome(self, member: discord.Member) -> str:
        """Generate AI-powered personalized welcome message."""
        prompt = f"""새로운 멤버 '{member.display_name}'님이 서버에 입장했습니다.
친근하고 따뜻한 환영 메시지를 한 문장으로 작성해주세요.
이모지를 적절히 사용해도 좋습니다.
멘션은 사용하지 마세요."""

        try:
            if asyncio.iscoroutinefunction(self.ai_callback):
                response = await self.ai_callback(prompt)
            else:
                response = await asyncio.to_thread(self.ai_callback, prompt)

            # Add mention at the beginning
            return f"{member.mention} {response}"
        except Exception as e:
            logger.warning(f"[CommunityManager] AI welcome generation failed: {e}")
            return self.welcome_message_template.format(member=member.mention)

    async def check_moderation(self, message: discord.Message) -> bool:
        """
        Check message against moderation rules.

        Args:
            message: Discord message to check

        Returns:
            True if message passes moderation, False if blocked
        """
        if not self.moderation_enabled:
            return True

        content_lower = message.content.lower()

        # Check blocked words
        for word in self.moderation_rule.blocked_words:
            if word.lower() in content_lower:
                await self._handle_moderation_violation(
                    message, f"blocked word: {word}"
                )
                return False

        # Check regex patterns
        for pattern in self._compiled_patterns:
            if pattern.search(message.content):
                await self._handle_moderation_violation(
                    message, f"pattern match: {pattern.pattern}"
                )
                return False

        return True

    async def _handle_moderation_violation(
        self, message: discord.Message, reason: str
    ) -> None:
        """Handle a moderation rule violation."""
        if self.moderation_rule.log_violations:
            logger.info(
                f"[CommunityManager] Moderation violation by {message.author.display_name}: {reason}"
            )

        if self.moderation_rule.delete_message:
            try:
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention} {self.moderation_rule.warning_message}",
                    delete_after=5,
                )
            except discord.Forbidden:
                logger.warning(
                    "[CommunityManager] Missing permissions to delete message"
                )
            except discord.NotFound:
                pass  # Message already deleted

    async def check_faq(self, message: discord.Message) -> bool:
        """
        Check if message matches any FAQ entry and respond.

        Args:
            message: Discord message to check

        Returns:
            True if FAQ response was sent
        """
        if not self.faq_entries:
            return False

        # Only respond in FAQ channel if configured
        if self.faq_channel_id and message.channel.id != self.faq_channel_id:
            return False

        content_lower = message.content.lower()

        for entry in self.faq_entries:
            if self._matches_faq(content_lower, entry):
                await self._send_faq_response(message, entry)
                return True

        return False

    def _matches_faq(self, content: str, entry: FAQEntry) -> bool:
        """Check if content matches FAQ entry keywords."""
        if entry.match_mode == "all":
            return all(keyword in content for keyword in entry.keywords)
        else:  # "any"
            return any(keyword in content for keyword in entry.keywords)

    async def _send_faq_response(
        self, message: discord.Message, entry: FAQEntry
    ) -> None:
        """Send FAQ response to channel."""
        try:
            if entry.use_embed:
                embed = discord.Embed(
                    description=entry.response,
                    color=discord.Color(entry.embed_color),
                )
                await message.reply(embed=embed)
            else:
                await message.reply(entry.response)

            logger.debug(
                f"[CommunityManager] FAQ response sent for keywords: {entry.keywords}"
            )
        except Exception as e:
            logger.error(f"[CommunityManager] Failed to send FAQ response: {e}")

    async def send_announcement(
        self,
        channel_id: int,
        title: str,
        content: str,
        mention_everyone: bool = False,
        color: int = 0x3498DB,
    ) -> bool:
        """
        Send an announcement embed to a channel.

        Args:
            channel_id: Target channel ID
            title: Announcement title
            content: Announcement content
            mention_everyone: Whether to mention @everyone
            color: Embed color (hex)

        Returns:
            True if announcement was sent
        """
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.error(f"[CommunityManager] Channel {channel_id} not found")
                return False

            embed = discord.Embed(
                title=title,
                description=content,
                color=discord.Color(color),
                timestamp=datetime.now(),
            )

            mention = "@everyone " if mention_everyone else ""
            await channel.send(mention, embed=embed)

            logger.info(f"[CommunityManager] Announcement sent to channel {channel_id}")
            return True

        except discord.Forbidden:
            logger.error("[CommunityManager] Missing permissions for announcement")
            return False
        except Exception as e:
            logger.error(f"[CommunityManager] Failed to send announcement: {e}")
            return False

    async def send_stream_notification(
        self,
        channel_id: int,
        stream_url: str,
        stream_title: str,
        thumbnail_url: Optional[str] = None,
        mention_everyone: bool = True,
    ) -> bool:
        """
        Send a stream start notification.

        Args:
            channel_id: Target channel ID
            stream_url: Stream URL
            stream_title: Stream title
            thumbnail_url: Optional thumbnail image URL
            mention_everyone: Whether to mention @everyone

        Returns:
            True if notification was sent
        """
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.error(f"[CommunityManager] Channel {channel_id} not found")
                return False

            embed = discord.Embed(
                title="방송이 시작되었습니다!",
                description=stream_title,
                url=stream_url,
                color=discord.Color.red(),
                timestamp=datetime.now(),
            )

            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)

            embed.add_field(
                name="시청하기", value=f"[클릭]({stream_url})", inline=False
            )

            mention = "@everyone " if mention_everyone else ""
            await channel.send(mention, embed=embed)

            logger.info("[CommunityManager] Stream notification sent")
            return True

        except discord.Forbidden:
            logger.error("[CommunityManager] Missing permissions for notification")
            return False
        except Exception as e:
            logger.error(f"[CommunityManager] Failed to send stream notification: {e}")
            return False

    def add_faq_entry(
        self,
        keywords: List[str],
        response: str,
        use_embed: bool = False,
        match_mode: str = "any",
    ) -> None:
        """
        Add a new FAQ entry at runtime.

        Args:
            keywords: Keywords to match
            response: Response message
            use_embed: Use embed for response
            match_mode: "any" or "all" keywords must match
        """
        entry = FAQEntry(
            keywords=[k.lower() for k in keywords],
            response=response,
            use_embed=use_embed,
            match_mode=match_mode,
        )
        self.faq_entries.append(entry)
        logger.info(f"[CommunityManager] Added FAQ entry: {keywords}")

    def remove_faq_entry(self, keyword: str) -> bool:
        """
        Remove FAQ entry containing the keyword.

        Args:
            keyword: Keyword to match for removal

        Returns:
            True if entry was removed
        """
        keyword_lower = keyword.lower()
        for i, entry in enumerate(self.faq_entries):
            if keyword_lower in entry.keywords:
                self.faq_entries.pop(i)
                logger.info(f"[CommunityManager] Removed FAQ entry: {keyword}")
                return True
        return False

    def add_blocked_word(self, word: str) -> None:
        """Add a word to the moderation blocklist."""
        if word not in self.moderation_rule.blocked_words:
            self.moderation_rule.blocked_words.append(word)
            logger.info(f"[CommunityManager] Added blocked word: {word}")

    def remove_blocked_word(self, word: str) -> bool:
        """Remove a word from the moderation blocklist."""
        try:
            self.moderation_rule.blocked_words.remove(word)
            logger.info(f"[CommunityManager] Removed blocked word: {word}")
            return True
        except ValueError:
            return False

    def cleanup_old_welcomes(self, max_age_hours: int = 24) -> int:
        """
        Clean up old welcome records to free memory.

        Args:
            max_age_hours: Maximum age in hours

        Returns:
            Number of entries removed
        """
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        old_ids = [uid for uid, ts in self._recent_welcomes.items() if ts < cutoff]

        for uid in old_ids:
            del self._recent_welcomes[uid]

        if old_ids:
            logger.debug(
                f"[CommunityManager] Cleaned up {len(old_ids)} old welcome records"
            )

        return len(old_ids)
