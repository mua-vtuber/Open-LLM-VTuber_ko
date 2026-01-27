from typing import AsyncIterator, List, Dict, Any, Optional
from loguru import logger

from ..base_agent import BaseAgent
from ..output_types import SentenceOutput
from ...config_manager import TTSPreprocessorConfig
from ..input_types import BatchInput
from ..stateless_llm.stateless_llm_interface import StatelessLLMInterface

try:
    from mem0 import Memory
except ImportError:
    logger.warning(
        "mem0ai package not installed. Please run 'pip install mem0ai'."
    )
    Memory = None


class Mem0Agent(BaseAgent):
    """
    LLM Agent with mem0 long-term memory support.
    Uses vector database to retrieve relevant information about the user.
    """

    def __init__(
        self,
        llm: StatelessLLMInterface,
        user_id: str,
        system: str,
        live2d_model,
        mem0_config: Dict[str, Any],
        tts_preprocessor_config: TTSPreprocessorConfig = None,
        faster_first_response: bool = True,
        segment_method: str = "pysbd",
    ):
        """
        Initialize mem0 Agent.

        Args:
            llm: Stateless LLM interface for completions.
            user_id: User identifier for memory isolation.
            system: System prompt.
            live2d_model: Live2D model instance.
            mem0_config: mem0 configuration.
            tts_preprocessor_config: TTS preprocessor settings.
            faster_first_response: Optimization for latency.
            segment_method: Sentence segmentation method.
        """
        super().__init__(
            live2d_model=live2d_model,
            tts_preprocessor_config=tts_preprocessor_config,
            faster_first_response=faster_first_response,
            segment_method=segment_method,
        )
        self._llm = llm
        self._user_id = user_id
        self._system = system
        self._mem0_config = mem0_config

        # Initialize mem0 Memory
        if Memory is None:
            raise ImportError(
                "mem0ai package not found. 'pip install mem0ai' is required for Mem0Agent."
            )

        try:
            if mem0_config:
                self._memory = Memory.from_config(mem0_config)
            else:
                self._memory = Memory()
            logger.info(f"mem0 Memory initialized (user_id: {user_id})")
        except Exception as e:
            logger.error(f"Failed to initialize mem0 Memory: {e}")
            self._memory = None

        # Wrap chat method with common transformers
        self.chat = self._apply_transformers(self._chat_internal)

        logger.info(f"Mem0Agent initialized (user_id: {self._user_id})")

    async def _chat_internal(self, input_data: BatchInput) -> AsyncIterator[str]:
        """
        Core chat logic including memory retrieval and LLM call.
        """
        user_message = self._to_text_prompt(input_data)
        logger.debug(f"User message: {user_message}")

        if not user_message.strip():
            logger.warning("Empty user message received.")
            return

        # 1. Retrieve relevant memories from mem0
        relevant_memories = []
        if self._memory:
            try:
                search_results = self._memory.search(
                    query=user_message,
                    user_id=self._user_id,
                )
                if search_results:
                    if isinstance(search_results, dict) and "results" in search_results:
                        relevant_memories = search_results["results"]
                    else:
                        relevant_memories = (
                            search_results if isinstance(search_results, list) else []
                        )
                logger.debug(f"Retrieved {len(relevant_memories)} relevant memories.")
            except Exception as e:
                logger.error(f"Memory search failed: {e}")

        # 2. Augment system prompt with memories
        current_system_prompt = self._system
        if relevant_memories:
            memory_context = "\n\n=== Relevant Memories ===\n"
            for idx, mem in enumerate(relevant_memories, 1):
                memory_text = (
                    mem.get("memory", "") if isinstance(mem, dict) else str(mem)
                )
                memory_context += f"{idx}. {memory_text}\n"
            current_system_prompt = f"{self._system}\n{memory_context}"

        # 3. LLM call
        messages = [
            {"role": "user", "content": user_message},
        ]

        assistant_response = []
        try:
            # Use the provided StatelessLLMInterface
            stream = self._llm.chat_completion(messages, current_system_prompt)

            async for event in stream:
                content = ""
                if isinstance(event, dict) and event.get("type") == "text_delta":
                    content = event.get("text", "")
                elif isinstance(event, str):
                    content = event
                
                if content:
                    assistant_response.append(content)
                    yield content

        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            error_message = f"[Error: {str(e)}]"
            yield error_message
            return

        # 4. Save interaction to mem0
        full_response = "".join(assistant_response)
        if self._memory and full_response.strip():
            try:
                messages_to_save = [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": full_response},
                ]
                self._memory.add(
                    messages=messages_to_save,
                    user_id=self._user_id,
                )
                logger.debug("Interaction saved to mem0.")
            except Exception as e:
                logger.error(f"Failed to save to mem0: {e}")

    async def chat(self, input_data: BatchInput) -> AsyncIterator[SentenceOutput]:
        """Run chat pipeline."""
        # This is replaced by the wrapped version in __init__
        # but kept for interface compliance if called directly
        async for output in self.chat(input_data):
            yield output

    def handle_interrupt(self, heard_response: str) -> None:
        """
        Handle user interruption.
        (Implementation can be expanded to update short-term memory if needed)
        """
        logger.info(f"Interrupt handled. Heard: {heard_response[:50]}...")
        self._interrupt_handled = True

    def set_memory_from_history(self, conf_uid: str, history_uid: str) -> None:
        """
        Load context from history.
        Mem0 relies on its own DB, but this can be used to prime current session.
        """
        logger.info(f"History load requested: {conf_uid}/{history_uid} (Not implemented for Mem0)")
        pass

    def get_all_memories(self) -> List[Dict[str, Any]]:
        """Retrieve all memories for the user."""
        if not self._memory:
            return []
        try:
            all_memories = self._memory.get_all(user_id=self._user_id)
            if isinstance(all_memories, dict) and "results" in all_memories:
                return all_memories["results"]
            return all_memories if isinstance(all_memories, list) else []
        except Exception as e:
            logger.error(f"Memory retrieval failed: {e}")
            return []

    def delete_memory(self, memory_id: str) -> bool:
        """Delete specific memory by ID."""
        if not self._memory:
            return False
        try:
            self._memory.delete(memory_id=memory_id)
            return True
        except Exception as e:
            logger.error(f"Memory deletion failed: {e}")
            return False

    def delete_all_memories(self) -> bool:
        """Delete all memories for the user."""
        if not self._memory:
            return False
        try:
            self._memory.delete_all(user_id=self._user_id)
            return True
        except Exception as e:
            logger.error(f"All memories deletion failed: {e}")
            return False