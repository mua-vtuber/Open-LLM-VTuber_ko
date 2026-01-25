# SPEC-001: Phase 1 기반 구축 (Foundation Setup)

## 메타데이터

| 항목 | 값 |
|------|-----|
| **SPEC ID** | SPEC-001 |
| **제목** | Phase 1: 기반 구축 - Docker, 테스트, 의존성 |
| **상태** | Draft |
| **우선순위** | Critical (배포 차단 이슈 해결) |
| **예상 범위** | 백엔드 중심, 일부 DevOps |
| **작성일** | 2026-01-25 |
| **관련 문서** | `docs/CODE_REVIEW_2026-01-25.md` |

---

## 1. 배경 및 목적

### 1.1 현재 상태

코드 리뷰 결과 다음과 같은 **치명적 이슈**가 발견됨:

| 이슈 | 심각도 | 현황 |
|------|--------|------|
| Dockerfile 깨짐 | 치명적 | `server.py` 참조하지만 진입점은 `run_server.py` |
| 테스트 인프라 부재 | 치명적 | `tests/` 디렉토리에 파일 1개만 존재 |
| 의존성 그룹 없음 | 높음 | 클라우드 API만 사용해도 torch/onnx 설치 필요 |

### 1.2 목적

1. **Docker 배포 정상화**: Dockerfile 수정으로 컨테이너 빌드 가능
2. **CI/CD 기반 마련**: pytest 설정 및 GitHub Actions 테스트 워크플로우
3. **설치 효율화**: 선택적 의존성 그룹으로 설치 시간 단축

### 1.3 성공 기준

- [ ] `docker build .` 성공
- [ ] `docker-compose up` 으로 전체 스택 실행 가능
- [ ] `pytest` 명령으로 테스트 실행 가능
- [ ] GitHub Actions에서 테스트 통과
- [ ] `pip install .[cloud-only]` 로 경량 설치 가능

---

## 2. 요구사항 (EARS 형식)

### 2.1 Dockerfile 수정

#### REQ-001: 진입점 수정
**WHEN** Docker 이미지가 빌드될 때,
**THE SYSTEM SHALL** `run_server.py`를 진입점으로 사용한다.

**현재:**
```dockerfile
CMD ["python", "server.py"]
```

**변경:**
```dockerfile
CMD ["python", "run_server.py"]
```

#### REQ-002: 패키지 관리자 현대화
**WHEN** 의존성이 설치될 때,
**THE SYSTEM SHALL** `uv` 또는 `pip`를 사용하고 `pyproject.toml`을 참조한다.

**현재:**
```dockerfile
RUN pip install -r requirements.txt
```

**변경:**
```dockerfile
RUN pip install -e .
# 또는
RUN pip install uv && uv pip install -e .
```

#### REQ-003: 멀티스테이지 빌드 (선택)
**IF** 이미지 크기 최적화가 필요하면,
**THE SYSTEM SHALL** 멀티스테이지 빌드를 사용한다.

---

### 2.2 Docker Compose 추가

#### REQ-004: docker-compose.yml 생성
**WHEN** 개발자가 전체 스택을 실행하려 할 때,
**THE SYSTEM SHALL** `docker-compose up`으로 백엔드와 필요한 서비스를 시작할 수 있다.

**서비스 구성:**
```yaml
services:
  backend:
    build: ./Open-LLM-VTuber
    ports:
      - "12393:12393"
    volumes:
      - ./conf.yaml:/app/conf.yaml
    environment:
      - CORS_ORIGINS=http://localhost:3000

  # 선택적 서비스
  ollama:
    image: ollama/ollama
    ports:
      - "11434:11434"
```

#### REQ-005: .env.docker 예제 파일
**WHEN** 새 개발자가 Docker를 설정할 때,
**THE SYSTEM SHALL** `.env.docker.example` 파일을 제공한다.

---

### 2.3 테스트 인프라 구축

#### REQ-006: pytest 설정
**WHEN** 테스트가 실행될 때,
**THE SYSTEM SHALL** 표준 pytest 설정을 사용한다.

