"""Token counting utility with tiktoken and CJK fallback."""

from __future__ import annotations

from loguru import logger


class TokenCounter:
    """Counts tokens for budget management.

    Uses tiktoken when available, falls back to character-based estimation
    with CJK-aware heuristics.
    """

    def __init__(self, model: str = "gpt-4"):
        self._encoder = None
        self._model = model
        try:
            import tiktoken

            self._encoder = tiktoken.encoding_for_model(model)
        except Exception:
            logger.debug(
                "tiktoken not available or model not found, "
                "using character-based estimation"
            )

    def count(self, text: str) -> int:
        """Count tokens in a text string."""
        if self._encoder:
            return len(self._encoder.encode(text))
        return self._estimate_tokens(text)

    def count_messages(self, messages: list[dict]) -> int:
        """Count total tokens in a list of chat messages."""
        total = 0
        for msg in messages:
            # Per-message overhead (role, formatting)
            total += 4
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.count(content)
            elif isinstance(content, list):
                # Multimodal content (text + images)
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        total += self.count(item.get("text", ""))
                    elif isinstance(item, dict) and item.get("type") == "image_url":
                        total += 85  # Approximate token cost for image reference
            if msg.get("name"):
                total += self.count(msg["name"])
        total += 2  # Priming tokens
        return total

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimate tokens using character-based heuristics.

        English: ~4 characters per token
        CJK (Korean, Japanese, Chinese): ~2 characters per token
        """
        cjk_count = sum(
            1
            for c in text
            if "\u4e00" <= c <= "\u9fff"  # CJK Unified
            or "\uac00" <= c <= "\ud7af"  # Korean Hangul
            or "\u3040" <= c <= "\u309f"  # Hiragana
            or "\u30a0" <= c <= "\u30ff"  # Katakana
        )
        non_cjk = len(text) - cjk_count
        return max(1, (non_cjk // 4) + (cjk_count // 2))
