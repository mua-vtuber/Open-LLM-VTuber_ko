"""Live streaming related routes (Chzzk OAuth, etc.).

라이브 스트리밍 연동을 위한 API 라우트.
Chzzk OAuth 인증 등 플랫폼별 연동 기능을 제공합니다.
"""

import html
import secrets
import time
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from fastapi import APIRouter
from starlette.responses import RedirectResponse, HTMLResponse
from loguru import logger

from ..service_context import ServiceContext
from ..chat_monitor.chzzk_oauth_manager import ChzzkOAuthManager

# CSRF state tokens for OAuth flow: maps state -> creation timestamp
_oauth_states: dict[str, float] = {}

_OAUTH_STATE_TTL = 600  # 10 minutes


def _cleanup_expired_oauth_states() -> None:
    """Remove OAuth state tokens older than the TTL."""
    now = time.time()
    expired = [s for s, ts in _oauth_states.items() if now - ts > _OAUTH_STATE_TTL]
    for s in expired:
        del _oauth_states[s]


def init_live_routes(default_context_cache: ServiceContext) -> APIRouter:
    """
    Create routes for live streaming related endpoints.

    Args:
        default_context_cache: Default service context cache.

    Returns:
        APIRouter: Router with live streaming endpoints.
    """
    router = APIRouter()

    @router.get(
        "/chzzk/auth",
        tags=["live"],
        summary="Chzzk OAuth 인증 시작",
        description="Chzzk OAuth 인증 플로우를 시작합니다. Chzzk 인증 페이지로 리다이렉트됩니다.",
        responses={
            307: {"description": "Chzzk 인증 페이지로 리다이렉트"},
            400: {"description": "OAuth 자격 증명 미설정"},
            500: {"description": "OAuth 초기화 오류"},
        },
    )
    async def chzzk_auth_init():
        """
        Chzzk OAuth 인증 플로우를 시작합니다.

        사용자를 Chzzk의 인증 페이지로 리다이렉트하여 권한을 부여받습니다.
        conf.yaml에 client_id와 client_secret이 설정되어 있어야 합니다.

        Returns:
            RedirectResponse: Chzzk 인증 페이지로 리다이렉트
        """
        try:
            chzzk_config = default_context_cache.config.live_config.chat_monitor.chzzk

            if not chzzk_config.client_id or not chzzk_config.client_secret:
                return HTMLResponse(
                    content="<h1>Error</h1><p>Chzzk OAuth credentials not configured. "
                    "Please set client_id and client_secret in conf.yaml</p>",
                    status_code=400,
                )

            oauth_manager = ChzzkOAuthManager(
                client_id=chzzk_config.client_id,
                client_secret=chzzk_config.client_secret,
                redirect_uri=chzzk_config.redirect_uri,
            )

            auth_url = oauth_manager.generate_auth_url()

            # Generate CSRF state token and append to auth URL
            state = secrets.token_urlsafe(32)
            _oauth_states[state] = time.time()
            _cleanup_expired_oauth_states()

            parsed = urlparse(auth_url)
            qs = parse_qs(parsed.query)
            qs["state"] = [state]
            new_query = urlencode(qs, doseq=True)
            auth_url = urlunparse(parsed._replace(query=new_query))

            logger.info(f"[Chzzk] Redirecting to authorization URL: {auth_url}")

            return RedirectResponse(url=auth_url)

        except Exception as e:
            logger.error(f"[Chzzk] Error initiating OAuth: {e}")
            escaped_error = html.escape(str(e))
            return HTMLResponse(
                content=f"<h1>Error</h1><p>Failed to initiate OAuth: {escaped_error}</p>",
                status_code=500,
            )

    @router.get(
        "/chzzk/callback",
        tags=["live"],
        summary="Chzzk OAuth 콜백",
        description="Chzzk OAuth 인증 완료 후 호출되는 콜백 엔드포인트입니다.",
        responses={
            200: {"description": "인증 성공"},
            400: {"description": "OAuth 자격 증명 미설정"},
            500: {"description": "토큰 교환 오류"},
        },
    )
    async def chzzk_auth_callback(code: str, state: str = None):
        """
        Chzzk OAuth 콜백을 처리합니다.

        Chzzk에서 받은 인증 코드를 액세스 토큰으로 교환하고
        cache/chzzk_tokens.json에 저장합니다.

        Args:
            code: Chzzk에서 받은 인증 코드
            state: CSRF 보호를 위한 상태 파라미터

        Returns:
            HTMLResponse: 성공 또는 오류 메시지
        """
        # Validate CSRF state token
        _cleanup_expired_oauth_states()

        if not state or state not in _oauth_states:
            logger.warning(
                "[Chzzk] OAuth callback with missing or invalid state parameter"
            )
            return HTMLResponse(
                content=_get_chzzk_error_html(
                    "Invalid or missing OAuth state parameter. "
                    "Please restart the authentication flow."
                ),
                status_code=400,
            )

        created_at = _oauth_states.pop(state)
        if time.time() - created_at > _OAUTH_STATE_TTL:
            logger.warning("[Chzzk] OAuth callback with expired state parameter")
            return HTMLResponse(
                content=_get_chzzk_error_html(
                    "OAuth state has expired. Please restart the authentication flow."
                ),
                status_code=400,
            )

        try:
            chzzk_config = default_context_cache.config.live_config.chat_monitor.chzzk

            if not chzzk_config.client_id or not chzzk_config.client_secret:
                return HTMLResponse(
                    content="<h1>Error</h1><p>Chzzk OAuth credentials not configured.</p>",
                    status_code=400,
                )

            oauth_manager = ChzzkOAuthManager(
                client_id=chzzk_config.client_id,
                client_secret=chzzk_config.client_secret,
                redirect_uri=chzzk_config.redirect_uri,
            )

            logger.info("[Chzzk] Exchanging authorization code for tokens...")
            await oauth_manager.exchange_code(code)

            logger.success(
                "[Chzzk] OAuth authentication successful! Tokens have been saved to cache/chzzk_tokens.json"
            )

            return HTMLResponse(
                content=_get_chzzk_success_html(),
                status_code=200,
            )

        except Exception as e:
            logger.error(f"[Chzzk] OAuth callback error: {e}")
            return HTMLResponse(
                content=_get_chzzk_error_html(str(e)),
                status_code=500,
            )

    return router