**생성할 파일:**
- `pyproject.toml` (pytest 섹션 추가)
- `tests/conftest.py` (공통 fixtures)
- `tests/__init__.py`

**pytest 설정:**
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
addopts = "-v --tb=short"
```

#### REQ-007: 테스트 파일 정리
**WHEN** 테스트가 구조화될 때,
**THE SYSTEM SHALL** 루트의 테스트 파일을 `tests/` 디렉토리로 이동한다.

**이동 대상:**
- `test_i18n.py` → `tests/test_i18n.py`
- `test_backward_compat.py` → `tests/test_backward_compat.py`
- `test_languages_api.py` → `tests/test_languages_api.py`
- (기타 `test_*.py` 파일들)

#### REQ-008: conftest.py 기본 fixtures
**WHEN** 테스트가 외부 서비스 없이 실행될 때,
**THE SYSTEM SHALL** mock fixtures를 제공한다.

**기본 fixtures:**
```python
@pytest.fixture
def mock_llm():
    """Mock LLM 응답"""

@pytest.fixture
def mock_tts():
    """Mock TTS 오디오"""

@pytest.fixture
def mock_asr():
    """Mock ASR 텍스트"""
```

#### REQ-009: GitHub Actions 테스트 워크플로우
**WHEN** PR이 생성되거나 main에 push될 때,
**THE SYSTEM SHALL** 자동으로 테스트를 실행한다.

**워크플로우 파일:** `.github/workflows/test.yml`
```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -e .[dev]
      - run: pytest
```

---

### 2.4 의존성 그룹 분리

#### REQ-010: 선택적 의존성 그룹 정의
**WHEN** 사용자가 특정 기능만 필요할 때,
**THE SYSTEM SHALL** 선택적으로 의존성을 설치할 수 있게 한다.

**그룹 정의:**
```toml
[project.optional-dependencies]
# 개발 도구 (테스트, 린팅)
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=4.0.0",
    "pre-commit>=4.1.0",
    "ruff>=0.8.6",
]

# 클라우드 API만 사용 (로컬 모델 없음)
cloud-only = [
    "fastapi>=0.115.8",
    "uvicorn>=0.33.0",
    "openai>=1.57.4",
    "anthropic>=0.40.0",
    "edge-tts>=7.0.0",
    # torch, onnxruntime 제외
]

# GPU 가속 (CUDA)
gpu = [
    "torch>=2.2.2",
    "onnxruntime-gpu>=1.20.1",
]

# 로컬 모델 전체
local = [
    "torch>=2.2.2",
    "onnxruntime>=1.20.1",
    "sherpa-onnx>=1.10.39",
    "faster-whisper>=1.0.3",
]

# 전체 (기존 동작 유지)
all = [
    "open-llm-vtuber[dev,local]",
]
```

#### REQ-011: 기본 의존성 최소화
**WHEN** `pip install open-llm-vtuber`가 실행될 때,
**THE SYSTEM SHALL** 핵심 기능만 설치한다 (클라우드 API 수준).

**핵심 의존성 (메인):**
- fastapi, uvicorn, pydantic
- openai, anthropic, groq
- edge-tts (무료, 경량)
- loguru, pyyaml

**분리할 의존성:**
- torch, onnxruntime → `[local]` 또는 `[gpu]`
- scipy, sympy → `[local]`
- pre-commit, ruff → `[dev]`

#### REQ-012: 설치 가이드 문서
**WHEN** 새 사용자가 설치할 때,
**THE SYSTEM SHALL** 사용 사례별 설치 명령을 문서화한다.

**문서 예시:**
```markdown
## 설치

### 클라우드 API만 사용 (빠른 설치)
pip install open-llm-vtuber[cloud-only]

### 로컬 모델 사용 (GPU)
pip install open-llm-vtuber[local,gpu]

