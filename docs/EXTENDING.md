# 새 프로바이더 추가 가이드

Open-LLM-VTuber는 모듈식 아키텍처를 채택하여 TTS, ASR, LLM 등 다양한 컴포넌트를 쉽게 확장할 수 있습니다. 이 문서는 새로운 프로바이더를 추가하는 방법을 설명합니다.

## 목차

1. [아키텍처 개요](#1-아키텍처-개요)
2. [TTS 프로바이더 추가](#2-tts-프로바이더-추가)
3. [ASR 프로바이더 추가](#3-asr-프로바이더-추가)
4. [LLM 프로바이더 추가](#4-llm-프로바이더-추가)
5. [에이전트 추가](#5-에이전트-추가)
6. [테스트 방법](#6-테스트-방법)

---

## 1. 아키텍처 개요

### 팩토리 패턴

Open-LLM-VTuber는 **Factory Pattern**을 사용하여 다양한 엔진을 생성합니다. 이 패턴은 Open-Closed Principle을 따릅니다:

- **확장에 열려 있음**: 새 엔진을 팩토리에 등록하면 됩니다
- **수정에 닫혀 있음**: 기존 팩토리 코드를 변경할 필요 없습니다

### 디렉터리 구조

```
src/open_llm_vtuber/
├── tts/                      # TTS 엔진
│   ├── tts_interface.py      # 추상 인터페이스
│   ├── tts_factory.py        # 팩토리 클래스
│   └── [provider]_tts.py     # 개별 TTS 구현
├── asr/                      # ASR 엔진
│   ├── asr_interface.py      # 추상 인터페이스
│   ├── asr_factory.py        # 팩토리 클래스
│   └── [provider]_asr.py     # 개별 ASR 구현
├── agent/                    # 대화 에이전트
│   ├── agents/
│   │   ├── agent_interface.py    # 추상 인터페이스
│   │   └── [agent_name].py       # 개별 에이전트 구현
│   ├── stateless_llm/
│   │   ├── stateless_llm_interface.py  # LLM 인터페이스
│   │   └── [provider]_llm.py           # 개별 LLM 구현
│   ├── agent_factory.py      # 에이전트 팩토리
│   └── stateless_llm_factory.py  # LLM 팩토리
└── config_manager/           # 설정 스키마
    ├── tts.py                # TTS 설정 스키마
    ├── asr.py                # ASR 설정 스키마
    └── agent.py              # 에이전트 설정 스키마
```

---

## 2. TTS 프로바이더 추가

### 2.1. TTSInterface 구현

새 TTS 프로바이더는 `TTSInterface`를 상속해야 합니다.

**파일**: `src/open_llm_vtuber/tts/my_tts.py`

```python
from .tts_interface import TTSInterface


class TTSEngine(TTSInterface):
    """My Custom TTS Engine"""

    def __init__(
        self,
        api_key: str,
        voice: str = "default",
        cache_dir: str = "cache",
    ):
        """
        TTS 엔진 초기화

        Args:
            api_key: API 키
            voice: 음성 ID
            cache_dir: 캐시 디렉터리
        """
        super().__init__(cache_dir)
        self.api_key = api_key
        self.voice = voice

    def generate_audio(self, text: str, file_name_no_ext=None) -> str:
        """
        텍스트를 음성으로 변환

        Args:
            text: 변환할 텍스트
            file_name_no_ext: 파일명 (확장자 제외)

        Returns:
            str: 생성된 오디오 파일 경로
        """
        # 캐시 파일 경로 생성
        output_path = self.generate_cache_file_name(
            file_name_no_ext,
            file_extension="wav"
        )

        # TODO: 실제 TTS API 호출 구현
        # 예: response = my_tts_api.synthesize(text, self.voice)
        # response.save(output_path)

        return output_path

    async def async_generate_audio(self, text: str, file_name_no_ext=None) -> str:
        """
        비동기 음성 생성 (선택적 오버라이드)

        기본 구현은 generate_audio()를 스레드에서 실행합니다.
        진정한 비동기 API가 있다면 이 메서드를 오버라이드하세요.
        """
        # 비동기 API가 있다면 직접 구현
        # 없다면 부모 클래스의 기본 구현 사용
        return await super().async_generate_audio(text, file_name_no_ext)
```

### 2.2. TTS Factory에 등록

**파일**: `src/open_llm_vtuber/tts/tts_factory.py`

```python
# 1. 팩토리 함수 추가
def _create_my_tts(**kwargs) -> TTSInterface:
    from .my_tts import TTSEngine

    return TTSEngine(
        api_key=kwargs.get("api_key"),
        voice=kwargs.get("voice"),
    )


# 2. TTS_FACTORIES 딕셔너리에 등록
TTS_FACTORIES: dict[str, Callable[..., TTSInterface]] = {
    # ... 기존 엔진들 ...
    "my_tts": _create_my_tts,  # 새 엔진 추가
}
```

### 2.3. 설정 스키마 추가

**파일**: `src/open_llm_vtuber/config_manager/tts.py`

```python
from pydantic import BaseModel


class MyTTSConfig(BaseModel):
    """My TTS 설정"""
    api_key: str
    voice: str = "default"


class TTSConfig(BaseModel):
    """TTS 통합 설정"""
    tts_engine: str = "edge_tts"  # 기본값
    # ... 기존 설정들 ...
    my_tts: MyTTSConfig | None = None  # 새 설정 추가
```

### 2.4. 기본 설정 파일 업데이트

**파일**: `config_templates/conf.default.yaml`

```yaml
tts_config:
  tts_engine: "my_tts"  # 사용할 엔진 선택
  my_tts:
    api_key: "your-api-key"
    voice: "default"
```

---

## 3. ASR 프로바이더 추가

### 3.1. ASRInterface 구현

**파일**: `src/open_llm_vtuber/asr/my_asr.py`

```python
import numpy as np
from .asr_interface import ASRInterface


class VoiceRecognition(ASRInterface):
    """My Custom ASR Engine"""

    # 오디오 상수 (ASRInterface에서 상속)
    # SAMPLE_RATE = 16000
    # NUM_CHANNELS = 1
    # SAMPLE_WIDTH = 2

    def __init__(
        self,
        api_key: str,
        language: str = "en-US",
    ):
        """
        ASR 엔진 초기화

        Args:
            api_key: API 키
            language: 인식 언어
        """
        self.api_key = api_key
        self.language = language

    def transcribe_np(self, audio: np.ndarray) -> str:
        """
        NumPy 배열 오디오를 텍스트로 변환

        Args:
            audio: 오디오 데이터 (float32, -1.0 ~ 1.0)

        Returns:
            str: 인식된 텍스트
        """
        # TODO: 실제 ASR API 호출 구현
        # 오디오는 16kHz, 모노, float32 형식입니다

        # 예: response = my_asr_api.transcribe(audio)
        # return response.text

        return "transcribed text"

    async def async_transcribe_np(self, audio: np.ndarray) -> str:
        """
        비동기 음성 인식 (선택적 오버라이드)

        기본 구현은 transcribe_np()를 스레드에서 실행합니다.
        """
        return await super().async_transcribe_np(audio)
```

### 3.2. ASR Factory에 등록

**파일**: `src/open_llm_vtuber/asr/asr_factory.py`

```python
class ASRFactory:
    @staticmethod
    def get_asr_system(system_name: str, **kwargs) -> Type[ASRInterface]:
        # ... 기존 코드 ...

        elif system_name == "my_asr":
            from .my_asr import VoiceRecognition as MyASR

            return MyASR(
                api_key=kwargs.get("api_key"),
                language=kwargs.get("language"),
            )

        else:
            raise ValueError(f"Unknown ASR system: {system_name}")
```

---

## 4. LLM 프로바이더 추가

### 4.1. StatelessLLMInterface 구현

**파일**: `src/open_llm_vtuber/agent/stateless_llm/my_llm.py`

```python
from typing import AsyncIterator, List, Dict, Any
from .stateless_llm_interface import StatelessLLMInterface


class AsyncLLM(StatelessLLMInterface):
    """My Custom LLM"""

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str | None = None,
        temperature: float = 0.7,
    ):
        """
        LLM 초기화

        Args:
            model: 모델 ID
            api_key: API 키
            base_url: API 베이스 URL
            temperature: 생성 온도
        """
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.temperature = temperature

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        system: str = None,
        tools: List[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        """
        채팅 완성 생성 (스트리밍)

        Args:
            messages: 대화 메시지 목록
                [{"role": "user", "content": "Hello"}]
            system: 시스템 프롬프트
            tools: 도구 정의 목록 (선택적)

        Yields:
            str: 생성된 텍스트 청크
        """
        # TODO: 실제 LLM API 호출 구현

        # 예시: OpenAI 호환 API 사용
        # async for chunk in self.client.chat.completions.create(
        #     model=self.model,
        #     messages=messages,
        #     stream=True,
        # ):
        #     if chunk.choices[0].delta.content:
        #         yield chunk.choices[0].delta.content

        yield "Hello, I am an AI assistant!"
```

### 4.2. LLM Factory에 등록

**파일**: `src/open_llm_vtuber/agent/stateless_llm_factory.py`

```python
class LLMFactory:
    @staticmethod
    def create_llm(llm_provider, **kwargs) -> Type[StatelessLLMInterface]:
        # ... 기존 코드 ...

        elif llm_provider == "my_llm":
            from .stateless_llm.my_llm import AsyncLLM as MyLLM

            return MyLLM(
                model=kwargs.get("model"),
                api_key=kwargs.get("llm_api_key"),
                base_url=kwargs.get("base_url"),
                temperature=kwargs.get("temperature"),
            )

        else:
            raise ValueError(f"Unsupported LLM provider: {llm_provider}")
```

---

## 5. 에이전트 추가

에이전트는 LLM 위에 메모리, 도구, 컨텍스트 관리 등의 기능을 추가합니다.

### 5.1. AgentInterface 구현

**파일**: `src/open_llm_vtuber/agent/agents/my_agent.py`

```python
from typing import AsyncIterator
from loguru import logger

from .agent_interface import AgentInterface
from ..output_types import SentenceOutput
from ..input_types import BatchInput


class MyAgent(AgentInterface):
    """My Custom Agent"""

    def __init__(
        self,
        llm,
        system_prompt: str,
        live2d_model=None,
    ):
        """
        에이전트 초기화

        Args:
            llm: StatelessLLMInterface 인스턴스
            system_prompt: 시스템 프롬프트
            live2d_model: Live2D 모델 (표정 추출용)
        """
        self.llm = llm
        self.system_prompt = system_prompt
        self.live2d_model = live2d_model
        self.messages = []  # 대화 히스토리

    async def chat(self, input_data: BatchInput) -> AsyncIterator[SentenceOutput]:
        """
        대화 처리

        Args:
            input_data: 사용자 입력

        Yields:
            SentenceOutput: 응답 청크
        """
        # 사용자 메시지 추가
        self.messages.append({
            "role": "user",
            "content": input_data.text
        })

        # LLM 호출
        full_response = ""
        async for chunk in self.llm.chat_completion(
            messages=self.messages,
            system=self.system_prompt,
        ):
            full_response += chunk

            # 문장 단위로 출력
            yield SentenceOutput(
                sentence=chunk,
                display_text=chunk,
                actions=None,
            )

        # 어시스턴트 응답 저장
        self.messages.append({
            "role": "assistant",
            "content": full_response
        })

    def handle_interrupt(self, heard_response: str) -> None:
        """
        인터럽트 처리

        Args:
            heard_response: 인터럽트 전 들은 응답
        """
        logger.info(f"Interrupt: heard '{heard_response}'")
        # 필요시 메시지 수정

    def set_memory_from_history(self, conf_uid: str, history_uid: str) -> None:
        """
        히스토리에서 메모리 로드

        Args:
            conf_uid: 설정 ID
            history_uid: 히스토리 ID
        """
        from ...chat_history_manager import get_history

        self.messages = get_history(conf_uid, history_uid)
```

### 5.2. Agent Factory에 등록

**파일**: `src/open_llm_vtuber/agent/agent_factory.py`

```python
class AgentFactory:
    @staticmethod
    def create_agent(
        conversation_agent_choice: str,
        agent_settings: dict,
        llm_configs: dict,
        system_prompt: str,
        live2d_model=None,
        **kwargs,
    ) -> Type[AgentInterface]:
        # ... 기존 코드 ...

        elif conversation_agent_choice == "my_agent":
            from .agents.my_agent import MyAgent

            settings = agent_settings.get("my_agent", {})
            llm_provider = settings.get("llm_provider")
            llm_config = llm_configs.get(llm_provider, {})

            llm = StatelessLLMFactory.create_llm(
                llm_provider=llm_provider,
                system_prompt=system_prompt,
                **llm_config
            )

            return MyAgent(
                llm=llm,
                system_prompt=system_prompt,
                live2d_model=live2d_model,
            )

        else:
            raise ValueError(f"Unsupported agent type: {conversation_agent_choice}")
```

---

## 6. 테스트 방법

### 6.1. 단위 테스트

**파일**: `tests/test_my_tts.py`

```python
import pytest
from src.open_llm_vtuber.tts.my_tts import TTSEngine


class TestMyTTS:
    def test_generate_audio(self):
        """오디오 생성 테스트"""
        tts = TTSEngine(api_key="test-key")
        result = tts.generate_audio("Hello, world!")

        assert result.endswith(".wav")

    @pytest.mark.asyncio
    async def test_async_generate_audio(self):
        """비동기 오디오 생성 테스트"""
        tts = TTSEngine(api_key="test-key")
        result = await tts.async_generate_audio("Hello!")

        assert result.endswith(".wav")
```

### 6.2. 통합 테스트

```bash
# 서버 실행
uv run run_server.py --verbose

# 웹 인터페이스에서 테스트
# http://localhost:12393
```

### 6.3. 팩토리 테스트

```python
# TTS 팩토리 테스트
from src.open_llm_vtuber.tts.tts_factory import TTSFactory

# 사용 가능한 엔진 목록 확인
print(TTSFactory.list_available_engines())

# 새 엔진 생성 테스트
tts = TTSFactory.get_tts_engine("my_tts", api_key="test")
```

---

## 참고 자료

- **TTS Interface**: `src/open_llm_vtuber/tts/tts_interface.py`
- **ASR Interface**: `src/open_llm_vtuber/asr/asr_interface.py`
- **Agent Interface**: `src/open_llm_vtuber/agent/agents/agent_interface.py`
- **LLM Interface**: `src/open_llm_vtuber/agent/stateless_llm/stateless_llm_interface.py`

### 기존 구현 예시

- **Edge TTS**: `src/open_llm_vtuber/tts/edge_tts.py` (간단한 예시)
- **OpenAI TTS**: `src/open_llm_vtuber/tts/openai_tts.py` (API 기반 예시)
- **Faster Whisper ASR**: `src/open_llm_vtuber/asr/faster_whisper_asr.py`
- **Claude LLM**: `src/open_llm_vtuber/agent/stateless_llm/claude_llm.py`
- **Basic Memory Agent**: `src/open_llm_vtuber/agent/agents/basic_memory_agent.py`
