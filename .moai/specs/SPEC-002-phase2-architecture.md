# SPEC-002: Phase 2 아키텍처 개선 (Architecture Improvement)

## 메타데이터

| 항목 | 값 |
|------|-----|
| **SPEC ID** | SPEC-002 |
| **제목** | Phase 2: 아키텍처 개선 - God Object 분리 |
| **상태** | Draft |
| **우선순위** | High |
| **예상 범위** | 백엔드 + 프론트엔드 |
| **선행 조건** | SPEC-001 완료 |
| **작성일** | 2026-01-25 |
| **관련 문서** | `docs/CODE_REVIEW_2026-01-25.md` |

---

## 1. 배경 및 목적

### 1.1 현재 상태

| 파일 | 줄 수 | 문제 |
|------|-------|------|
| `websocket_handler.py` | 1,431 | 7개 이상의 책임 혼재 |
| `CompanionMode.tsx` | 517 | Electron/Web 로직 혼재 |
| `store/index.ts` | 793 | 모든 상태/액션 단일 파일 |

### 1.2 목적

1. **단일 책임 원칙 적용**: 대형 파일을 목적별 모듈로 분리
2. **테스트 용이성 향상**: 작은 단위로 분리하여 단위 테스트 가능
3. **유지보수성 향상**: 변경 영향 범위 최소화

### 1.3 성공 기준

- [ ] `websocket_handler.py` → 5개 이하 파일로 분리
- [ ] `CompanionMode.tsx` → Electron/Web 분리
- [ ] `store/index.ts` → 6개 슬라이스로 분리
- [ ] 기존 기능 100% 유지 (회귀 테스트 통과)

---

## 2. 요구사항

### 2.1 WebSocketHandler 분리 (백엔드)

#### REQ-013: 연결 관리자 분리
**THE SYSTEM SHALL** WebSocket 연결 생명주기를 별도 클래스로 분리한다.

**새 파일:** `websocket/connection_manager.py`
```python
class WebSocketConnectionManager:
    """WebSocket 연결 추적 및 세션 관리"""
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, client_id: str, websocket: WebSocket): ...
    async def disconnect(self, client_id: str): ...
    async def broadcast(self, message: dict): ...
```

#### REQ-014: 메시지 라우터 분리
**THE SYSTEM SHALL** 메시지 타입별 라우팅을 별도 클래스로 분리한다.

**새 파일:** `websocket/message_router.py`
```python
class WebSocketMessageRouter:
    """메시지 타입별 핸들러 라우팅"""
    def __init__(self):
        self.handlers: dict[str, Callable] = {}

    def register(self, message_type: str, handler: Callable): ...
    async def route(self, message: dict): ...
```

#### REQ-015: 그룹 관리자 분리
**THE SYSTEM SHALL** 채팅 그룹 관리를 별도 클래스로 분리한다.

**새 파일:** `websocket/group_manager.py`
```python
class ChatGroupManager:
    """그룹 생성, 참여, 탈퇴 관리"""
    async def create_group(self, group_id: str): ...
    async def add_to_group(self, client_id: str, group_id: str): ...
    async def remove_from_group(self, client_id: str, group_id: str): ...
```

#### REQ-016: 상태 관리자 분리
**THE SYSTEM SHALL** 클라이언트 상태를 별도 클래스로 분리한다.

**새 파일:** `websocket/state_manager.py`
```python
class ClientStateManager:
    """클라이언트별 상태 및 컨텍스트 관리"""
    def get_context(self, client_id: str) -> ServiceContext: ...
    def set_context(self, client_id: str, context: ServiceContext): ...
```

#### REQ-017: 통합 핸들러 리팩토링
**THE SYSTEM SHALL** `WebSocketHandler`를 조합 패턴으로 리팩토링한다.

**변경된 파일:** `websocket_handler.py` (500줄 이하로 축소)
```python
class WebSocketHandler:
    def __init__(
        self,
        connection_manager: WebSocketConnectionManager,
        message_router: WebSocketMessageRouter,
        group_manager: ChatGroupManager,
        state_manager: ClientStateManager,
    ):
        self.connections = connection_manager
        self.router = message_router
        self.groups = group_manager
        self.state = state_manager
```

---

### 2.2 CompanionMode 분리 (프론트엔드)

#### REQ-018: Electron/Web 분리
**THE SYSTEM SHALL** 플랫폼별 컴포넌트를 분리한다.

**새 구조:**
```
features/modes/components/
├── CompanionMode.tsx          # 라우팅/조건부 렌더링 (~50줄)
├── companion/
│   ├── ElectronCompanion.tsx  # Electron 전용 (~180줄)
│   ├── WebCompanion.tsx       # 웹 전용 (~150줄)
│   └── shared/
│       ├── CharacterDisplay.tsx
│       └── ControlButtons.tsx
```

#### REQ-019: 드래그 로직 추출
**THE SYSTEM SHALL** 드래그 로직을 커스텀 훅으로 추출한다.

