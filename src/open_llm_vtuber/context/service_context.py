"""
Service Context - Facade integrating all context managers.

This is the main entry point for service context, composing specialized
managers for different responsibilities.
"""

import os
import json
from typing import Callable
from loguru import logger
from fastapi import WebSocket

from prompts import prompt_loader

from ..live2d_model import Live2dModel
from ..asr.asr_interface import ASRInterface
from ..tts.tts_interface import TTSInterface
from ..vad.vad_interface import VADInterface
from ..agent.agents.agent_interface import AgentInterface
from ..translate.translate_interface import TranslateInterface

from ..mcpp.server_registry import ServerRegistry
from ..mcpp.tool_adapter import ToolAdapter

from ..config_manager import (
    Config,
    CharacterConfig,
    SystemConfig,
    read_yaml,
    validate_config,
)

from .engine_manager import EngineManager
from .mcp_manager import MCPManager


def deep_merge(dict1: dict, dict2: dict) -> dict:
    """Recursively merges dict2 into dict1, prioritizing values from dict2."""
    result = dict1.copy()
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class ServiceContext:
    """
    Facade for service context management.

    Composes specialized managers for clean separation of concerns:
    - EngineManager: AI engine initialization and management
    - MCPManager: MCP component management
    """

    def __init__(self):
        # Configuration
        self.config: Config | None = None
        self.system_config: SystemConfig | None = None
        self.character_config: CharacterConfig | None = None

        # Managers
        self._engine_manager = EngineManager()
        self._mcp_manager = MCPManager()

        # Session state
        self.system_prompt: str | None = None
        self.history_uid: str = ""
        self.send_text: Callable | None = None
        self.client_uid: str | None = None

    # ==========================================================================
    # Properties - Delegate to managers for backward compatibility
    # ==========================================================================

    @property
    def live2d_model(self) -> Live2dModel | None:
        return self._engine_manager.live2d_model

    @live2d_model.setter
    def live2d_model(self, value: Live2dModel | None):
        self._engine_manager.live2d_model = value

    @property
    def asr_engine(self) -> ASRInterface | None:
        return self._engine_manager.asr_engine

    @asr_engine.setter
    def asr_engine(self, value: ASRInterface | None):
        self._engine_manager.asr_engine = value

    @property
    def tts_engine(self) -> TTSInterface | None:
        return self._engine_manager.tts_engine

    @tts_engine.setter
    def tts_engine(self, value: TTSInterface | None):
        self._engine_manager.tts_engine = value

    @property
    def vad_engine(self) -> VADInterface | None:
        return self._engine_manager.vad_engine

    @vad_engine.setter
    def vad_engine(self, value: VADInterface | None):
        self._engine_manager.vad_engine = value

    @property
    def agent_engine(self) -> AgentInterface | None:
        return self._engine_manager.agent_engine

    @agent_engine.setter
    def agent_engine(self, value: AgentInterface | None):
        self._engine_manager.agent_engine = value

    @property
    def translate_engine(self) -> TranslateInterface | None:
        return self._engine_manager.translate_engine

    @translate_engine.setter
    def translate_engine(self, value: TranslateInterface | None):
        self._engine_manager.translate_engine = value

    @property
    def mcp_server_registery(self) -> ServerRegistry | None:
        return self._mcp_manager.server_registry

    @mcp_server_registery.setter
    def mcp_server_registery(self, value: ServerRegistry | None):
        self._mcp_manager.server_registry = value

    @property
    def tool_adapter(self) -> ToolAdapter | None:
        return self._mcp_manager.tool_adapter

    @tool_adapter.setter
    def tool_adapter(self, value: ToolAdapter | None):
        self._mcp_manager.tool_adapter = value

    @property
    def tool_manager(self):
        return self._mcp_manager.tool_manager

    @property
    def mcp_client(self):
        return self._mcp_manager.mcp_client

    @property
    def tool_executor(self):
        return self._mcp_manager.tool_executor

    @property
    def mcp_prompt(self) -> str:
        return self._mcp_manager.mcp_prompt

    # ==========================================================================
    # String representation
    # ==========================================================================

    def __str__(self):
        return (
            f"ServiceContext:\n"
            f"  System Config: {'Loaded' if self.system_config else 'Not Loaded'}\n"
            f"    Details: {json.dumps(self.system_config.model_dump(), indent=6) if self.system_config else 'None'}\n"
            f"  Live2D Model: {self.live2d_model.model_info if self.live2d_model else 'Not Loaded'}\n"
            f"  ASR Engine: {type(self.asr_engine).__name__ if self.asr_engine else 'Not Loaded'}\n"
            f"    Config: {json.dumps(self.character_config.asr_config.model_dump(), indent=6) if self.character_config and self.character_config.asr_config else 'None'}\n"
            f"  TTS Engine: {type(self.tts_engine).__name__ if self.tts_engine else 'Not Loaded'}\n"
            f"    Config: {json.dumps(self.character_config.tts_config.model_dump(), indent=6) if self.character_config and self.character_config.tts_config else 'None'}\n"
            f"  LLM Engine: {type(self.agent_engine).__name__ if self.agent_engine else 'Not Loaded'}\n"
            f"    Agent Config: {json.dumps(self.character_config.agent_config.model_dump(), indent=6) if self.character_config and self.character_config.agent_config else 'None'}\n"
            f"  VAD Engine: {type(self.vad_engine).__name__ if self.vad_engine else 'Not Loaded'}\n"
            f"    VAD Config: {json.dumps(self.character_config.vad_config.model_dump(), indent=6) if self.character_config and self.character_config.vad_config else 'None'}\n"
            f"  System Prompt: {self.system_prompt or 'Not Set'}\n"
            f"  MCP Enabled: {'Yes' if self.mcp_client else 'No'}"
        )

    # ==========================================================================
    # Lifecycle methods
    # ==========================================================================

    async def close(self):
        """Clean up resources."""
        logger.info("Closing ServiceContext resources...")
        await self._mcp_manager.close()
        await self._engine_manager.close()
        logger.info("ServiceContext closed.")

    async def load_cache(
        self,
        config: Config,
        system_config: SystemConfig,
        character_config: CharacterConfig,
        live2d_model: Live2dModel,
        asr_engine: ASRInterface,
        tts_engine: TTSInterface,
        vad_engine: VADInterface,
        agent_engine: AgentInterface,
        translate_engine: TranslateInterface | None,
        mcp_server_registery: ServerRegistry | None = None,
        tool_adapter: ToolAdapter | None = None,
        send_text: Callable = None,
        client_uid: str = None,
    ) -> None:
        """Load ServiceContext with pre-initialized instances (pass by reference)."""
        if not character_config:
            raise ValueError("character_config cannot be None")
        if not system_config:
            raise ValueError("system_config cannot be None")

        # Store configurations
        self.config = config
        self.system_config = system_config
        self.character_config = character_config
        self.send_text = send_text
        self.client_uid = client_uid

        # Load engines by reference
        self._engine_manager.live2d_model = live2d_model
        self._engine_manager.asr_engine = asr_engine
        self._engine_manager.tts_engine = tts_engine
        self._engine_manager.vad_engine = vad_engine
        self._engine_manager.agent_engine = agent_engine
        self._engine_manager.translate_engine = translate_engine

        # Load MCP components by reference
        self._mcp_manager.server_registry = mcp_server_registery
        self._mcp_manager.tool_adapter = tool_adapter

        # Initialize session-specific MCP components
        agent_settings = character_config.agent_config.agent_settings.basic_memory_agent
        await self._mcp_manager.initialize(
            use_mcpp=agent_settings.use_mcpp,
            enabled_servers=agent_settings.mcp_enabled_servers,
            send_text=send_text,
            client_uid=client_uid,
        )

        logger.debug(f"Loaded service context with cache: {character_config}")

    async def load_from_config(self, config: Config) -> None:
        """Load ServiceContext from config, reinitializing instances as needed."""
        if not self.config:
            self.config = config

        if not self.system_config:
            self.system_config = config.system_config

        if not self.character_config:
            self.character_config = config.character_config

        char_config = config.character_config

        # Initialize engines
        self._engine_manager.init_live2d(
            char_config.live2d_model_name, self.character_config
        )
        self._engine_manager.init_asr(char_config.asr_config, self.character_config)
        self._engine_manager.init_tts(char_config.tts_config, self.character_config)
        self._engine_manager.init_vad(char_config.vad_config, self.character_config)

        # Initialize ToolAdapter if needed
        agent_settings = char_config.agent_config.agent_settings.basic_memory_agent
        if agent_settings.use_mcpp and not self._mcp_manager.tool_adapter:
            if not self._mcp_manager.server_registry:
                self._mcp_manager.server_registry = ServerRegistry()
            self._mcp_manager.ensure_tool_adapter(self._mcp_manager.server_registry)

        # Initialize MCP components
        await self._mcp_manager.initialize(
            use_mcpp=agent_settings.use_mcpp,
            enabled_servers=agent_settings.mcp_enabled_servers,
            send_text=self.send_text,
            client_uid=self.client_uid,
        )

        # Construct system prompt and initialize agent
        system_prompt = await self.construct_system_prompt(char_config.persona_prompt)
        await self._engine_manager.init_agent(
            agent_config=char_config.agent_config,
            persona_prompt=char_config.persona_prompt,
            character_config=self.character_config,
            system_config=self.system_config,
            system_prompt=system_prompt,
            tool_manager=self._mcp_manager.tool_manager,
            tool_executor=self._mcp_manager.tool_executor,
            mcp_prompt=self._mcp_manager.mcp_prompt,
        )
        self.system_prompt = system_prompt

        # Initialize translator
        self._engine_manager.init_translate(
            char_config.tts_preprocessor_config.translator_config,
            self.character_config,
        )

        # Update config references
        self.config = config
        self.system_config = config.system_config or self.system_config
        self.character_config = config.character_config

    # ==========================================================================
    # Delegation methods for backward compatibility
    # ==========================================================================

    def init_live2d(self, live2d_model_name: str) -> None:
        """Initialize Live2D model."""
        self._engine_manager.init_live2d(live2d_model_name, self.character_config)

    def init_asr(self, asr_config) -> None:
        """Initialize ASR engine."""
        self._engine_manager.init_asr(asr_config, self.character_config)

    def init_tts(self, tts_config) -> None:
        """Initialize TTS engine."""
        self._engine_manager.init_tts(tts_config, self.character_config)

    def init_vad(self, vad_config) -> None:
        """Initialize VAD engine."""
        self._engine_manager.init_vad(vad_config, self.character_config)

    async def init_agent(self, agent_config, persona_prompt: str) -> None:
        """Initialize agent engine."""
        system_prompt = await self.construct_system_prompt(persona_prompt)
        await self._engine_manager.init_agent(
            agent_config=agent_config,
            persona_prompt=persona_prompt,
            character_config=self.character_config,
            system_config=self.system_config,
            system_prompt=system_prompt,
            tool_manager=self._mcp_manager.tool_manager,
            tool_executor=self._mcp_manager.tool_executor,
            mcp_prompt=self._mcp_manager.mcp_prompt,
        )
        self.system_prompt = system_prompt
        self.character_config.agent_config = agent_config

    def init_translate(self, translator_config) -> None:
        """Initialize translation engine."""
        self._engine_manager.init_translate(translator_config, self.character_config)

    # ==========================================================================
    # Utility methods
    # ==========================================================================

    async def construct_system_prompt(self, persona_prompt: str) -> str:
        """Construct system prompt by appending tool prompts to persona prompt."""
        logger.debug(f"constructing persona_prompt: '''{persona_prompt}'''")

        for prompt_name, prompt_file in self.system_config.tool_prompts.items():
            if prompt_name in ("group_conversation_prompt", "proactive_speak_prompt"):
                continue

            prompt_content = prompt_loader.load_util(prompt_file)

            if prompt_name == "live2d_expression_prompt":
                prompt_content = prompt_content.replace(
                    "[<insert_emomap_keys>]", self.live2d_model.emo_str
                )

            if prompt_name == "mcp_prompt":
                continue

            persona_prompt += prompt_content

        logger.debug("\n === System Prompt ===")
        logger.debug(persona_prompt)

        return persona_prompt

    async def handle_config_switch(
        self,
        websocket: WebSocket,
        config_file_name: str,
    ) -> None:
        """Handle configuration switch request."""
        try:
            new_character_config_data = None

            if config_file_name == "conf.yaml":
                new_character_config_data = read_yaml("conf.yaml").get(
                    "character_config"
                )
            else:
                characters_dir = self.system_config.config_alts_dir
                file_path = os.path.normpath(
                    os.path.join(characters_dir, config_file_name)
                )
                if not file_path.startswith(characters_dir):
                    raise ValueError("Invalid configuration file path")

                alt_config_data = read_yaml(file_path).get("character_config")
                new_character_config_data = deep_merge(
                    self.config.character_config.model_dump(), alt_config_data
                )

            if new_character_config_data:
                new_config = {
                    "system_config": self.system_config.model_dump(),
                    "character_config": new_character_config_data,
                }
                new_config = validate_config(new_config)
                await self.load_from_config(new_config)

                logger.debug(f"New config: {self}")
                logger.debug(
                    f"New character config: {self.character_config.model_dump()}"
                )

                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "set-model-and-conf",
                            "model_info": self.live2d_model.model_info,
                            "conf_name": self.character_config.conf_name,
                            "conf_uid": self.character_config.conf_uid,
                        }
                    )
                )

                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "config-switched",
                            "message": f"Switched to config: {config_file_name}",
                        }
                    )
                )

                logger.info(f"Configuration switched to {config_file_name}")
            else:
                raise ValueError(
                    f"Failed to load configuration from {config_file_name}"
                )

        except Exception as e:
            logger.error(f"Error switching configuration: {e}")
            logger.debug(self)
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "message": f"Error switching configuration: {str(e)}",
                    }
                )
            )
            raise e
