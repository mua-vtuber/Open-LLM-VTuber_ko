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

try:
    from mem0 import Memory
except ImportError:
    logger.warning("mem0ai 패키지가 설치되지 않았습니다. pip install mem0ai를 실행하세요.")
    Memory = None

try:
    from openai import AsyncOpenAI
except ImportError:
    logger.warning("openai 패키지가 설치되지 않았습니다. pip install openai를 실행하세요.")
    AsyncOpenAI = None


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

        # mem0 Memory 인스턴스 초기화
        if Memory is None:
            raise ImportError(
                "mem0ai 패키지가 설치되지 않았습니다. 'pip install mem0ai'를 실행하세요."
            )

        try:
            self._memory = Memory(config=mem0_config) if mem0_config else Memory()
            logger.info(f"mem0 Memory 인스턴스 초기화 완료 (user_id: {user_id})")
        except Exception as e:
            logger.error(f"mem0 Memory 초기화 실패: {e}")
            self._memory = None

        # OpenAI 호환 LLM 클라이언트 초기화
        if AsyncOpenAI is None:
            raise ImportError(
                "openai 패키지가 설치되지 않았습니다. 'pip install openai'를 실행하세요."
            )

        self._openai_client = AsyncOpenAI(base_url=base_url)
        logger.debug(f"OpenAI 클라이언트 초기화 완료 (base_url: {base_url}, model: {model})")

        # 데코레이터 적용 (letta_agent.py 패턴 참고)
        self.chat = tts_filter(self._tts_preprocessor_config)(
            display_processor()(
                actions_extractor(self._live2d_model)(
                    sentence_divider(
                        faster_first_response=self._faster_first_response,
                        segment_method=self._segment_method,
                        valid_tags=["think"],
                    )(self.chat)
                )
            )
        )

        logger.info(f"mem0 LLM Agent 초기화 완료 (user_id: {self._user_id})")

    async def chat(self, input_data: BatchInput) -> AsyncIterator[SentenceOutput]:
        """
        채팅 로직 구현 - LLM API 호출 및 mem0 메모리 검색/저장 통합.
        데코레이터를 통해 문장 분할, 표정 추출, TTS 필터링이 적용됩니다.

        Args:
            input_data: 사용자 입력 데이터

        Yields:
            str: LLM 응답 텍스트 스트림
        """
        # 1. 사용자 메시지 추출
        user_message = self._to_text_prompt(input_data)
        logger.debug(f"User message: {user_message}")

        if not user_message.strip():
            logger.warning("빈 사용자 메시지 수신")
            return

        # 2. mem0에서 관련 메모리 검색
        relevant_memories = []
        if self._memory:
            try:
                search_results = self._memory.search(
                    query=user_message,
                    user_id=self._user_id,
                )
                relevant_memories = search_results if search_results else []
                logger.debug(f"검색된 메모리 수: {len(relevant_memories)}")
            except Exception as e:
                logger.error(f"mem0 메모리 검색 실패: {e}")

        # 3. 시스템 프롬프트 구성 (메모리 포함)
        system_prompt = self._system
        if relevant_memories:
            memory_context = "\n\n=== 관련 기억 ===\n"
            for idx, mem in enumerate(relevant_memories, 1):
                # mem0 검색 결과는 딕셔너리 형태
                memory_text = mem.get("memory", "") if isinstance(mem, dict) else str(mem)
                memory_context += f"{idx}. {memory_text}\n"
            system_prompt = f"{self._system}\n{memory_context}"
            logger.debug(f"메모리 컨텍스트 추가됨: {len(relevant_memories)}개")

        # 4. LLM API 스트리밍 호출
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        assistant_response = []
        try:
            stream = await self._openai_client.chat.completions.create(
                model=self._model,
                messages=messages,
                stream=True,
            )

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    assistant_response.append(content)
                    yield content

        except Exception as e:
            logger.error(f"LLM API 호출 실패: {e}")
            error_message = f"오류가 발생했습니다: {str(e)}"
            assistant_response.append(error_message)
            yield error_message
            return

        # 5. 대화 내용을 mem0에 저장
        full_response = "".join(assistant_response)
        if self._memory and full_response.strip():
            try:
                # mem0에 메시지 형식으로 저장
                messages_to_save = [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": full_response},
                ]
                self._memory.add(
                    messages=messages_to_save,
                    user_id=self._user_id,
                )
                logger.debug(f"대화 내용을 mem0에 저장 완료")
            except Exception as e:
                logger.error(f"mem0 메모리 저장 실패: {e}")

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
