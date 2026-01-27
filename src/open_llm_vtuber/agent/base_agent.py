from typing import AsyncIterator, List, Dict, Any, Callable, Union, Optional
from abc import abstractmethod
from loguru import logger
import numpy as np

from .agents.agent_interface import AgentInterface
from .output_types import SentenceOutput, DisplayText
from .input_types import BatchInput, TextSource
from .transformers import (
    sentence_divider,
    actions_extractor,
    tts_filter,
    display_processor,
)
from ..config_manager import TTSPreprocessorConfig


class BaseAgent(AgentInterface):
    """
    Base class for Agent implementations providing common utilities and pipeline setup.
    """

    _system: str = "You are a helpful assistant."

    def __init__(
        self,
        live2d_model=None,
        tts_preprocessor_config: TTSPreprocessorConfig = None,
        faster_first_response: bool = True,
        segment_method: str = "pysbd",
    ):
        """Initialize base agent with common configurations."""
        super().__init__()
        self._live2d_model = live2d_model
        self._tts_preprocessor_config = tts_preprocessor_config
        self._faster_first_response = faster_first_response
        self._segment_method = segment_method
        self._interrupt_handled = False

    def set_system(self, system: str):
        """Set the system prompt."""
        logger.debug(f"Agent: Setting system prompt: '''{system}'''")
        self._system = system

    def reset_interrupt(self) -> None:
        """Reset interrupt flag."""
        self._interrupt_handled = False

    def _apply_transformers(self, chat_func: Callable) -> Callable:
        """
        Apply common transformers (decorators) to a chat function.
        
        Args:
            chat_func: The core chat function to wrap.
            
        Returns:
            Callable: Wrapped chat function with all transformers applied.
        """
        return tts_filter(self._tts_preprocessor_config)(
            display_processor()(
                actions_extractor(self._live2d_model)(
                    sentence_divider(
                        faster_first_response=self._faster_first_response,
                        segment_method=self._segment_method,
                        valid_tags=["think"],
                    )(chat_func)
                )
            )
        )

    def _to_text_prompt(self, input_data: BatchInput) -> str:
        """
        Format input data to a plain text prompt.
        
        Args:
            input_data: BatchInput object.
            
        Returns:
            str: Combined text prompt.
        """
        message_parts = []

        for text_data in input_data.texts:
            if text_data.source == TextSource.INPUT:
                message_parts.append(text_data.content)
            elif text_data.source == TextSource.CLIPBOARD:
                message_parts.append(
                    f"[User shared content from clipboard: {text_data.content}]"
                )

        if input_data.images:
            message_parts.append("\n[User has also provided images]")

        return "\n".join(message_parts).strip()

    @abstractmethod
    async def chat(self, input_data: BatchInput) -> AsyncIterator[SentenceOutput]:
        """Implemented by subclasses."""
        pass

    @abstractmethod
    def handle_interrupt(self, heard_response: str) -> None:
        """Implemented by subclasses."""
        pass

    @abstractmethod
    def set_memory_from_history(self, conf_uid: str, history_uid: str) -> None:
        """Implemented by subclasses."""
        pass
