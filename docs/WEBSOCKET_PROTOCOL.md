# WebSocket 프로토콜 명세서

이 문서는 Open-LLM-VTuber의 WebSocket 통신 프로토콜을 정의합니다.

## 목차

1. [연결 정보](#1-연결-정보)
2. [메시지 형식](#2-메시지-형식)
3. [클라이언트 → 서버 메시지](#3-클라이언트--서버-메시지)
4. [서버 → 클라이언트 메시지](#4-서버--클라이언트-메시지)
5. [예시 시나리오](#5-예시-시나리오)

---

## 1. 연결 정보

### 엔드포인트

| 엔드포인트 | 설명 |
|-----------|------|
| `ws://localhost:12393/client-ws` | 메인 클라이언트 WebSocket |

### 연결 흐름

```
1. 클라이언트가 WebSocket 연결 요청
2. 서버가 연결 수락 및 client_uid 생성
3. 서버가 초기 메시지 전송:
   - "full-text": 연결 확인
   - "set-model-and-conf": 모델 및 설정 정보
   - "group-update": 그룹 상태
   - "control": 마이크 시작 신호
4. 양방향 메시지 교환 시작
```

### 연결 예시 (JavaScript)

```javascript
const ws = new WebSocket('ws://localhost:12393/client-ws');

ws.onopen = () => {
    console.log('Connected to server');
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Received:', data.type, data);
};

ws.onclose = () => {
    console.log('Disconnected');
};
```

---

## 2. 메시지 형식

모든 메시지는 JSON 형식입니다.

### 기본 구조

```json
{
    "type": "message-type",
    // 메시지 타입에 따른 추가 필드
}
```

### 메시지 타입 분류

| 카테고리 | 메시지 타입 |
|---------|------------|
| **대화** | `text-input`, `mic-audio-end`, `ai-speak-signal` |
| **오디오** | `mic-audio-data`, `raw-audio-data` |
| **제어** | `interrupt-signal`, `audio-play-start`, `heartbeat` |
| **히스토리** | `fetch-history-list`, `fetch-and-set-history`, `create-new-history`, `delete-history` |
| **설정** | `fetch-configs`, `switch-config`, `update-config`, `request-init-config` |
| **그룹** | `add-client-to-group`, `remove-client-from-group`, `request-group-info` |
| **메모리** | `get_memories`, `delete_memory`, `delete_all_memories` |
| **프로필** | `get-visitor-profile`, `update-visitor-profile`, `list-visitor-profiles`, `delete-visitor-profile` |

---

## 3. 클라이언트 → 서버 메시지

### 3.1. 대화 관련

#### `text-input` - 텍스트 입력

사용자가 텍스트로 메시지를 전송할 때 사용합니다.

```json
{
    "type": "text-input",
    "text": "안녕하세요!",
    "images": ["base64-encoded-image"]  // 선택적
}
```

| 필드 | 타입 | 필수 | 설명 |
|-----|------|-----|------|
| `type` | string | O | `"text-input"` |
| `text` | string | O | 사용자 입력 텍스트 |
| `images` | string[] | X | Base64 인코딩된 이미지 배열 |

#### `mic-audio-data` - 오디오 데이터

마이크에서 캡처한 오디오 청크를 전송합니다.

```json
{
    "type": "mic-audio-data",
    "audio": [0.1, -0.2, 0.05, ...]  // Float32 배열
}
```

| 필드 | 타입 | 필수 | 설명 |
|-----|------|-----|------|
| `type` | string | O | `"mic-audio-data"` |
| `audio` | number[] | O | Float32 오디오 샘플 (-1.0 ~ 1.0) |

#### `mic-audio-end` - 음성 입력 완료

음성 입력이 완료되었음을 알립니다. 서버는 버퍼링된 오디오를 처리합니다.

```json
{
    "type": "mic-audio-end"
}
```

#### `ai-speak-signal` - AI 발화 요청

AI가 먼저 말하도록 요청합니다 (인사말 등).

```json
{
    "type": "ai-speak-signal"
}
```

### 3.2. 제어 관련

#### `interrupt-signal` - 응답 중단

AI 응답을 중단합니다 (사용자가 말을 끊을 때).

```json
{
    "type": "interrupt-signal",
    "text": "지금까지 들은 응답"  // 선택적
}
```

| 필드 | 타입 | 필수 | 설명 |
|-----|------|-----|------|
| `type` | string | O | `"interrupt-signal"` |
| `text` | string | X | 인터럽트 전 들은 응답 텍스트 |

#### `audio-play-start` - 오디오 재생 시작

클라이언트가 오디오 재생을 시작했음을 알립니다.

```json
{
    "type": "audio-play-start",
    "display_text": {
        "text": "표시할 텍스트"
    }
}
```

#### `heartbeat` - 연결 유지

연결 상태를 확인합니다.

```json
{
    "type": "heartbeat"
}
```

**응답**:
```json
{
    "type": "heartbeat-ack"
}
```

### 3.3. 히스토리 관련

#### `fetch-history-list` - 히스토리 목록 조회

```json
{
    "type": "fetch-history-list"
}
```

#### `fetch-and-set-history` - 특정 히스토리 로드

```json
{
    "type": "fetch-and-set-history",
    "history_uid": "history-uuid-here"
}
```

#### `create-new-history` - 새 히스토리 생성

```json
{
    "type": "create-new-history"
}
```

#### `delete-history` - 히스토리 삭제

```json
{
    "type": "delete-history",
    "history_uid": "history-uuid-here"
}
```

### 3.4. 설정 관련

#### `fetch-configs` - 설정 목록 조회

```json
{
    "type": "fetch-configs"
}
```

#### `switch-config` - 설정 전환

```json
{
    "type": "switch-config",
    "file": "character-config.yaml"
}
```

#### `update-config` - 설정 업데이트

런타임에 설정을 부분적으로 업데이트합니다.

```json
{
    "type": "update-config",
    "config": {
        "tts_config": {
            "voice": "new-voice-id"
        }
    }
}
```

#### `request-init-config` - 초기 설정 요청

```json
{
    "type": "request-init-config"
}
```

### 3.5. 그룹 관련

#### `add-client-to-group` - 그룹에 클라이언트 추가

```json
{
    "type": "add-client-to-group",
    "invitee_uid": "client-uid-to-invite"
}
```

#### `remove-client-from-group` - 그룹에서 클라이언트 제거

```json
{
    "type": "remove-client-from-group",
    "target_uid": "client-uid-to-remove"
}
```

#### `request-group-info` - 그룹 정보 요청

```json
{
    "type": "request-group-info"
}
```

### 3.6. 메모리 관련

#### `get_memories` - 메모리 조회

```json
{
    "type": "get_memories"
}
```

#### `delete_memory` - 특정 메모리 삭제

```json
{
    "type": "delete_memory",
    "memory_id": "mem_xxx"
}
```

#### `delete_all_memories` - 모든 메모리 삭제

```json
{
    "type": "delete_all_memories"
}
```

### 3.7. 방문자 프로필 관련

#### `get-visitor-profile` - 프로필 조회

```json
{
    "type": "get-visitor-profile",
    "identifier": "user-id",  // 선택적, 기본값: client_uid
    "platform": "direct"       // 선택적, 기본값: "direct"
}
```

#### `update-visitor-profile` - 프로필 업데이트

```json
{
    "type": "update-visitor-profile",
    "action": "add_fact",      // add_fact, add_preference, update_affinity, record_message
    "value": "좋아하는 것",
    "category": "likes"        // add_preference 시 필요
}
```

---

## 4. 서버 → 클라이언트 메시지

### 4.1. 초기화 메시지

#### `full-text` - 전체 텍스트

```json
{
    "type": "full-text",
    "text": "Connection established"
}
```

#### `set-model-and-conf` - 모델 및 설정 정보

연결 시 전송되는 초기 설정 정보입니다.

```json
{
    "type": "set-model-and-conf",
    "model_info": {
        "name": "shizuku",
        "path": "live2d-models/shizuku/shizuku.model3.json",
        // Live2D 모델 정보
    },
    "conf_name": "Shizuku",
    "conf_uid": "config-uuid",
    "client_uid": "client-uuid"
}
```

### 4.2. 응답 메시지

#### `audio-response` - 오디오 응답

AI의 음성 응답입니다.

```json
{
    "type": "audio",
    "audio": "base64-encoded-audio-data",
    "audio_format": "wav",
    "sample_rate": 24000,
    "display_text": {
        "text": "AI가 말한 텍스트"
    },
    "actions": {
        "expression": "happy",
        "motion": "wave"
    },
    "volumes": [0.5, 0.6, 0.7, ...]  // 립싱크용 볼륨 데이터
}
```

| 필드 | 타입 | 설명 |
|-----|------|------|
| `audio` | string | Base64 인코딩된 오디오 |
| `audio_format` | string | 오디오 형식 (wav, mp3) |
| `sample_rate` | number | 샘플레이트 |
| `display_text` | object | 표시할 텍스트 |
| `actions` | object | Live2D 액션 (표정, 모션) |
| `volumes` | number[] | 립싱크 볼륨 데이터 |

#### `sentence` - 문장 단위 텍스트

스트리밍 응답의 문장 청크입니다.

```json
{
    "type": "sentence",
    "text": "문장 텍스트",
    "display_text": "표시용 텍스트",
    "actions": {
        "expression": "neutral"
    }
}
```

### 4.3. 제어 메시지

#### `control` - 제어 신호

```json
{
    "type": "control",
    "text": "start-mic"  // start-mic, interrupt, mic-audio-end
}
```

| 값 | 설명 |
|---|------|
| `start-mic` | 마이크 시작 |
| `interrupt` | 현재 응답 중단 |
| `mic-audio-end` | 마이크 입력 종료 (VAD 감지) |

### 4.4. 상태 메시지

#### `group-update` - 그룹 상태 업데이트

```json
{
    "type": "group-update",
    "members": ["client-uid-1", "client-uid-2"],
    "is_owner": true
}
```

#### `history-list` - 히스토리 목록

```json
{
    "type": "history-list",
    "histories": [
        {
            "uid": "history-uuid",
            "name": "Chat 1",
            "created_at": "2024-01-01T00:00:00Z"
        }
    ]
}
```

#### `history-data` - 히스토리 데이터

```json
{
    "type": "history-data",
    "messages": [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"}
    ]
}
```

#### `config-files` - 설정 파일 목록

```json
{
    "type": "config-files",
    "configs": [
        {"name": "Shizuku", "file": "shizuku.yaml"},
        {"name": "Haru", "file": "haru.yaml"}
    ]
}
```

### 4.5. 큐 상태 메시지

#### `queue-status-update` - 큐 상태 업데이트

```json
{
    "type": "queue-status-update",
    "status": {
        "pending": 3,
        "processing": 1,
        "max_size": 100,
        "total_received": 150,
        "total_processed": 145,
        "total_dropped": 2,
        "running": true,
        "avg_processing_time": 0.05,
        "processing_rate": 20.0
    },
    "timestamp": "2024-01-01T12:00:00.000Z"
}
```

#### `queue-alert` - 큐 알림

```json
{
    "type": "queue-alert",
    "alert_type": "overflow",
    "message": "Queue is full, messages may be dropped",
    "severity": "warning",
    "timestamp": "2024-01-01T12:00:00.000Z"
}
```

### 4.6. 에러 메시지

#### `error` - 에러

```json
{
    "type": "error",
    "message": "에러 메시지"
}
```

---

## 5. 예시 시나리오

### 시나리오 1: 텍스트 대화

```
1. [클라이언트 → 서버] text-input
   {"type": "text-input", "text": "오늘 날씨 어때?"}

2. [서버 → 클라이언트] sentence (여러 번)
   {"type": "sentence", "text": "오늘", ...}
   {"type": "sentence", "text": " 날씨는", ...}

3. [서버 → 클라이언트] audio
   {"type": "audio", "audio": "base64...", ...}
```

### 시나리오 2: 음성 대화

```
1. [클라이언트 → 서버] mic-audio-data (여러 번)
   {"type": "mic-audio-data", "audio": [0.1, -0.2, ...]}

2. [클라이언트 → 서버] mic-audio-end
   {"type": "mic-audio-end"}

3. [서버 → 클라이언트] sentence + audio
   (시나리오 1과 동일)
```

### 시나리오 3: 인터럽트

```
1. [서버 → 클라이언트] audio 재생 중...

2. [클라이언트 → 서버] interrupt-signal
   {"type": "interrupt-signal", "text": "지금까지 들은 내용"}

3. [서버] 응답 중단, 대화 컨텍스트 업데이트
```

### 시나리오 4: 설정 전환

```
1. [클라이언트 → 서버] fetch-configs
   {"type": "fetch-configs"}

2. [서버 → 클라이언트] config-files
   {"type": "config-files", "configs": [...]}

3. [클라이언트 → 서버] switch-config
   {"type": "switch-config", "file": "new-character.yaml"}

4. [서버 → 클라이언트] set-model-and-conf
   (새 모델 정보)
```

---

## 참고

- **구현 파일**: `src/open_llm_vtuber/websocket_handler.py`
- **라우팅**: `src/open_llm_vtuber/routes.py`
- **대화 처리**: `src/open_llm_vtuber/conversations/conversation_handler.py`
