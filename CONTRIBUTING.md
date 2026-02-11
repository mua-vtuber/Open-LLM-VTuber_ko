# 기여 가이드

Open-LLM-VTuber 프로젝트에 기여해 주셔서 감사합니다! 이 문서는 프로젝트에 기여하는 방법을 안내합니다.

## 목차

1. [개발 환경 설정](#1-개발-환경-설정)
2. [코드 스타일](#2-코드-스타일)
3. [PR 프로세스](#3-pr-프로세스)
4. [커밋 메시지 규칙](#4-커밋-메시지-규칙)
5. [질문 및 토론](#5-질문-및-토론)

---

## 1. 개발 환경 설정

### 1.1. 필수 요구사항

- Python 3.10 ~ 3.12
- Node.js 18+ (프론트엔드 개발 시)
- Git

### 1.2. uv 패키지 매니저 설치

Open-LLM-VTuber는 [uv](https://github.com/astral-sh/uv)를 사용합니다.

**macOS / Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**
```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

### 1.3. 프로젝트 클론 및 의존성 설치

```bash
# 저장소 클론 (서브모듈 포함)
git clone --recursive https://github.com/Open-LLM-VTuber/Open-LLM-VTuber.git
cd Open-LLM-VTuber

# 의존성 설치
uv sync

# 개발 도구 포함 설치
uv sync --extra dev
```

### 1.4. pre-commit 훅 설치

코드 품질을 유지하기 위해 pre-commit 훅을 설치합니다.

```bash
uv run pre-commit install
```

이제 커밋할 때마다 자동으로 린팅과 포맷팅이 실행됩니다.

### 1.5. 서버 실행

```bash
# 기본 실행
uv run run_server.py

# 상세 로그 출력
uv run run_server.py --verbose

# 포트 변경
uv run run_server.py --port 8080
```

### 1.6. 테스트 실행

```bash
# 전체 테스트
uv run pytest

# 커버리지 포함
uv run pytest --cov=src/open_llm_vtuber

# 특정 테스트만
uv run pytest tests/test_specific.py
```

---

## 2. 코드 스타일

### 2.1. Python

프로젝트는 [Ruff](https://github.com/astral-sh/ruff)를 사용합니다.

```bash
# 린트 검사
ruff check .

# 자동 수정
ruff check --fix .

# 포맷팅
ruff format .
```

**주요 규칙:**
- Python 3.10 타겟
- 줄 길이: 88자 (Black 호환)
- import 정렬: isort 호환
- 타입 힌트 권장

**예시:**
```python
from typing import Optional, List
from loguru import logger


class MyClass:
    """클래스 설명."""

    def __init__(self, name: str, count: int = 0):
        """
        초기화 메서드.

        Args:
            name: 이름
            count: 카운트 (기본값: 0)
        """
        self.name = name
        self.count = count

    def process(self, items: List[str]) -> Optional[str]:
        """
        아이템 처리.

        Args:
            items: 처리할 아이템 목록

        Returns:
            처리 결과 또는 None
        """
        if not items:
            return None
        return items[0]
```

### 2.2. TypeScript (프론트엔드)

프론트엔드는 ESLint와 Prettier를 사용합니다.

```bash
cd frontend

# 린트 검사
npm run lint

# 포맷팅
npm run format
```

**주요 규칙:**
- TypeScript strict 모드
- React Hooks 규칙
- import 순서: 외부 → 내부 → 상대 경로

### 2.3. YAML 설정 파일

- 들여쓰기: 스페이스 2칸
- 주석으로 각 섹션 설명
- 민감한 정보는 `.env` 또는 환경 변수 사용

---

## 3. PR 프로세스

### 3.1. 브랜치 전략

```
main
  └── feature/feature-name     # 새 기능
  └── fix/bug-description      # 버그 수정
  └── docs/doc-update          # 문서 업데이트
  └── refactor/refactor-area   # 리팩토링
```

### 3.2. 브랜치 생성

```bash
# 최신 main에서 시작
git checkout main
git pull origin main

# feature 브랜치 생성
git checkout -b feature/my-new-feature
```

### 3.3. 변경 사항 커밋

```bash
# 변경 사항 확인
git status

# 파일 추가
git add src/open_llm_vtuber/my_file.py

# 커밋 (Conventional Commits 형식)
git commit -m "feat: add new TTS provider"
```

### 3.4. PR 생성

```bash
# 원격 브랜치로 푸시
git push origin feature/my-new-feature
```

GitHub에서 PR을 생성할 때:

1. **제목**: 변경 사항을 요약 (Conventional Commits 형식 권장)
2. **설명**: 변경 내용, 이유, 테스트 방법 설명
3. **체크리스트**: 테스트 통과, 문서 업데이트 확인

### 3.5. PR 체크리스트

- [ ] 코드 린팅 통과 (`ruff check .`)
- [ ] 테스트 통과 (`uv run pytest`)
- [ ] 새 기능에 테스트 추가
- [ ] 필요시 문서 업데이트
- [ ] 변경 사항 스크린샷 (UI 변경 시)

---

## 4. 커밋 메시지 규칙

[Conventional Commits](https://www.conventionalcommits.org/)를 따릅니다.

### 4.1. 형식

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

### 4.2. 타입

| 타입 | 설명 |
|-----|------|
| `feat` | 새로운 기능 |
| `fix` | 버그 수정 |
| `docs` | 문서 변경 |
| `style` | 코드 포맷팅 (기능 변경 없음) |
| `refactor` | 리팩토링 |
| `perf` | 성능 개선 |
| `test` | 테스트 추가/수정 |
| `chore` | 빌드, 도구 변경 |
| `ci` | CI/CD 변경 |

### 4.3. 예시

```bash
# 새 기능
git commit -m "feat(tts): add ElevenLabs TTS provider"

# 버그 수정
git commit -m "fix(websocket): handle disconnect gracefully"

# 문서
git commit -m "docs: update README with installation guide"

# 리팩토링
git commit -m "refactor(agent): extract common logic to base class"

# 브레이킹 체인지
git commit -m "feat(api)!: change WebSocket message format

BREAKING CHANGE: audio-response type renamed to audio"
```

### 4.4. 좋은 커밋 메시지 작성법

**좋은 예:**
```
feat(asr): add Groq Whisper ASR support

- Add GroqWhisperASR class implementing ASRInterface
- Register in ASR factory
- Add configuration options in config_manager
```

**나쁜 예:**
```
update code
fix bug
WIP
```

---

## 5. 질문 및 토론

### 5.1. 질문하기

- **GitHub Issues**: 버그 리포트, 기능 요청
- **GitHub Discussions**: 일반적인 질문, 아이디어 공유

### 5.2. 이슈 작성 가이드

**버그 리포트:**
- 재현 단계
- 예상 동작
- 실제 동작
- 환경 정보 (OS, Python 버전)
- 로그 출력

**기능 요청:**
- 해결하려는 문제
- 제안하는 해결책
- 대안

### 5.3. 코드 리뷰

PR이 머지되기 전 코드 리뷰가 필요합니다:

- 최소 1명의 승인 필요
- 모든 CI 검사 통과
- 충돌 해결

**리뷰어에게:**
- 건설적인 피드백 제공
- 구체적인 개선 제안
- 좋은 코드에 칭찬

**작성자에게:**
- 피드백에 열린 자세
- 변경 이유 설명
- 필요시 토론

---

## 추가 자료

- [프로젝트 아키텍처](./docs/ARCHITECTURE.md)
- [새 프로바이더 추가 가이드](./docs/EXTENDING.md)
- [WebSocket 프로토콜](./docs/WEBSOCKET_PROTOCOL.md)
- [공식 문서 사이트](https://open-llm-vtuber.github.io/)

---

기여해 주셔서 감사합니다!
