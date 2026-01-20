"""Sherpa-ONNX ASR implementation with registry pattern for model types."""

import os
from typing import Callable

import numpy as np
import sherpa_onnx
import onnxruntime
from loguru import logger

from .asr_interface import ASRInterface
from .utils import download_and_extract, check_and_extract_local_file


def _create_transducer(config: "VoiceRecognition") -> sherpa_onnx.OfflineRecognizer:
    return sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=config.encoder,
        decoder=config.decoder,
        joiner=config.joiner,
        tokens=config.tokens,
        num_threads=config.num_threads,
        sample_rate=config.SAMPLE_RATE,
        feature_dim=config.feature_dim,
        decoding_method=config.decoding_method,
        hotwords_file=config.hotwords_file,
        hotwords_score=config.hotwords_score,
        modeling_unit=config.modeling_unit,
        bpe_vocab=config.bpe_vocab,
        blank_penalty=config.blank_penalty,
        debug=config.debug,
        provider=config.provider,
    )


def _create_paraformer(config: "VoiceRecognition") -> sherpa_onnx.OfflineRecognizer:
    return sherpa_onnx.OfflineRecognizer.from_paraformer(
        paraformer=config.paraformer,
        tokens=config.tokens,
        num_threads=config.num_threads,
        sample_rate=config.SAMPLE_RATE,
        feature_dim=config.feature_dim,
        decoding_method=config.decoding_method,
        debug=config.debug,
        provider=config.provider,
    )


def _create_nemo_ctc(config: "VoiceRecognition") -> sherpa_onnx.OfflineRecognizer:
    return sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
        model=config.nemo_ctc,
        tokens=config.tokens,
        num_threads=config.num_threads,
        sample_rate=config.SAMPLE_RATE,
        feature_dim=config.feature_dim,
        decoding_method=config.decoding_method,
        debug=config.debug,
        provider=config.provider,
    )


def _create_wenet_ctc(config: "VoiceRecognition") -> sherpa_onnx.OfflineRecognizer:
    return sherpa_onnx.OfflineRecognizer.from_wenet_ctc(
        model=config.wenet_ctc,
        tokens=config.tokens,
        num_threads=config.num_threads,
        sample_rate=config.SAMPLE_RATE,
        feature_dim=config.feature_dim,
        decoding_method=config.decoding_method,
        debug=config.debug,
        provider=config.provider,
    )


def _create_whisper(config: "VoiceRecognition") -> sherpa_onnx.OfflineRecognizer:
    return sherpa_onnx.OfflineRecognizer.from_whisper(
        encoder=config.whisper_encoder,
        decoder=config.whisper_decoder,
        tokens=config.tokens,
        num_threads=config.num_threads,
        decoding_method=config.decoding_method,
        debug=config.debug,
        language=config.whisper_language,
        task=config.whisper_task,
        tail_paddings=config.whisper_tail_paddings,
        provider=config.provider,
    )


def _create_tdnn_ctc(config: "VoiceRecognition") -> sherpa_onnx.OfflineRecognizer:
    return sherpa_onnx.OfflineRecognizer.from_tdnn_ctc(
        model=config.tdnn_model,
        tokens=config.tokens,
        sample_rate=config.SAMPLE_RATE,
        feature_dim=config.feature_dim,
        num_threads=config.num_threads,
        decoding_method=config.decoding_method,
        debug=config.debug,
        provider=config.provider,
    )


def _create_sense_voice(config: "VoiceRecognition") -> sherpa_onnx.OfflineRecognizer:
    _ensure_sense_voice_model(config.sense_voice)
    return sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=config.sense_voice,
        tokens=config.tokens,
        num_threads=config.num_threads,
        use_itn=config.use_itn,
        debug=config.debug,
        provider=config.provider,
    )


def _ensure_sense_voice_model(model_path: str) -> None:
    """Ensure SenseVoice model exists, download if necessary."""
    if model_path and os.path.isfile(model_path):
        return

    expected_path = "./models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
    if not model_path or not model_path.startswith(expected_path):
        logger.critical(
            "The SenseVoice model is missing. "
            "Please provide the path to the model.onnx file."
        )
        return

    logger.warning("SenseVoice model not found. Downloading the model...")

    url = (
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
        "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2"
    )
    output_dir = "./models"

    local_result = check_and_extract_local_file(url, output_dir)
    if local_result is None:
        logger.info("Local file not found. Downloading...")
        download_and_extract(url, output_dir)
    else:
        logger.info("Local file found. Using existing file.")


