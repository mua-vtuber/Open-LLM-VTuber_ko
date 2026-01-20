"""Live streaming related routes (Chzzk OAuth, etc.)."""

from fastapi import APIRouter
from starlette.responses import RedirectResponse, HTMLResponse
from loguru import logger

from ..service_context import ServiceContext
from ..chat_monitor.chzzk_oauth_manager import ChzzkOAuthManager


def init_live_routes(default_context_cache: ServiceContext) -> APIRouter:
    """
    Create routes for live streaming related endpoints.

    Args:
        default_context_cache: Default service context cache.

    Returns:
        APIRouter: Router with live streaming endpoints.
    """
    router = APIRouter()

    @router.get("/chzzk/auth")
    async def chzzk_auth_init():
        """
        Initiate Chzzk OAuth authorization flow.

        Returns a redirect to Chzzk's authorization page where the user can grant permissions.
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
            logger.info(f"[Chzzk] Redirecting to authorization URL: {auth_url}")

            return RedirectResponse(url=auth_url)

        except Exception as e:
            logger.error(f"[Chzzk] Error initiating OAuth: {e}")
            return HTMLResponse(
                content=f"<h1>Error</h1><p>Failed to initiate OAuth: {str(e)}</p>",
                status_code=500,
            )

    @router.get("/chzzk/callback")
    async def chzzk_auth_callback(code: str, state: str = None):
        """
        Handle Chzzk OAuth callback.

        Args:
            code: Authorization code from Chzzk
            state: Optional state parameter for CSRF protection

        Returns:
            Success or error message
        """
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
