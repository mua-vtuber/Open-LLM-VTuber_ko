from pydantic import Field
from typing import Dict, ClassVar, List
from .i18n import I18nMixin, Description


class YouTubeChatConfig(I18nMixin):
    """Configuration for YouTube Live Chat monitoring."""

    enabled: bool = Field(False, alias="enabled")
    api_key: str = Field("", alias="api_key")
    channel_id: str = Field("", alias="channel_id")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "enabled": Description(
            en="Enable YouTube chat monitoring",
            zh="启用YouTube聊天监控",
            ko="YouTube 채팅 모니터링 활성화",
        ),
        "api_key": Description(
            en="YouTube Data API v3 key",
            zh="YouTube Data API v3 密钥",
            ko="YouTube Data API v3 키",
        ),
        "channel_id": Description(
            en="YouTube channel ID to monitor",
            zh="要监控的YouTube频道ID",
            ko="모니터링할 YouTube 채널 ID",
        ),
    }


class ChzzkChatConfig(I18nMixin):
    """Configuration for Chzzk (치지직) Live Chat monitoring using official OAuth API."""

    enabled: bool = Field(False, alias="enabled")
    channel_id: str = Field("", alias="channel_id")
    client_id: str = Field("", alias="client_id")
    client_secret: str = Field("", alias="client_secret")
    redirect_uri: str = Field(
        "http://localhost:12393/chzzk/callback", alias="redirect_uri"
    )
    access_token: str = Field("", alias="access_token")
    refresh_token: str = Field("", alias="refresh_token")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "enabled": Description(
            en="Enable Chzzk chat monitoring",
            zh="启用Chzzk聊天监控",
            ko="치지직 채팅 모니터링 활성화",
        ),
        "channel_id": Description(
            en="Chzzk channel ID to monitor",
            zh="要监控的Chzzk频道ID",
            ko="모니터링할 치지직 채널 ID",
        ),
        "client_id": Description(
            en="OAuth2 Client ID from CHZZK Developer Center",
            zh="来自CHZZK开发者中心的OAuth2客户端ID",
            ko="CHZZK 개발자 센터의 OAuth2 클라이언트 ID",
        ),
        "client_secret": Description(
            en="OAuth2 Client Secret from CHZZK Developer Center",
            zh="来自CHZZK开发者中心的OAuth2客户端密钥",
            ko="CHZZK 개발자 센터의 OAuth2 클라이언트 시크릿",
        ),
        "redirect_uri": Description(
            en="OAuth2 redirect URI (must match Developer Center settings)",
            zh="OAuth2重定向URI（必须与开发者中心设置匹配）",
            ko="OAuth2 리다이렉트 URI (개발자 센터 설정과 일치해야 함)",
        ),
        "access_token": Description(
            en="OAuth2 access token (automatically set after authorization)",
            zh="OAuth2访问令牌（授权后自动设置）",
            ko="OAuth2 액세스 토큰 (인증 후 자동 설정)",
        ),
        "refresh_token": Description(
            en="OAuth2 refresh token (automatically set after authorization)",
            zh="OAuth2刷新令牌（授权后自动设置）",
            ko="OAuth2 리프레시 토큰 (인증 후 자동 설정)",
        ),
    }


