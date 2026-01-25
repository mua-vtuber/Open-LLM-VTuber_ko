# SPEC-004: Phase 4 안정성 및 테스트 (Stability & Testing)

## 메타데이터

| 항목 | 값 |
|------|-----|
| **SPEC ID** | SPEC-004 |
| **제목** | Phase 4: 안정성 및 테스트 - 프로덕션 준비 |
| **상태** | Draft |
| **우선순위** | Medium |
| **예상 범위** | 프론트엔드 + 백엔드 |
| **선행 조건** | SPEC-001, SPEC-002 완료 |
| **작성일** | 2026-01-25 |
| **관련 문서** | `docs/CODE_REVIEW_2026-01-25.md` |

---

## 1. 배경 및 목적

### 1.1 현재 상태

| 이슈 | 심각도 | 현황 |
|------|--------|------|
| 에러 바운더리 없음 | 높음 | React 앱 크래시 시 전체 화면 하얀색 |
| 환경변수 미사용 | 높음 | URL/포트 하드코딩 |
| 예외 처리 일반적 | 중간 | `except Exception`만 사용 |
| 핵심 로직 테스트 부족 | 높음 | 단위 테스트 거의 없음 |

### 1.2 목적

1. **앱 안정성**: 에러 발생 시 graceful degradation
2. **배포 유연성**: 환경변수로 설정 가능
3. **변경 자신감**: 핵심 로직에 대한 테스트 커버리지

### 1.3 성공 기준

- [ ] 컴포넌트 오류 시 에러 UI 표시 (앱 전체 크래시 방지)
- [ ] 모든 하드코딩된 URL/포트가 환경변수로 대체
- [ ] 핵심 로직 테스트 커버리지 50% 이상
- [ ] 예외 처리가 타입별로 분리됨

---

## 2. 요구사항

### 2.1 에러 바운더리 (프론트엔드)

#### REQ-031: 전역 에러 바운더리
**THE SYSTEM SHALL** 앱 전체를 감싸는 에러 바운더리를 제공한다.

**새 파일:** `shared/components/ErrorBoundary.tsx`
```typescript
import { Component, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('Error caught by boundary:', error, errorInfo);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="flex flex-col items-center justify-center h-screen bg-gray-900 text-white">
          <h2 className="text-2xl font-bold text-red-400">오류가 발생했습니다</h2>
          <p className="mt-2 text-gray-400">{this.state.error?.message}</p>
          <button
            onClick={this.handleRetry}
            className="mt-4 px-4 py-2 bg-blue-500 rounded hover:bg-blue-600"
          >
            다시 시도
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
```

#### REQ-032: 기능별 에러 바운더리
**THE SYSTEM SHALL** 주요 기능별로 독립적인 에러 바운더리를 적용한다.

**적용 위치:**
- `<App>` 최상위
- `<CharacterCanvas>` (Live2D 렌더링)
- `<SettingsModal>` (설정 UI)
- `<ConversationPanel>` (대화 UI)

```tsx
// App.tsx
<ErrorBoundary>
  <ErrorBoundary fallback={<CharacterFallback />}>
    <CharacterCanvas />
  </ErrorBoundary>
  <ErrorBoundary fallback={<SettingsFallback />}>
    <SettingsModal />
  </ErrorBoundary>
</ErrorBoundary>
```

---

### 2.2 환경변수화 (프론트엔드)

#### REQ-033: 설정 객체 생성
**THE SYSTEM SHALL** 환경변수 기반 설정 객체를 제공한다.

**새 파일:** `shared/config.ts`
```typescript
const CONFIG = {
  // 서버 연결
  apiHost: import.meta.env.VITE_API_HOST || 'localhost',
  apiPort: import.meta.env.VITE_API_PORT || '12393',

  get apiUrl() {
    return `http://${this.apiHost}:${this.apiPort}`;
  },

  get wsUrl() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${this.apiHost}:${this.apiPort}/client-ws`;
  },

  // 기능 플래그
  enableDebug: import.meta.env.VITE_DEBUG === 'true',

  // 기본값
  defaultModelPath: '/live2d-models/mao_pro/mao_pro.model3.json',
} as const;

export default CONFIG;
```