# Registry mapping model type to factory function
MODEL_FACTORIES: dict[str, Callable[["VoiceRecognition"], sherpa_onnx.OfflineRecognizer]] = {
    "transducer": _create_transducer,
    "paraformer": _create_paraformer,
    "nemo_ctc": _create_nemo_ctc,
    "wenet_ctc": _create_wenet_ctc,
    "whisper": _create_whisper,
    "tdnn_ctc": _create_tdnn_ctc,
    "sense_voice": _create_sense_voice,
}


class VoiceRecognition(ASRInterface):
    """Sherpa-ONNX based voice recognition."""

    def __init__(
        self,
        model_type: str = "paraformer",
        encoder: str = None,
        decoder: str = None,
        joiner: str = None,
        paraformer: str = None,
        nemo_ctc: str = None,
        wenet_ctc: str = None,
        tdnn_model: str = None,
        whisper_encoder: str = None,
        whisper_decoder: str = None,
        sense_voice: str = None,
        tokens: str = None,
        hotwords_file: str = "",
        hotwords_score: float = 1.5,
        modeling_unit: str = "",
        bpe_vocab: str = "",
        num_threads: int = 1,
        whisper_language: str = "",
        whisper_task: str = "transcribe",
        whisper_tail_paddings: int = -1,
        blank_penalty: float = 0.0,
        decoding_method: str = "greedy_search",
        debug: bool = False,
        sample_rate: int = 16000,
        feature_dim: int = 80,
        use_itn: bool = True,
        provider: str = "cpu",
    ) -> None:
        self.model_type = model_type
        self.encoder = encoder
        self.decoder = decoder
        self.joiner = joiner
        self.paraformer = paraformer
        self.nemo_ctc = nemo_ctc
        self.wenet_ctc = wenet_ctc
        self.tdnn_model = tdnn_model
        self.whisper_encoder = whisper_encoder
        self.whisper_decoder = whisper_decoder
        self.sense_voice = sense_voice
        self.tokens = tokens
        self.hotwords_file = hotwords_file
        self.hotwords_score = hotwords_score
        self.modeling_unit = modeling_unit
        self.bpe_vocab = bpe_vocab
        self.num_threads = num_threads
        self.whisper_language = whisper_language
        self.whisper_task = whisper_task
        self.whisper_tail_paddings = whisper_tail_paddings
        self.blank_penalty = blank_penalty
        self.decoding_method = decoding_method
        self.debug = debug
        self.SAMPLE_RATE = sample_rate
        self.feature_dim = feature_dim
        self.use_itn = use_itn

        self.provider = self._validate_provider(provider)
        logger.info(f"Sherpa-Onnx-ASR: Using {self.provider} for inference")

        self.recognizer = self._create_recognizer()

    def _validate_provider(self, provider: str) -> str:
        """Validate and return the provider, falling back to CPU if needed."""
        if provider != "cuda":
            return provider

        try:
            if "CUDAExecutionProvider" not in onnxruntime.get_available_providers():
                logger.warning(
                    "CUDA provider not available for ONNX. Falling back to CPU."
                )
                return "cpu"
        except ImportError:
            logger.warning("ONNX Runtime not installed. Falling back to CPU.")
            return "cpu"

        return provider

    def _create_recognizer(self) -> sherpa_onnx.OfflineRecognizer:
        """Create recognizer based on model type using registry pattern."""
        factory = MODEL_FACTORIES.get(self.model_type)
        if factory is None:
            available = ", ".join(sorted(MODEL_FACTORIES.keys()))
            raise ValueError(
                f"Invalid model type: {self.model_type}. "
                f"Available types: {available}"
            )
        return factory(self)

    def transcribe_np(self, audio: np.ndarray) -> str:
        """Transcribe audio from numpy array."""
        stream = self.recognizer.create_stream()
        stream.accept_waveform(self.SAMPLE_RATE, audio)
        self.recognizer.decode_streams([stream])
        return stream.result.text