class DiscordConfig(I18nMixin):
    """Configuration for Discord integration."""

    enabled: bool = Field(False, alias="enabled")
    bot_token: str = Field("", alias="bot_token")
    guild_id: int = Field(0, alias="guild_id")

    # Text channel settings
    text_channel_ids: List[int] = Field([], alias="text_channel_ids")
    respond_to_mentions: bool = Field(True, alias="respond_to_mentions")
    respond_to_all: bool = Field(False, alias="respond_to_all")
    command_prefix: str = Field("!", alias="command_prefix")

    # Voice channel settings (Phase 4)
    voice_enabled: bool = Field(False, alias="voice_enabled")
    voice_channel_id: int = Field(0, alias="voice_channel_id")

    # Community management settings
    community_management: bool = Field(False, alias="community_management")
    welcome_channel_id: int = Field(0, alias="welcome_channel_id")
    welcome_message: str = Field(
        "환영합니다 {member}님! 즐거운 시간 보내세요~", alias="welcome_message"
    )

    # Moderation settings
    moderation_enabled: bool = Field(False, alias="moderation_enabled")
    blocked_words: List[str] = Field([], alias="blocked_words")

    # AI welcome settings
    ai_welcome: bool = Field(False, alias="ai_welcome")

    # FAQ settings
    faq_channel_id: int = Field(0, alias="faq_channel_id")
    faq_entries: Dict[str, str] = Field({}, alias="faq_entries")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "enabled": Description(
            en="Enable Discord integration",
            zh="启用Discord集成",
            ko="Discord 연동 활성화",
        ),
        "bot_token": Description(
            en="Discord bot token from Developer Portal",
            zh="来自Discord开发者门户的机器人令牌",
            ko="Discord 개발자 포털의 봇 토큰",
        ),
        "guild_id": Description(
            en="Discord server (guild) ID",
            zh="Discord服务器ID",
            ko="Discord 서버 ID",
        ),
        "text_channel_ids": Description(
            en="List of text channel IDs to monitor",
            zh="要监控的文字频道ID列表",
            ko="모니터링할 텍스트 채널 ID 목록",
        ),
        "respond_to_mentions": Description(
            en="Respond when the bot is mentioned",
            zh="当机器人被提及时回复",
            ko="봇이 멘션되면 응답",
        ),
        "respond_to_all": Description(
            en="Respond to all messages in monitored channels",
            zh="回复监控频道中的所有消息",
            ko="모니터링 채널의 모든 메시지에 응답",
        ),
        "command_prefix": Description(
            en="Command prefix for bot commands",
            zh="机器人命令前缀",
            ko="봇 명령어 접두사",
        ),
        "voice_enabled": Description(
            en="Enable voice channel features",
            zh="启用语音频道功能",
            ko="음성 채널 기능 활성화",
        ),
        "voice_channel_id": Description(
            en="Voice channel ID to join",
            zh="要加入的语音频道ID",
            ko="참여할 음성 채널 ID",
        ),
        "community_management": Description(
            en="Enable community management features",
            zh="启用社区管理功能",
            ko="커뮤니티 관리 기능 활성화",
        ),
        "welcome_channel_id": Description(
            en="Channel ID for welcome messages",
            zh="欢迎消息频道ID",
            ko="환영 메시지 채널 ID",
        ),
        "welcome_message": Description(
            en="Welcome message template ({member} will be replaced)",
            zh="欢迎消息模板（{member}将被替换）",
            ko="환영 메시지 템플릿 ({member}가 치환됨)",
        ),
        "moderation_enabled": Description(
            en="Enable message moderation",
            zh="启用消息审核",
            ko="메시지 모더레이션 활성화",
        ),
        "blocked_words": Description(
            en="List of blocked words for moderation",
            zh="审核用屏蔽词列表",
            ko="모더레이션용 차단 단어 목록",
        ),
        "ai_welcome": Description(
            en="Use AI to generate personalized welcome messages",
            zh="使用AI生成个性化欢迎消息",
            ko="AI로 개인화된 환영 메시지 생성",
        ),
        "faq_channel_id": Description(
            en="Channel ID for FAQ auto-responses (0 = all channels)",
            zh="FAQ自动回复频道ID（0=所有频道）",
            ko="FAQ 자동 응답 채널 ID (0 = 모든 채널)",
        ),
        "faq_entries": Description(
            en="FAQ keyword-response pairs",
            zh="FAQ关键词-回复对",
            ko="FAQ 키워드-응답 쌍",
        ),
    }


class ChatMonitorConfig(I18nMixin):
    """Configuration for live chat monitoring across platforms."""

    enabled: bool = Field(False, alias="enabled")
    youtube: YouTubeChatConfig = Field(YouTubeChatConfig(), alias="youtube")
    chzzk: ChzzkChatConfig = Field(ChzzkChatConfig(), alias="chzzk")
    discord: DiscordConfig = Field(DiscordConfig(), alias="discord")
    max_retries: int = Field(10, alias="max_retries")
    retry_interval: int = Field(60, alias="retry_interval")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "enabled": Description(
            en="Enable chat monitoring system",
            zh="启用聊天监控系统",
            ko="채팅 모니터링 시스템 활성화",
        ),
        "youtube": Description(
            en="YouTube chat configuration",
            zh="YouTube聊天配置",
            ko="YouTube 채팅 설정",
        ),
        "chzzk": Description(
            en="Chzzk chat configuration", zh="Chzzk聊天配置", ko="치지직 채팅 설정"
        ),
        "discord": Description(
            en="Discord chat configuration",
            zh="Discord聊天配置",
            ko="Discord 채팅 설정",
        ),
        "max_retries": Description(
            en="Maximum retry attempts for reconnection",
            zh="重连最大重试次数",
            ko="재연결 최대 재시도 횟수",
        ),
        "retry_interval": Description(
            en="Retry interval in seconds",
            zh="重试间隔（秒）",
            ko="재시도 간격 (초)",
        ),
    }


class LiveConfig(I18nMixin):
    """Configuration for live streaming platforms integration."""

    chat_monitor: ChatMonitorConfig = Field(ChatMonitorConfig(), alias="chat_monitor")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "chat_monitor": Description(
            en="Configuration for live chat monitoring",
            zh="直播聊天监控配置",
            ko="라이브 채팅 모니터링 설정",
        ),
    }