#### REQ-034: .env.example 생성
**THE SYSTEM SHALL** 환경변수 예제 파일을 제공한다.

**새 파일:** `.env.example`
```bash
# Open-LLM-VTuber 프론트엔드 환경변수

# API 서버 주소
VITE_API_HOST=localhost
VITE_API_PORT=12393

# 디버그 모드
VITE_DEBUG=false
```

#### REQ-035: 하드코딩 제거
**THE SYSTEM SHALL** 모든 하드코딩된 URL/포트를 CONFIG로 대체한다.

**변경 대상:**
| 파일 | 하드코딩 | 변경 |
|------|----------|------|
| `store/index.ts:140` | `http://localhost:12393/...` | `CONFIG.apiUrl + '/...'` |
| `store/index.ts:306` | `ws://localhost:12393/client-ws` | `CONFIG.wsUrl` |
| `CharacterSettings.tsx:48` | `http://localhost:12393` | `CONFIG.apiUrl` |

---

### 2.3 환경변수화 (백엔드)

#### REQ-036: 환경변수 지원
**THE SYSTEM SHALL** 주요 설정을 환경변수로 오버라이드할 수 있게 한다.

**변경:** `config_manager/env_config.py`
```python
import os

class EnvConfig:
    """환경변수 기반 설정 오버라이드"""

    @staticmethod
    def get(key: str, default: str | None = None) -> str | None:
        return os.getenv(f"OLLV_{key}", default)

    # 서버 설정
    HOST = get("HOST", "0.0.0.0")
    PORT = int(get("PORT", "12393"))

    # CORS
    CORS_ORIGINS = get("CORS_ORIGINS", "*").split(",")

    # 로그 레벨
    LOG_LEVEL = get("LOG_LEVEL", "INFO")
```

#### REQ-037: .env 파일 로드
**THE SYSTEM SHALL** `.env` 파일이 있으면 자동으로 로드한다.

**변경:** `run_server.py`
```python
from dotenv import load_dotenv

# .env 파일 로드 (존재 시)
load_dotenv()
```

---

### 2.4 예외 처리 정교화 (백엔드)

#### REQ-038: 커스텀 예외 클래스
**THE SYSTEM SHALL** 도메인별 예외 클래스를 정의한다.

**새 파일:** `exceptions.py`
```python
class OpenLLMVTuberError(Exception):
    """기본 예외 클래스"""
    code: str = "INTERNAL_ERROR"

class ConfigurationError(OpenLLMVTuberError):
    """설정 오류"""
    code = "CONFIG_ERROR"

class ProviderError(OpenLLMVTuberError):
    """프로바이더 오류 (LLM, TTS, ASR)"""
    code = "PROVIDER_ERROR"

class ConnectionError(OpenLLMVTuberError):
    """연결 오류"""
    code = "CONNECTION_ERROR"

class TimeoutError(OpenLLMVTuberError):
    """타임아웃"""
    code = "TIMEOUT"
```

#### REQ-039: 예외 핸들러 미들웨어
**THE SYSTEM SHALL** FastAPI 예외 핸들러를 등록한다.

**변경:** `server.py`
```python
from fastapi import Request
from fastapi.responses import JSONResponse
from .exceptions import OpenLLMVTuberError

@app.exception_handler(OpenLLMVTuberError)
async def handle_app_error(request: Request, exc: OpenLLMVTuberError):
    return JSONResponse(
        status_code=400,
        content={
            "error": True,
            "code": exc.code,
            "message": str(exc),
        }
    )
```

---

### 2.5 핵심 로직 테스트

#### REQ-040: 팩토리 테스트
**THE SYSTEM SHALL** 팩토리 클래스에 대한 단위 테스트를 추가한다.

**새 파일:** `tests/test_factories.py`
```python
import pytest
from src.open_llm_vtuber.tts.tts_factory import TTSFactory
from src.open_llm_vtuber.asr.asr_factory import ASRFactory

class TestTTSFactory:
    def test_create_edge_tts(self):
        """Edge TTS 생성 테스트"""
        config = {"provider": "edge_tts", "voice": "ko-KR-SunHiNeural"}
        tts = TTSFactory.create(config)
        assert tts is not None

    def test_unknown_provider_raises(self):
        """알 수 없는 프로바이더 예외 테스트"""
        with pytest.raises(ValueError):
            TTSFactory.create({"provider": "unknown"})
```

