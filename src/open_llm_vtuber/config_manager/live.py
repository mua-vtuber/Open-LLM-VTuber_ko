from pydantic import Field
from typing import Dict, ClassVar, List
from .i18n import I18nMixin, Description


class BiliBiliLiveConfig(I18nMixin):
    """Configuration for BiliBili Live platform."""

    room_ids: List[int] = Field([], alias="room_ids")
    sessdata: str = Field("", alias="sessdata")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "room_ids": Description(
            en="List of BiliBili live room IDs to monitor", zh="要监控的B站直播间ID列表"
        ),
        "sessdata": Description(
            en="SESSDATA cookie value for authenticated requests (optional)",
            zh="用于认证请求的SESSDATA cookie值（可选）",
        ),
    }


class YouTubeChatConfig(I18nMixin):
    """Configuration for YouTube Live Chat monitoring."""

    enabled: bool = Field(False, alias="enabled")
    api_key: str = Field("", alias="api_key")
    channel_id: str = Field("", alias="channel_id")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "enabled": Description(
            en="Enable YouTube chat monitoring", zh="启用YouTube聊天监控", ko="YouTube 채팅 모니터링 활성화"
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
    redirect_uri: str = Field("http://localhost:12393/chzzk/callback", alias="redirect_uri")
    access_token: str = Field("", alias="access_token")
    refresh_token: str = Field("", alias="refresh_token")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "enabled": Description(
            en="Enable Chzzk chat monitoring", zh="启用Chzzk聊天监控", ko="치지직 채팅 모니터링 활성화"
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


class ChatMonitorConfig(I18nMixin):
    """Configuration for live chat monitoring across platforms."""

    enabled: bool = Field(False, alias="enabled")
    youtube: YouTubeChatConfig = Field(YouTubeChatConfig(), alias="youtube")
    chzzk: ChzzkChatConfig = Field(ChzzkChatConfig(), alias="chzzk")
    max_retries: int = Field(10, alias="max_retries")
    retry_interval: int = Field(60, alias="retry_interval")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "enabled": Description(
            en="Enable chat monitoring system",
            zh="启用聊天监控系统",
            ko="채팅 모니터링 시스템 활성화",
        ),
        "youtube": Description(
            en="YouTube chat configuration", zh="YouTube聊天配置", ko="YouTube 채팅 설정"
        ),
        "chzzk": Description(
            en="Chzzk chat configuration", zh="Chzzk聊天配置", ko="치지직 채팅 설정"
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

    bilibili_live: BiliBiliLiveConfig = Field(
        BiliBiliLiveConfig(), alias="bilibili_live"
    )
    chat_monitor: ChatMonitorConfig = Field(ChatMonitorConfig(), alias="chat_monitor")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "bilibili_live": Description(
            en="Configuration for BiliBili Live platform", zh="B站直播平台配置"
        ),
        "chat_monitor": Description(
            en="Configuration for live chat monitoring",
            zh="直播聊天监控配置",
            ko="라이브 채팅 모니터링 설정",
        ),
    }
