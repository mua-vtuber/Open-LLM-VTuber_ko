# Chat Monitor Implementation Summary

## Overview

유튜브/치지직 채팅 반응 기능이 Open-LLM-VTuber에 성공적으로 통합되었습니다. 이 기능을 통해 AI VTuber가 YouTube와 Chzzk (치지직) 라이브 채팅에 실시간으로 반응할 수 있습니다.

## 구현된 기능

### 1. 아키텍처 및 모듈 구조

```
src/open_llm_vtuber/chat_monitor/
├── __init__.py                      # 모듈 초기화
├── chat_monitor_interface.py       # 기본 인터페이스
├── youtube_chat_monitor.py         # YouTube 채팅 모니터
├── chzzk_chat_monitor.py          # 치지직 채팅 모니터
├── chat_monitor_manager.py        # 통합 관리자
└── README.md                       # 상세 문서
```

### 2. 주요 컴포넌트

#### ChatMonitorInterface
- 모든 플랫폼 모니터의 기본 인터페이스
- 표준화된 메시지 포맷 정의
- 재연결 로직 제공

#### YouTubeChatMonitor
- YouTube Data API v3 사용
- 폴링 방식 (2초마다 체크)
- API 키 인증
- 실시간 라이브 스트림 자동 감지

#### ChzzkChatMonitor
- chzzkpy v2 공식 라이브러리 사용
- WebSocket 기반 실시간 통신
- OAuth2 인증 방식 (client_id, client_secret)
- 토큰 자동 갱신 지원
- Python 3.11+ 필요

#### ChatMonitorManager
- 다중 플랫폼 모니터 조정
- 생명주기 관리 (초기화, 시작, 중지)
- 메시지 라우팅
- 상태 리포팅

### 3. 설정 시스템

#### 설정 클래스 추가 (config_manager/live.py)
```python
class YouTubeChatConfig      # YouTube 설정
class ChzzkChatConfig        # 치지직 설정
class ChatMonitorConfig      # 통합 설정
class LiveConfig             # 라이브 스트리밍 통합
```

#### conf.yaml 설정 추가
```yaml
live_config:
  chat_monitor:
    enabled: false
    youtube:
      enabled: false
      api_key: ""
      channel_id: ""
    chzzk:
      enabled: false
      channel_id: ""
      client_id: ""             # OAuth2 클라이언트 ID
      client_secret: ""         # OAuth2 클라이언트 시크릿
      redirect_uri: "http://localhost:12393/chzzk/callback"
      access_token: ""          # 자동 설정됨
      refresh_token: ""         # 자동 설정됨
    max_retries: 10
    retry_interval: 60
```

### 4. WebSocket 통합

#### 메시지 핸들러 추가 (websocket_handler.py)
- `start-chat-monitor`: 모니터링 시작
- `stop-chat-monitor`: 모니터링 중지
- `chat-monitor-status`: 상태 조회
- `chat-message`: 수신된 채팅 메시지 (클라이언트로 전송)

#### 자동 초기화
- 서버 시작 시 설정에 따라 자동으로 모니터링 시작
- 첫 번째 클라이언트 연결 시 채팅 메시지를 대화 시스템에 주입

### 5. 의존성 관리

#### pyproject.toml 업데이트
```toml
[project.optional-dependencies]
chat_monitor = [
    "chzzkpy>=2.0.0; python_version >= '3.11'",
]
```

설치 방법:
```bash
# Chzzk 지원 포함
uv sync --extra chat_monitor

# Chzzk 지원 제외 (YouTube만)
uv sync
```

## 사용 방법

### 1. 기본 설정

`conf.yaml` 파일을 편집하여 채팅 모니터링을 활성화:

```yaml
live_config:
  chat_monitor:
    enabled: true
    youtube:
      enabled: true
      api_key: "YOUR_YOUTUBE_API_KEY"
      channel_id: "YOUR_YOUTUBE_CHANNEL_ID"
```

### 2. 서버 실행

```bash
uv run run_server.py
```

### 3. 작동 방식

1. **채팅 메시지 수신**
   - YouTube: 2초마다 폴링
   - Chzzk: WebSocket 실시간 수신

2. **메시지 처리**
   - 표준 `ChatMessage` 포맷으로 변환
   - 모든 연결된 클라이언트에 브로드캐스트

3. **AI 응답 생성**
   - 메시지가 text-input으로 대화 시스템에 주입
   - LLM이 메시지 처리 및 응답 생성
   - TTS로 음성 합성
   - Live2D로 표현 출력

## 파일 변경 사항

### 새로 추가된 파일

```
src/open_llm_vtuber/chat_monitor/
├── __init__.py
├── chat_monitor_interface.py
├── youtube_chat_monitor.py
├── chzzk_chat_monitor.py
├── chzzk_oauth_manager.py      # NEW: OAuth 토큰 관리
├── chat_monitor_manager.py
└── README.md

CHAT_MONITOR_IMPLEMENTATION.md (이 파일)
```

### 수정된 파일

```
src/open_llm_vtuber/
├── config_manager/live.py           # 설정 클래스 추가 (OAuth 필드)
├── websocket_handler.py             # 채팅 모니터 통합
├── routes.py                        # OAuth 인증 엔드포인트 추가
conf.yaml                             # 채팅 모니터 설정 추가 (OAuth 필드)
pyproject.toml                        # 의존성 추가
```

## 테스트 가이드

### 1. YouTube 채팅 테스트

```yaml
# conf.yaml
live_config:
  chat_monitor:
    enabled: true
    youtube:
      enabled: true
      api_key: "YOUR_API_KEY"
      channel_id: "YOUR_CHANNEL_ID"
```

