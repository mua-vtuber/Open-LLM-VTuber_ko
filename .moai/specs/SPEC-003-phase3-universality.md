# SPEC-003: Phase 3 문서화 및 범용성 (Documentation & Universality)

## 메타데이터

| 항목 | 값 |
|------|-----|
| **SPEC ID** | SPEC-003 |
| **제목** | Phase 3: 문서화 및 범용성 - 외부 기여자 경험 개선 |
| **상태** | Complete |
| **우선순위** | Medium-High |
| **예상 범위** | 문서 + 설정 |
| **선행 조건** | SPEC-001 완료 (SPEC-002는 병렬 가능) |
| **작성일** | 2026-01-25 |
| **관련 문서** | `docs/CODE_REVIEW_2026-01-25.md` |

---

## 1. 배경 및 목적

### 1.1 현재 상태

| 이슈 | 심각도 | 현황 |
|------|--------|------|
| OpenAPI 문서 없음 | 높음 | FastAPI 내장 기능 미활용 |
| 확장 가이드 없음 | 높음 | TTS/ASR/LLM 추가 방법 미문서화 |
| WebSocket 프로토콜 미문서화 | 높음 | 메시지 형식 정의 없음 |
| CONTRIBUTING.md 스텁 | 중간 | 외부 링크만 있음 |

### 1.2 목적

1. **API 사용성 향상**: OpenAPI/Swagger로 REST API 문서화
2. **기여 용이성**: 확장 가이드와 기여 가이드라인 제공
3. **통합 용이성**: WebSocket 프로토콜 명세서 제공

### 1.3 성공 기준

- [ ] `/docs` 엔드포인트에서 Swagger UI 접근 가능
- [ ] `docs/EXTENDING.md`로 새 프로바이더 추가 가능
- [ ] `docs/WEBSOCKET_PROTOCOL.md`로 클라이언트 개발 가능
- [ ] `CONTRIBUTING.md`가 실제 가이드라인 포함

---

## 2. 요구사항

### 2.1 OpenAPI 문서화

#### REQ-022: FastAPI OpenAPI 활성화
**THE SYSTEM SHALL** Swagger UI와 ReDoc을 활성화한다.

**변경:** `server.py`
```python
app = FastAPI(
    title="Open-LLM-VTuber API",
    description="AI VTuber 백엔드 서버 API",
    version="1.2.1",
    docs_url="/docs",      # Swagger UI
    redoc_url="/redoc",    # ReDoc
)
```

#### REQ-023: 라우트 문서화
**THE SYSTEM SHALL** 모든 라우트에 docstring과 response_model을 추가한다.

**예시:** `routes/model_routes.py`
```python
@router.get(
    "/models",
    response_model=list[ModelInfo],
    summary="사용 가능한 모델 목록",
    description="현재 설정된 LLM, TTS, ASR 모델 정보를 반환합니다.",
)
async def get_models() -> list[ModelInfo]:
    """
    Returns:
        list[ModelInfo]: 모델 목록
    """
```

#### REQ-024: Pydantic 스키마 정리
**THE SYSTEM SHALL** API 요청/응답 스키마를 정의한다.

**새 파일:** `schemas/api.py`
```python
from pydantic import BaseModel, Field

class ModelInfo(BaseModel):
    """모델 정보 스키마"""
    type: str = Field(..., description="모델 유형 (llm, tts, asr)")
    name: str = Field(..., description="모델 이름")
    provider: str = Field(..., description="제공자")

    class Config:
        json_schema_extra = {
            "example": {
                "type": "llm",
                "name": "claude-3-5-sonnet",
                "provider": "anthropic"
            }
        }
```

---

### 2.2 확장 가이드 (EXTENDING.md)

#### REQ-025: 확장 가이드 문서 작성
**THE SYSTEM SHALL** 새 프로바이더 추가 방법을 문서화한다.

**새 파일:** `docs/EXTENDING.md`

**목차:**
1. 아키텍처 개요
2. TTS 프로바이더 추가
3. ASR 프로바이더 추가
4. LLM 프로바이더 추가
5. 에이전트 추가
6. 테스트 방법

**예시 내용 (TTS):**
```markdown
## TTS 프로바이더 추가

### 1단계: 인터페이스 구현

`src/open_llm_vtuber/tts/my_tts.py`:
```python
from .tts_interface import TTSInterface

class MyTTS(TTSInterface):
    async def generate_audio(
        self,
        text: str,
        **kwargs
    ) -> AsyncIterator[bytes]:
        # 구현
        yield audio_chunk
```

### 2단계: 팩토리 등록

`src/open_llm_vtuber/tts/tts_factory.py`:
```python
from .my_tts import MyTTS

# ENGINE_MAP에 추가
"my_tts": MyTTS,
```

### 3단계: 설정 스키마 추가

`src/open_llm_vtuber/config_manager/tts.py`:
```python
class MyTTSConfig(BaseModel):
    api_key: str
    voice_id: str = "default"
```
```

---

### 2.3 WebSocket 프로토콜 문서

#### REQ-026: WebSocket 프로토콜 명세서
**THE SYSTEM SHALL** WebSocket 메시지 형식을 문서화한다.

**새 파일:** `docs/WEBSOCKET_PROTOCOL.md`

**내용:**
```markdown
# WebSocket 프로토콜

## 연결

- URL: `ws://localhost:12393/client-ws`
- 핸드셰이크: 표준 WebSocket

## 메시지 형식

모든 메시지는 JSON 형식:
```json
{
  "type": "message-type",
  "data": { ... }
}
```

## 클라이언트 → 서버

