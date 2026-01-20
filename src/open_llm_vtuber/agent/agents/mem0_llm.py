from typing import AsyncIterator, List, Dict, Any, Optional
from loguru import logger

from .agent_interface import AgentInterface
from ..output_types import SentenceOutput
from ..transformers import (
    sentence_divider,
    actions_extractor,
    tts_filter,
    display_processor,
)
from ...config_manager import TTSPreprocessorConfig
from ..input_types import BatchInput, TextSource


class LLM(AgentInterface):
    """
    mem0 기반 장기 메모리를 지원하는 LLM Agent 클래스.
    벡터 데이터베이스를 활용하여 사용자와의 대화 기록 및 중요 정보를 장기간 보관.
    """

    def __init__(
        self,
        user_id: str,
        system: str,
        live2d_model,
        base_url: str,
        model: str,
        mem0_config: Dict[str, Any],
        tts_preprocessor_config: TTSPreprocessorConfig = None,
        faster_first_response: bool = True,
        segment_method: str = "pysbd",
    ):
        """
        mem0 Agent 초기화.

        Args:
            user_id: 사용자 고유 ID (mem0 메모리 격리용)
            system: 시스템 프롬프트
            live2d_model: Live2D 모델 인스턴스
            base_url: LLM API base URL
            model: LLM 모델 이름
            mem0_config: mem0 설정 (vector_store, llm, embedder 등)
            tts_preprocessor_config: TTS 전처리 설정
            faster_first_response: 첫 응답 속도 최적화 여부
            segment_method: 문장 분할 방법
        """
        super().__init__()
        self._user_id = user_id
        self._system = system
        self._live2d_model = live2d_model
        self._base_url = base_url
        self._model = model
        self._mem0_config = mem0_config
        self._tts_preprocessor_config = tts_preprocessor_config
        self._faster_first_response = faster_first_response
        self._segment_method = segment_method

        # mem0 Memory 인스턴스는 subtask-2-2에서 초기화 예정
        self._memory = None

        # 데코레이터 적용 (letta_agent.py 패턴 참고)
        self.chat = tts_filter(self._tts_preprocessor_config)(
            display_processor()(
                actions_extractor(self._live2d_model)(
                    sentence_divider(
                        faster_first_response=self._faster_first_response,
                        segment_method=self._segment_method,
                        valid_tags=["think"],
                    )(self._chat_impl)
                )
            )
        )

        logger.info(f"mem0 LLM Agent initialized for user: {self._user_id}")

    async def _chat_impl(self, input_data: BatchInput) -> AsyncIterator[str]:
        """
        실제 채팅 로직 구현 (내부 메서드).
        LLM API 호출 및 mem0 메모리 검색/저장은 subtask-2-2에서 구현 예정.

        Args:
            input_data: 사용자 입력 데이터

        Yields:
            str: LLM 응답 텍스트 스트림
        """
        # 기본 구조만 구현 (subtask-2-1)
        # 실제 mem0 통합은 subtask-2-2에서 구현
        user_message = self._to_text_prompt(input_data)
        logger.debug(f"User message: {user_message}")

        # Placeholder: 실제 LLM 호출은 subtask-2-2에서 구현
        yield "mem0 agent placeholder response"

    async def chat(self, input_data: BatchInput) -> AsyncIterator[SentenceOutput]:
        """
        사용자 입력을 받아 LLM 응답을 생성하고 mem0 메모리에 저장.

        이 메서드는 __init__에서 데코레이터로 래핑됨:
        - sentence_divider: 문장 단위로 분할
        - actions_extractor: Live2D 액션 추출
        - display_processor: 디스플레이 텍스트 처리
        - tts_filter: TTS 전처리 필터 적용

        Args:
            input_data: BatchInput - 사용자 입력 데이터

        Yields:
            SentenceOutput: 문장 단위 출력 (display_text, tts_text, actions)
        """
        # 이 메서드는 __init__에서 데코레이터가 적용된 버전으로 교체됨
        # 실제 구현은 _chat_impl에 있음
        pass

    def handle_interrupt(self, heard_response: str) -> None:
        """
        사용자의 중단(interrupt)을 처리.

        Args:
            heard_response: 중단 전까지 생성된 응답 텍스트
        """
        logger.info(f"Interrupt handled. Heard response: {heard_response[:50]}...")
        # 기본 구현 (필요시 subtask-2-2에서 확장)
        pass

    def set_memory_from_history(self, conf_uid: str, history_uid: str) -> None:
        """
        채팅 히스토리에서 메모리를 로드.

        Args:
            conf_uid: 설정 UID
            history_uid: 히스토리 UID
        """
        logger.info(
            f"Loading memory from history: conf={conf_uid}, history={history_uid}"
        )
        # mem0는 벡터 DB에서 자동으로 메모리 검색하므로
        # 별도의 히스토리 로딩이 필요 없을 수 있음
        # 필요시 subtask-2-2에서 구현
        pass

    def _to_text_prompt(self, input_data: BatchInput) -> str:
        """
        BatchInput을 텍스트 프롬프트로 변환.

        Args:
            input_data: BatchInput - 입력 데이터

        Returns:
            str: 변환된 프롬프트 문자열
        """
        message_parts = []

        # 텍스트 입력 처리 (letta_agent.py 패턴 참고)
        for text_data in input_data.texts:
            if text_data.source == TextSource.INPUT:
                message_parts.append(text_data.content)
            elif text_data.source == TextSource.CLIPBOARD:
                message_parts.append(f"[Clipboard content: {text_data.content}]")

        return "\n".join(message_parts)