def _get_chzzk_success_html() -> str:
    """Return HTML for successful Chzzk OAuth."""
    return """
    <html>
    <head>
        <title>Chzzk OAuth Success</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 600px;
                margin: 50px auto;
                padding: 20px;
                background-color: #f5f5f5;
            }
            .success {
                background-color: #d4edda;
                border: 1px solid #c3e6cb;
                color: #155724;
                padding: 20px;
                border-radius: 5px;
            }
            h1 { margin-top: 0; }
            code {
                background-color: #f8f9fa;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: monospace;
            }
            .next-steps {
                margin-top: 20px;
                padding: 15px;
                background-color: white;
                border-radius: 5px;
            }
        </style>
    </head>
    <body>
        <div class="success">
            <h1>✅ Chzzk OAuth Authentication Successful!</h1>
            <p>Your OAuth tokens have been saved successfully.</p>

            <div class="next-steps">
                <h2>Next Steps:</h2>
                <ol>
                    <li>The tokens are saved in <code>cache/chzzk_tokens.json</code></li>
                    <li>Make sure <code>chat_monitor.chzzk.enabled</code> is set to <code>true</code> in <code>conf.yaml</code></li>
                    <li>Restart the Open-LLM-VTuber server if it's running</li>
                    <li>Chzzk chat monitoring will start automatically when you begin streaming</li>
                </ol>
            </div>

            <p style="margin-top: 20px;">
                <strong>Note:</strong> If the tokens expire, you can re-authenticate by visiting
                <code>/chzzk/auth</code> again.
            </p>
        </div>
    </body>
    </html>
    """


def _get_chzzk_error_html(error: str) -> str:
    """Return HTML for Chzzk OAuth error."""
    error = html.escape(error)
    return f"""
    <html>
    <head>
        <title>Chzzk OAuth Error</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 600px;
                margin: 50px auto;
                padding: 20px;
                background-color: #f5f5f5;
            }}
            .error {{
                background-color: #f8d7da;
                border: 1px solid #f5c6cb;
                color: #721c24;
                padding: 20px;
                border-radius: 5px;
            }}
        </style>
    </head>
    <body>
        <div class="error">
            <h1>❌ OAuth Authentication Failed</h1>
            <p><strong>Error:</strong> {error}</p>
            <p>Please try again by visiting <code>/chzzk/auth</code></p>
        </div>
    </body>
    </html>
    """