**새 파일:** `features/modes/hooks/useCompanionDrag.ts`
```typescript
export function useCompanionDrag() {
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);

  const handleMouseDown = useCallback(...);
  const handleMouseMove = useCallback(...);
  const handleMouseUp = useCallback(...);

  return { position, isDragging, handlers };
}
```

---

### 2.3 Store 슬라이스 분리 (프론트엔드)

#### REQ-020: 도메인별 슬라이스 분리
**THE SYSTEM SHALL** 상태를 도메인별 슬라이스로 분리한다.

**새 구조:**
```
shared/store/
├── index.ts           # 통합 export
├── slices/
│   ├── uiSlice.ts          # UI 상태 (모달, 사이드바 등)
│   ├── characterSlice.ts   # 캐릭터/Live2D 상태
│   ├── conversationSlice.ts # 대화 상태
│   ├── mediaSlice.ts       # 오디오/비디오 상태
│   ├── settingsSlice.ts    # 설정 상태
│   └── connectionSlice.ts  # WebSocket 연결 상태
└── types.ts           # 공통 타입
```

#### REQ-021: 슬라이스 타입 정의
**THE SYSTEM SHALL** 각 슬라이스의 타입을 명확히 정의한다.

**예시:** `slices/characterSlice.ts`
```typescript
interface CharacterState {
  modelPath: string;
  position: { x: number; y: number };
  scale: number;
  lipSyncValue: number;
  currentExpression: string;
}

interface CharacterActions {
  setModelPath: (path: string) => void;
  setPosition: (pos: { x: number; y: number }) => void;
  setLipSyncValue: (value: number) => void;
}

export const createCharacterSlice = (set, get) => ({
  character: { /* initial state */ },
  setModelPath: (path) => set(...),
  // ...
});
```

---

## 3. 구현 계획

### 3.1 작업 분해

| # | 작업 | 파일 | 예상 |
|---|------|------|------|
| 1 | connection_manager.py 생성 | 신규 | 1시간 |
| 2 | message_router.py 생성 | 신규 | 1시간 |
| 3 | group_manager.py 생성 | 신규 | 45분 |
| 4 | state_manager.py 생성 | 신규 | 45분 |
| 5 | websocket_handler.py 리팩토링 | 기존 파일 | 2시간 |
| 6 | ElectronCompanion.tsx 분리 | 신규 | 1시간 |
| 7 | WebCompanion.tsx 분리 | 신규 | 1시간 |
| 8 | useCompanionDrag.ts 추출 | 신규 | 30분 |
| 9 | Store 슬라이스 6개 생성 | 신규 | 2시간 |
| 10 | 기존 import 경로 수정 | 다수 | 1시간 |
| 11 | 회귀 테스트 | 전체 | 1시간 |

### 3.2 의존성 관계

```
REQ-013 (connection_manager)
REQ-014 (message_router)     ─┬─→ REQ-017 (통합 핸들러)
REQ-015 (group_manager)       │
REQ-016 (state_manager)      ─┘

REQ-018 (Electron/Web 분리)
    └── REQ-019 (드래그 훅)

REQ-020 (슬라이스 분리)
    └── REQ-021 (타입 정의)
```

---

## 4. 테스트 계획

### 4.1 단위 테스트 (신규)

| 모듈 | 테스트 파일 | 테스트 케이스 |
|------|------------|--------------|
| ConnectionManager | `test_connection_manager.py` | connect, disconnect, broadcast |
| MessageRouter | `test_message_router.py` | register, route, unknown_type |
| GroupManager | `test_group_manager.py` | create, add, remove |
| CharacterSlice | `characterSlice.test.ts` | setModelPath, setPosition |

### 4.2 통합 테스트

| 테스트 | 검증 내용 |
|--------|----------|
| WebSocket 전체 흐름 | 연결 → 메시지 → 응답 |
| CompanionMode 렌더링 | Electron/Web 각각 |
| Store 상태 동기화 | 슬라이스 간 상태 일관성 |

### 4.3 회귀 테스트

- 기존 E2E 시나리오 모두 통과
- WebSocket 메시지 형식 호환성 유지

---

## 5. 리스크 및 완화

| 리스크 | 가능성 | 영향 | 완화 전략 |
|--------|--------|------|----------|
| Import 경로 누락 | 높음 | 중간 | IDE 리팩토링 도구 활용, grep 검증 |
| 순환 참조 발생 | 중간 | 높음 | 의존성 방향 문서화, 팩토리 패턴 |
| Store 마이그레이션 실패 | 중간 | 높음 | 점진적 마이그레이션, 호환 레이어 |

---

## 6. 완료 체크리스트

- [ ] `websocket_handler.py`가 500줄 이하로 축소됨
- [ ] 새로운 4개 WebSocket 모듈이 생성됨
- [ ] `CompanionMode.tsx`가 50줄 이하로 축소됨
- [ ] Electron/Web 컴포넌트가 분리됨
- [ ] Store가 6개 슬라이스로 분리됨
- [ ] 모든 기존 기능이 정상 작동함
- [ ] 새 모듈에 대한 단위 테스트가 추가됨

---

*이 SPEC은 SPEC-001 완료 후 진행됩니다.*