1. YouTube Studio에서 라이브 스트림 시작
2. Open-LLM-VTuber 서버 실행
3. 브라우저에서 클라이언트 접속
4. YouTube 채팅에 메시지 입력
5. AI가 채팅에 반응하는지 확인

### 2. 치지직 채팅 테스트

#### 첫 번째: OAuth 인증 설정

1. [CHZZK Developer Center](https://developers.chzzk.naver.com/application/)에서 OAuth 앱 생성
2. Redirect URI를 `http://localhost:12393/chzzk/callback`으로 설정
3. Client ID와 Client Secret 복사

```yaml
# conf.yaml
live_config:
  chat_monitor:
    enabled: true
    chzzk:
      enabled: true
      channel_id: "YOUR_CHANNEL_ID"
      client_id: "YOUR_CLIENT_ID"
      client_secret: "YOUR_CLIENT_SECRET"
      redirect_uri: "http://localhost:12393/chzzk/callback"
```

4. Open-LLM-VTuber 서버 실행 (Python 3.11+)
5. 브라우저에서 `http://localhost:12393/chzzk/auth` 접속
6. Chzzk 권한 승인 페이지에서 권한 승인
7. 자동으로 `/chzzk/callback`으로 리다이렉트되고 토큰 저장됨
8. 성공 메시지 확인 (토큰은 `cache/chzzk_tokens.json`에 저장됨)

#### 두 번째: 채팅 모니터링 테스트

1. 치지직에서 라이브 방송 시작
2. Open-LLM-VTuber 서버 재시작 (이미 실행 중이면)
3. 브라우저에서 클라이언트 접속
4. 치지직 채팅에 메시지 입력
5. AI가 채팅에 반응하는지 확인

**참고**: 토큰이 만료되면 `/chzzk/auth`를 다시 방문하여 재인증하면 됩니다.

### 3. WebSocket 메시지 테스트

브라우저 콘솔에서 테스트:

```javascript
// 상태 확인
ws.send(JSON.stringify({type: "chat-monitor-status"}));

// 모니터링 시작
ws.send(JSON.stringify({type: "start-chat-monitor"}));

// 모니터링 중지
ws.send(JSON.stringify({type: "stop-chat-monitor"}));
```

## 코드 품질

### 타입 안전성
- 모든 함수에 타입 힌트 적용
- Pydantic 모델을 사용한 설정 검증
- TypedDict를 사용한 메시지 포맷 정의

### 에러 처리
- 모든 네트워크 호출에 try-except 블록
- 자동 재연결 로직
- 상세한 에러 로깅

### 문서화
- 모든 클래스와 메서드에 docstring
- 상세한 README.md
- 인라인 코드 주석

### 코드 포맷팅
```bash
# Ruff로 자동 포맷팅 완료
uv run ruff format src/open_llm_vtuber/chat_monitor/
# Result: 3 files reformatted, 2 files left unchanged

# Ruff 린터 검사 통과
uv run ruff check src/open_llm_vtuber/chat_monitor/
# Result: All checks passed!
```

## 알려진 제한사항

### YouTube
- API 할당량 제한 (일일 10,000 단위)
- 폴링 방식이므로 2초 지연 발생
- 라이브 스트림이 활성화되어야 작동

### Chzzk
- Python 3.11+ 필요
- 공식 API 사용 (chzzkpy v2)
- OAuth2 인증 필요
- 토큰 자동 갱신 지원

### 일반
- 메시지 필터링 없음 (모든 채팅을 AI가 처리)
- 스팸 방지 기능 없음
- 단일 클라이언트만 AI 응답 수신

## 향후 개선 사항

### 단기 (1-2주)
- [ ] 메시지 필터링 (봇, 스팸 무시)
- [ ] Rate limiting (과도한 메시지 방지)
- [ ] 플랫폼별 커스텀 포맷팅

### 중기 (1-2개월)
- [ ] Super Chat / 후원 지원
- [ ] Twitch 플랫폼 추가
- [ ] Discord 통합
- [ ] 다중 클라이언트 지원

### 장기 (3개월+)
- [ ] AI 기반 메시지 우선순위 설정
- [ ] 커스텀 콜백 시스템
- [ ] 채팅 분석 대시보드
- [ ] 멀티 스트리밍 지원

## 기여 가이드라인

코드 기여 시 다음을 준수해주세요:

1. **코드 스타일**: `ruff format` 사용
2. **타입 힌트**: 모든 함수에 타입 힌트 추가
3. **Docstring**: 공개 메서드에 docstring 작성
4. **문서 업데이트**: 새 기능 추가 시 README 업데이트
5. **테스트**: 가능한 경우 YouTube와 Chzzk 모두 테스트

## 참고 자료

### YouTube Data API
- [API Console](https://console.cloud.google.com/)
- [Documentation](https://developers.google.com/youtube/v3/docs)
- [Live Chat API](https://developers.google.com/youtube/v3/live/docs/liveChatMessages)

### Chzzk
- [chzzkpy GitHub](https://github.com/Louelle/chzzkpy)
- [Chzzk Platform](https://chzzk.naver.com/)

### Open-LLM-VTuber
- [GitHub Repository](https://github.com/t41372/Open-LLM-VTuber)
- [Documentation](https://github.com/t41372/Open-LLM-VTuber/wiki)

## 라이선스

Open-LLM-VTuber 프로젝트의 일부로, 메인 LICENSE 파일의 조건을 따릅니다.

---

**구현 완료일**: 2026-01-20
**구현자**: Claude Code
**버전**: 1.0.0
