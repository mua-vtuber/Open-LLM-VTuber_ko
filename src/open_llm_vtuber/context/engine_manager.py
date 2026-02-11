"""Engine initialization and management."""

from typing import TYPE_CHECKING
from loguru import logger

from ..live2d_model import Live2dModel
from ..asr.asr_interface import ASRInterface
from ..tts.tts_interface import TTSInterface
from ..vad.vad_interface import VADInterface
from ..agent.agents.agent_interface import AgentInterface
from ..translate.translate_interface import TranslateInterface

from ..asr.asr_factory import ASRFactory
from ..tts.tts_factory import TTSFactory
from ..vad.vad_factory import VADFactory
from ..agent.agent_factory import AgentFactory
from ..translate.translate_factory import TranslateFactory

from ..config_manager import (
    AgentConfig,
    CharacterConfig,
    SystemConfig,
    ASRConfig,
    TTSConfig,
    VADConfig,
    TranslatorConfig,
)

if TYPE_CHECKING:
    from ..mcpp.tool_manager import ToolManager
    from ..mcpp.tool_executor import ToolExecutor


class EngineManager:
    """Manages initialization and lifecycle of all AI engines."""

    def __init__(self):
        self.live2d_model: Live2dModel | None = None
        self.asr_engine: ASRInterface | None = None
        self.tts_engine: TTSInterface | None = None
        self.vad_engine: VADInterface | None = None
        self.agent_engine: AgentInterface | None = None
        self.translate_engine: TranslateInterface | None = None

    def init_live2d(
        self, live2d_model_name: str, character_config: CharacterConfig
    ) -> None:
        """Initialize Live2D model."""
        logger.info(f"Initializing Live2D: {live2d_model_name}")
        try:
            self.live2d_model = Live2dModel(live2d_model_name)
            character_config.live2d_model_name = live2d_model_name
        except Exception as e:
            logger.critical(f"Error initializing Live2D: {e}")
            logger.critical("Try to proceed without Live2D...")

    def init_asr(self, asr_config: ASRConfig, character_config: CharacterConfig) -> None:
        """Initialize ASR engine."""
        if not self.asr_engine or (character_config.asr_config != asr_config):
            logger.info(f"Initializing ASR: {asr_config.asr_model}")
            self.asr_engine = ASRFactory.get_asr_system(
                asr_config.asr_model,
                **getattr(asr_config, asr_config.asr_model).model_dump(),
            )
            character_config.asr_config = asr_config
        else:
            logger.info("ASR already initialized with the same config.")

    def init_tts(self, tts_config: TTSConfig, character_config: CharacterConfig) -> None:
        """Initialize TTS engine."""
        if not self.tts_engine or (character_config.tts_config != tts_config):
            logger.info(f"Initializing TTS: {tts_config.tts_model}")
            self.tts_engine = TTSFactory.get_tts_engine(
                tts_config.tts_model,
                **getattr(tts_config, tts_config.tts_model.lower()).model_dump(),
            )
            character_config.tts_config = tts_config
        else:
            logger.info("TTS already initialized with the same config.")

    def init_vad(self, vad_config: VADConfig, character_config: CharacterConfig) -> None:
        """Initialize VAD engine."""
        if vad_config.vad_model is None:
            logger.info("VAD is disabled.")
            self.vad_engine = None
            return

        if not self.vad_engine or (character_config.vad_config != vad_config):
            logger.info(f"Initializing VAD: {vad_config.vad_model}")
            self.vad_engine = VADFactory.get_vad_engine(
                vad_config.vad_model,
                **getattr(vad_config, vad_config.vad_model.lower()).model_dump(),
            )
            character_config.vad_config = vad_config
        else:
            logger.info("VAD already initialized with the same config.")

    async def init_agent(
        self,
        agent_config: AgentConfig,
        persona_prompt: str,
        character_config: CharacterConfig,
        system_config: SystemConfig,
        system_prompt: str,
        tool_manager: "ToolManager | None",
        tool_executor: "ToolExecutor | None",
        mcp_prompt: str,
        memory_config=None,
    ) -> None:
        """Initialize or update the agent engine based on configuration."""
        logger.info(f"Initializing Agent: {agent_config.conversation_agent_choice}")

        if (
            self.agent_engine is not None
            and agent_config == character_config.agent_config
            and persona_prompt == character_config.persona_prompt
        ):
            logger.debug("Agent already initialized with the same config.")
            return

        avatar = character_config.avatar or ""

        try:
            self.agent_engine = AgentFactory.create_agent(
                conversation_agent_choice=agent_config.conversation_agent_choice,
                agent_settings=agent_config.agent_settings.model_dump(),
                llm_configs=agent_config.llm_configs.model_dump(),
                system_prompt=system_prompt,
                live2d_model=self.live2d_model,
                tts_preprocessor_config=character_config.tts_preprocessor_config,
                character_avatar=avatar,
                system_config=system_config.model_dump(),
                tool_manager=tool_manager,
                tool_executor=tool_executor,
                mcp_prompt_string=mcp_prompt,
                memory_config=memory_config,
            )

            logger.debug(f"Agent choice: {agent_config.conversation_agent_choice}")
            logger.debug(f"System prompt: {system_prompt}")

            character_config.agent_config = agent_config

        except Exception as e:
            logger.error(f"Failed to initialize agent: {e}")
            raise

    def init_translate(
        self, translator_config: TranslatorConfig, character_config: CharacterConfig
    ) -> None:
        """Initialize or update the translation engine."""
        if not translator_config.translate_audio:
            logger.debug("Translation is disabled.")
            return

        current_translator_config = (
            character_config.tts_preprocessor_config.translator_config
        )
        if not self.translate_engine or current_translator_config != translator_config:
            logger.info(
                f"Initializing Translator: {translator_config.translate_provider}"
            )
            self.translate_engine = TranslateFactory.get_translator(
                translator_config.translate_provider,
                getattr(
                    translator_config, translator_config.translate_provider
                ).model_dump(),
            )
            character_config.tts_preprocessor_config.translator_config = (
                translator_config
            )
        else:
            logger.info("Translation already initialized with the same config.")

    async def close(self) -> None:
        """Clean up engine resources."""
        if self.agent_engine and hasattr(self.agent_engine, "close"):
            await self.agent_engine.close()
            logger.info("Agent engine closed.")
