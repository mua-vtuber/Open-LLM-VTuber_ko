"""
OAuth2 token manager for Chzzk (치지직) authentication.

Handles OAuth2 authorization flow, token storage, and token refresh.
"""

from typing import Optional, Dict
from loguru import logger
from pathlib import Path
import json


class ChzzkOAuthManager:
    """
    Manages OAuth2 authentication for Chzzk API.

    Handles:
    - Authorization URL generation
    - Token exchange
    - Token refresh
    - Token persistence
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        token_file: str = "chzzk_tokens.json",
    ):
        """
        Initialize OAuth manager.

        Args:
            client_id: OAuth2 client ID from CHZZK Developer Center
            client_secret: OAuth2 client secret
            redirect_uri: OAuth2 redirect URI
            token_file: Path to store tokens (default: chzzk_tokens.json in cache/)
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.token_file = Path("cache") / token_file
        self._client = None
        self._user_client = None

        # Ensure cache directory exists
        self.token_file.parent.mkdir(parents=True, exist_ok=True)

    def generate_auth_url(self) -> str:
        """
        Generate OAuth2 authorization URL.

        Returns:
            str: Authorization URL for user to visit
        """
        try:
            from chzzkpy import Client

            # Create client
            client = Client(self.client_id, self.client_secret)

            # Generate authorization URL
            auth_url = client.generate_authorization_token_url(
                redirect_uri=self.redirect_uri
            )

            logger.info(f"[ChzzkOAuth] Generated auth URL: {auth_url}")
            return auth_url

        except ImportError as e:
            logger.error(
                "[ChzzkOAuth] Failed to import chzzkpy. "
                "Please install: pip install chzzkpy"
            )
            raise RuntimeError("chzzkpy not installed") from e
        except Exception as e:
            logger.error(f"[ChzzkOAuth] Error generating auth URL: {e}")
            raise

    async def exchange_code(self, code: str) -> Dict[str, str]:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            Dict containing access_token and refresh_token
        """
        try:
            from chzzkpy import Client

            # Create client
            client = Client(self.client_id, self.client_secret)

            # Generate user client with authorization code
            user_client = await client.generate_user_client(
                code=code, redirect_uri=self.redirect_uri
            )

            # Extract tokens
            tokens = {
                "access_token": user_client.access_token,
                "refresh_token": user_client.refresh_token,
            }

            # Save tokens
            self._save_tokens(tokens)

            logger.success("[ChzzkOAuth] Successfully obtained tokens")
            return tokens

        except Exception as e:
            logger.error(f"[ChzzkOAuth] Error exchanging code: {e}")
            raise

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, str]:
        """
        Refresh access token using refresh token.

        Args:
            refresh_token: Refresh token

        Returns:
            Dict containing new access_token and refresh_token
        """
        try:
            from chzzkpy import Client

            # Create client
            client = Client(self.client_id, self.client_secret)

            # Refresh token
            user_client = await client.generate_user_client(refresh_token=refresh_token)

            # Extract new tokens
            tokens = {
                "access_token": user_client.access_token,
                "refresh_token": user_client.refresh_token,
            }

            # Save tokens
            self._save_tokens(tokens)

            logger.success("[ChzzkOAuth] Successfully refreshed tokens")
            return tokens

        except Exception as e:
            logger.error(f"[ChzzkOAuth] Error refreshing token: {e}")
            raise

    def _save_tokens(self, tokens: Dict[str, str]) -> None:
        """
        Save tokens to file.

        Args:
            tokens: Dictionary containing tokens
        """
        try:
            with open(self.token_file, "w") as f:
                json.dump(tokens, f, indent=2)
            logger.debug(f"[ChzzkOAuth] Tokens saved to {self.token_file}")
        except Exception as e:
            logger.error(f"[ChzzkOAuth] Error saving tokens: {e}")

    def load_tokens(self) -> Optional[Dict[str, str]]:
        """
        Load tokens from file.

        Returns:
            Dictionary containing tokens, or None if not found
        """
        try:
            if not self.token_file.exists():
                logger.debug("[ChzzkOAuth] Token file not found")
                return None

            with open(self.token_file, "r") as f:
                tokens = json.load(f)

            logger.debug("[ChzzkOAuth] Tokens loaded successfully")
            return tokens

        except Exception as e:
            logger.error(f"[ChzzkOAuth] Error loading tokens: {e}")
            return None

    def clear_tokens(self) -> None:
        """Clear stored tokens."""
        try:
            if self.token_file.exists():
                self.token_file.unlink()
                logger.info("[ChzzkOAuth] Tokens cleared")
        except Exception as e:
            logger.error(f"[ChzzkOAuth] Error clearing tokens: {e}")

    async def get_user_client(self, access_token: str, refresh_token: str):
        """
        Get authenticated user client.

        Args:
            access_token: Current access token
            refresh_token: Current refresh token

        Returns:
            Authenticated user client
        """
        try:
            from chzzkpy import Client

            # Create base client
            client = Client(self.client_id, self.client_secret)

            # Create user client with tokens
            user_client = await client.generate_user_client(
                access_token=access_token, refresh_token=refresh_token
            )

            return user_client

        except Exception as e:
            logger.error(f"[ChzzkOAuth] Error creating user client: {e}")
            # Try to refresh token
            try:
                logger.info("[ChzzkOAuth] Attempting to refresh token...")
                new_tokens = await self.refresh_access_token(refresh_token)
                user_client = await client.generate_user_client(
                    access_token=new_tokens["access_token"],
                    refresh_token=new_tokens["refresh_token"],
                )
                return user_client
            except Exception as refresh_error:
                logger.error(f"[ChzzkOAuth] Failed to refresh token: {refresh_error}")
                raise

    def is_authenticated(self) -> bool:
        """
        Check if tokens are available.

        Returns:
            bool: True if tokens exist
        """
        tokens = self.load_tokens()
        return (
            tokens is not None
            and "access_token" in tokens
            and "refresh_token" in tokens
        )
