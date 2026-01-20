/**
 * 오디오 및 네트워크 관련 상수 정의
 *
 * 이 파일은 web_tool의 main.js와 recorder.js에서 사용되는
 * 매직 넘버들을 명명된 상수로 정의합니다.
 *
 * 주의: 이 파일은 다른 JavaScript 파일들보다 먼저 로드되어야 합니다.
 */

/**
 * 오디오 처리 관련 상수
 */
const AUDIO = Object.freeze({
    // 샘플 레이트 (Hz) - ASR/TTS에서 사용하는 표준 샘플 레이트
    SAMPLE_RATE: 16000,

    // WAV 파일 헤더 크기 (바이트)
    WAV_HEADER_SIZE: 44,

    // 비트 깊이 (bits per sample)
    BIT_DEPTH: 16,

    // 채널 수 (모노)
    NUM_CHANNELS: 1,

    // PCM 포맷 식별자
    PCM_FORMAT: 1,

    // fmt 청크 크기 (바이트)
    FMT_CHUNK_SIZE: 16,

    // 16-bit signed integer 최대값 (0x7FFF = 32767)
    // float32 양수를 int16으로 변환할 때 곱하는 값
    INT16_MAX: 0x7fff,

    // 16-bit signed integer 최소값의 절대값 (0x8000 = 32768)
    // float32 음수를 int16으로 변환할 때 곱하는 값
    INT16_MIN_ABS: 0x8000,
});

/**
 * 네트워크 및 타이밍 관련 상수
 */
const NETWORK = Object.freeze({
    // WebSocket 재연결 지연 시간 (밀리초)
    WEBSOCKET_RECONNECT_DELAY_MS: 5000,

    // HTTP fetch 최대 재시도 횟수
    MAX_FETCH_RETRIES: 3,

    // 재시도 간 지연 시간 (밀리초)
    RETRY_DELAY_MS: 1000,

    // 대기 중인 오디오 완료 대기 시간 (밀리초)
    PENDING_AUDIO_WAIT_MS: 500,
});