### 개발 환경
pip install -e .[dev]
```

---

## 3. 구현 계획

### 3.1 작업 분해

| # | 작업 | 파일 | 예상 |
|---|------|------|------|
| 1 | Dockerfile 진입점 수정 | `dockerfile` | 10분 |
| 2 | Dockerfile 패키지 설치 수정 | `dockerfile` | 15분 |
| 3 | docker-compose.yml 생성 | 신규 파일 | 30분 |
| 4 | pytest 설정 추가 | `pyproject.toml` | 10분 |
| 5 | conftest.py 생성 | `tests/conftest.py` | 30분 |
| 6 | 테스트 파일 이동 | `tests/` | 15분 |
| 7 | GitHub Actions 워크플로우 | `.github/workflows/test.yml` | 20분 |
| 8 | 의존성 그룹 분리 | `pyproject.toml` | 45분 |
| 9 | requirements.txt 동기화 | `requirements.txt` | 10분 |
| 10 | 설치 가이드 업데이트 | `README.md` 또는 별도 문서 | 20분 |

### 3.2 의존성 관계

```
REQ-001 (Dockerfile 진입점)
    └── REQ-002 (패키지 관리자)
        └── REQ-010 (의존성 그룹) ─┐
                                   ├── REQ-003 (멀티스테이지)
REQ-004 (docker-compose)          │
    └── REQ-005 (.env.docker)     │
                                   │
REQ-006 (pytest 설정)             │
    ├── REQ-007 (파일 이동)        │
    ├── REQ-008 (fixtures)         │
    └── REQ-009 (GitHub Actions) ──┘
                                   │
REQ-011 (기본 의존성 최소화) ──────┘
    └── REQ-012 (설치 가이드)
```

---

## 4. 테스트 계획

### 4.1 Docker 테스트

| 테스트 | 명령 | 예상 결과 |
|--------|------|----------|
| 이미지 빌드 | `docker build -t ollv:test .` | 성공, 이미지 생성 |
| 컨테이너 실행 | `docker run -p 12393:12393 ollv:test` | 서버 시작 로그 |
| Compose 스택 | `docker-compose up` | 모든 서비스 healthy |

### 4.2 테스트 인프라

| 테스트 | 명령 | 예상 결과 |
|--------|------|----------|
| pytest 실행 | `pytest` | 테스트 발견 및 실행 |
| 커버리지 | `pytest --cov` | 커버리지 리포트 |
| CI 시뮬레이션 | `act -j test` (선택) | 워크플로우 통과 |

### 4.3 의존성 테스트

| 테스트 | 명령 | 예상 결과 |
|--------|------|----------|
| 클라우드 전용 설치 | `pip install .[cloud-only]` | torch 미설치 확인 |
| 전체 설치 | `pip install .[all]` | 모든 패키지 설치 |
| 가상환경 분리 | 별도 venv에서 테스트 | 충돌 없음 |

---

## 5. 리스크 및 완화

| 리스크 | 가능성 | 영향 | 완화 전략 |
|--------|--------|------|----------|
| 의존성 분리 시 import 오류 | 높음 | 높음 | 각 그룹별 import 테스트 추가 |
| 기존 사용자 설치 스크립트 깨짐 | 중간 | 중간 | `[all]` 그룹으로 기존 동작 유지 |
| Docker 빌드 시간 증가 | 낮음 | 낮음 | 멀티스테이지 빌드로 최적화 |

---

## 6. 완료 체크리스트

- [ ] Dockerfile이 정상 빌드됨
- [ ] docker-compose.yml이 전체 스택을 실행함
- [ ] `pytest`가 테스트를 발견하고 실행함
- [ ] GitHub Actions 워크플로우가 PR에서 실행됨
- [ ] `pip install .[cloud-only]`가 torch 없이 설치됨
- [ ] README에 설치 옵션이 문서화됨
- [ ] 기존 `pip install -e .`가 여전히 작동함

---

## 7. 다음 단계

Phase 1 완료 후:
1. **Phase 2: 아키텍처 개선** - WebSocketHandler 분리 (SPEC-002)
2. **Phase 3: 문서화 및 범용성** - OpenAPI, EXTENDING.md (SPEC-003)
3. **Phase 4: 안정성 및 테스트** - 에러 바운더리, 핵심 테스트 (SPEC-004)

---

*이 SPEC은 `docs/CODE_REVIEW_2026-01-25.md`의 Phase 1 로드맵을 기반으로 작성되었습니다.*