| 타입 | 설명 | 데이터 |
|------|------|--------|
| `text-input` | 텍스트 입력 | `{ "text": "안녕하세요" }` |
| `mic-audio-end` | 음성 입력 완료 | `{ "audio": "base64..." }` |
| `interrupt-signal` | 응답 중단 | `{}` |

## 서버 → 클라이언트

| 타입 | 설명 | 데이터 |
|------|------|--------|
| `text-response` | 텍스트 응답 | `{ "text": "...", "final": false }` |
| `audio-response` | 음성 응답 | `{ "audio": "base64..." }` |
| `expression` | 표정 변경 | `{ "expression": "happy" }` |
| `error` | 오류 | `{ "code": "...", "message": "..." }` |
```

---

### 2.4 기여 가이드라인

#### REQ-027: CONTRIBUTING.md 보강
**THE SYSTEM SHALL** 실제 기여 가이드라인을 포함한다.

**변경:** `CONTRIBUTING.md`

**내용:**
```markdown
# 기여 가이드

## 개발 환경 설정

1. 저장소 포크 및 클론
2. 의존성 설치: `pip install -e .[dev]`
3. pre-commit 훅 설치: `pre-commit install`

## 코드 스타일

- Python: Ruff (설정: pyproject.toml)
- TypeScript: ESLint + Prettier

## PR 프로세스

1. feature 브랜치 생성: `feature/my-feature`
2. 변경사항 커밋 (Conventional Commits)
3. 테스트 통과 확인: `pytest`
4. PR 생성

## 커밋 메시지 규칙

- `feat:` 새 기능
- `fix:` 버그 수정
- `docs:` 문서
- `refactor:` 리팩토링
- `test:` 테스트

## 질문 및 토론

- GitHub Discussions 사용
- Discord: [링크]
```

#### REQ-028: PR 템플릿 추가
**THE SYSTEM SHALL** PR 템플릿을 제공한다.

**새 파일:** `.github/PULL_REQUEST_TEMPLATE.md`
```markdown
## 변경 사항

<!-- 변경 내용을 간략히 설명해주세요 -->

## 관련 이슈

<!-- #123 형식으로 연결 -->

## 체크리스트

- [ ] 테스트 통과
- [ ] 문서 업데이트 (필요시)
- [ ] 변경 사항 스크린샷 (UI 변경시)
```

---

### 2.5 설정 스키마 검증

#### REQ-029: conf.yaml 스키마 검증
**THE SYSTEM SHALL** 시작 시 설정 파일을 검증하고 명확한 오류를 표시한다.

**변경:** `config_manager/main.py`
```python
from pydantic import ValidationError

def load_config(path: str) -> Config:
    try:
        raw = yaml.safe_load(open(path))
        return Config(**raw)
    except ValidationError as e:
        logger.error("설정 파일 오류:")
        for error in e.errors():
            field = ".".join(str(p) for p in error["loc"])
            logger.error(f"  {field}: {error['msg']}")
        raise ConfigurationError("설정 파일이 유효하지 않습니다")
```

#### REQ-030: conf.yaml.example 생성
**THE SYSTEM SHALL** 명확한 플레이스홀더가 있는 예제 파일을 제공한다.

**새 파일:** `conf.yaml.example`
```yaml
# Open-LLM-VTuber 설정 예제
# 이 파일을 conf.yaml로 복사하고 값을 수정하세요

system:
  host: "0.0.0.0"
  port: 12393

llm_configs:
  openai:
    api_key: "YOUR_OPENAI_API_KEY"  # 필수
    model: "gpt-4o"

  anthropic:
    api_key: "YOUR_ANTHROPIC_API_KEY"  # 선택

tts:
  provider: "edge_tts"  # 무료, API 키 불필요
  voice: "ko-KR-SunHiNeural"

asr:
  provider: "sherpa_onnx"  # 로컬, 무료
```

---

## 3. 구현 계획

### 3.1 작업 분해

| # | 작업 | 파일 | 예상 |
|---|------|------|------|
| 1 | FastAPI OpenAPI 활성화 | `server.py` | 15분 |
| 2 | 라우트 docstring 추가 | `routes/*.py` | 1시간 |
| 3 | API 스키마 정의 | `schemas/api.py` | 1시간 |
| 4 | EXTENDING.md 작성 | `docs/EXTENDING.md` | 2시간 |
| 5 | WEBSOCKET_PROTOCOL.md 작성 | `docs/WEBSOCKET_PROTOCOL.md` | 1시간 |
| 6 | CONTRIBUTING.md 보강 | `CONTRIBUTING.md` | 1시간 |
| 7 | PR 템플릿 추가 | `.github/PULL_REQUEST_TEMPLATE.md` | 15분 |
| 8 | 설정 검증 로직 | `config_manager/main.py` | 1시간 |
| 9 | conf.yaml.example 생성 | `conf.yaml.example` | 30분 |

---

## 4. 완료 체크리스트

- [x] `/docs`에서 Swagger UI 접근 가능
- [x] `/redoc`에서 ReDoc 접근 가능
- [x] 모든 API 엔드포인트가 문서화됨
- [x] `docs/EXTENDING.md`가 TTS/ASR/LLM 추가 방법 포함
- [x] `docs/WEBSOCKET_PROTOCOL.md`가 모든 메시지 타입 정의
- [x] `CONTRIBUTING.md`가 개발 환경 설정 포함
- [x] PR 템플릿이 존재함
- [x] 잘못된 `conf.yaml` 시 명확한 오류 메시지 표시
- [x] `conf.yaml.example`이 존재함

---

*이 SPEC은 SPEC-001 완료 후 진행되며, SPEC-002와 병렬 진행 가능합니다.*