#### REQ-041: 설정 검증 테스트
**THE SYSTEM SHALL** 설정 검증에 대한 테스트를 추가한다.

**새 파일:** `tests/test_config.py`
```python
import pytest
from pydantic import ValidationError
from src.open_llm_vtuber.config_manager.main import Config

class TestConfig:
    def test_valid_config(self, sample_config):
        """유효한 설정 테스트"""
        config = Config(**sample_config)
        assert config.system.port == 12393

    def test_missing_required_field(self):
        """필수 필드 누락 테스트"""
        with pytest.raises(ValidationError):
            Config(system={})
```

#### REQ-042: 메시지 라우터 테스트 (Phase 2 연계)
**THE SYSTEM SHALL** 메시지 라우터에 대한 테스트를 추가한다.

**새 파일:** `tests/test_message_router.py`
```python
import pytest
from src.open_llm_vtuber.websocket.message_router import MessageRouter

class TestMessageRouter:
    def test_route_text_input(self):
        """텍스트 입력 라우팅 테스트"""
        router = MessageRouter()
        handler_called = False

        @router.register("text-input")
        async def handle_text(data):
            nonlocal handler_called
            handler_called = True

        await router.route({"type": "text-input", "data": {}})
        assert handler_called
```

---

## 3. 구현 계획

### 3.1 작업 분해

| # | 작업 | 파일 | 예상 |
|---|------|------|------|
| 1 | ErrorBoundary 컴포넌트 생성 | `shared/components/ErrorBoundary.tsx` | 30분 |
| 2 | 기능별 에러 바운더리 적용 | `App.tsx` 외 | 45분 |
| 3 | CONFIG 객체 생성 | `shared/config.ts` | 20분 |
| 4 | .env.example 생성 | `.env.example` | 10분 |
| 5 | 하드코딩 제거 (프론트) | 다수 파일 | 1시간 |
| 6 | EnvConfig 클래스 생성 | `config_manager/env_config.py` | 30분 |
| 7 | 커스텀 예외 클래스 | `exceptions.py` | 30분 |
| 8 | 예외 핸들러 미들웨어 | `server.py` | 20분 |
| 9 | 팩토리 테스트 작성 | `tests/test_factories.py` | 1시간 |
| 10 | 설정 검증 테스트 | `tests/test_config.py` | 45분 |
| 11 | 메시지 라우터 테스트 | `tests/test_message_router.py` | 45분 |

---

## 4. 테스트 계획

### 4.1 에러 바운더리 테스트

| 시나리오 | 예상 동작 |
|----------|----------|
| Live2D 모델 로드 실패 | CharacterFallback UI 표시 |
| 설정 모달 오류 | SettingsFallback UI 표시 |
| 전역 오류 | 전체 에러 UI + 재시도 버튼 |

### 4.2 환경변수 테스트

| 시나리오 | 명령 |
|----------|------|
| 기본값 사용 | `npm run dev` (환경변수 없음) |
| 커스텀 서버 | `VITE_API_HOST=192.168.1.100 npm run dev` |
| 프로덕션 | `.env.production` 파일 사용 |

### 4.3 단위 테스트 커버리지

| 모듈 | 목표 커버리지 |
|------|--------------|
| 팩토리 클래스 | 80% |
| 설정 검증 | 90% |
| 메시지 라우터 | 70% |
| 예외 처리 | 80% |

---

## 5. 완료 체크리스트

- [ ] ErrorBoundary가 앱 전체를 감싸고 있음
- [ ] 기능별 에러 바운더리가 적용됨
- [ ] CONFIG 객체가 모든 하드코딩을 대체함
- [ ] `.env.example`이 존재함
- [ ] 백엔드가 환경변수를 지원함
- [ ] 커스텀 예외 클래스가 정의됨
- [ ] 예외 핸들러 미들웨어가 등록됨
- [ ] 팩토리 테스트 통과
- [ ] 설정 검증 테스트 통과
- [ ] 전체 테스트 커버리지 50% 이상

---

*이 SPEC은 SPEC-001, SPEC-002 완료 후 진행됩니다.*
