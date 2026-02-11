# config_manager/utils.py
import yaml
from pathlib import Path
from typing import Union, Dict, Any, TypeVar
from pydantic import BaseModel, ValidationError
import os
import re
import chardet
from loguru import logger

from .main import Config

T = TypeVar("T", bound=BaseModel)


def read_yaml(config_path: str) -> Dict[str, Any]:
    """
    Read the specified YAML configuration file with environment variable substitution
    and guess encoding. Return the configuration data as a dictionary.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Configuration data as a dictionary.

    Raises:
        FileNotFoundError: If the configuration file is not found.
        IOError: If the configuration file cannot be read.
    """

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    content = load_text_file_with_guess_encoding(config_path)
    if not content:
        raise IOError(f"Failed to read configuration file: {config_path}")

    # Replace environment variables
    pattern = re.compile(r"\$\{(\w+)\}")

    def replacer(match):
        env_var = match.group(1)
        return os.getenv(env_var, match.group(0))

    content = pattern.sub(replacer, content)

    try:
        return yaml.safe_load(content)
    except yaml.YAMLError as e:
        logger.critical(f"Error parsing YAML file: {e}")
        raise e


def _format_validation_error(error: ValidationError) -> str:
    """
    ValidationError를 사용자 친화적인 오류 메시지로 포맷합니다.

    Args:
        error: Pydantic ValidationError

    Returns:
        포맷된 오류 메시지 문자열
    """
    error_messages = []

    for err in error.errors():
        # 오류 발생 위치 추출 (예: character_config -> agent_config -> llm_provider)
        location = " -> ".join(str(loc) for loc in err["loc"])
        error_type = err["type"]
        msg = err["msg"]
        input_value = err.get("input", "N/A")

        # 사용자 친화적 오류 메시지 생성
        if error_type == "missing":
            error_messages.append(
                f"  - '{location}': 필수 필드가 누락되었습니다. "
                f"conf.yaml에 이 필드를 추가해주세요."
            )
        elif error_type == "string_type":
            error_messages.append(
                f"  - '{location}': 문자열 타입이 필요합니다. "
                f"현재 값: {input_value}"
            )
        elif error_type == "int_type":
            error_messages.append(
                f"  - '{location}': 정수 타입이 필요합니다. "
                f"현재 값: {input_value}"
            )
        elif error_type == "bool_type":
            error_messages.append(
                f"  - '{location}': 불리언 타입이 필요합니다 (true/false). "
                f"현재 값: {input_value}"
            )
        elif error_type == "value_error":
            error_messages.append(
                f"  - '{location}': {msg}"
            )
        elif "greater_than" in error_type or "less_than" in error_type:
            error_messages.append(
                f"  - '{location}': 값이 범위를 벗어났습니다. {msg}"
            )
        else:
            error_messages.append(
                f"  - '{location}': {msg} (타입: {error_type})"
            )

    return "\n".join(error_messages)


def validate_config(config_data: dict) -> Config:
    """
    설정 데이터를 Config 모델에 대해 검증합니다.

    Args:
        config_data: 검증할 설정 데이터 딕셔너리

    Returns:
        검증된 Config 객체

    Raises:
        ValidationError: 설정 검증 실패 시

    Note:
        검증 실패 시 사용자 친화적인 오류 메시지를 로그에 출력합니다.
        오류 메시지에는 문제 위치, 예상 타입, 현재 값 등이 포함됩니다.
    """
    try:
        return Config(**config_data)
    except ValidationError as e:
        # 사용자 친화적 오류 메시지 생성
        formatted_errors = _format_validation_error(e)

        logger.critical(
            "\n"
            "=" * 60 + "\n"
            "설정 파일 검증 실패 (Configuration Validation Error)\n"
            "=" * 60 + "\n"
            f"\n발견된 오류:\n{formatted_errors}\n"
            "\n해결 방법:\n"
            "  1. conf.yaml 파일을 열어 위 오류를 수정하세요.\n"
            "  2. config_templates/conf.default.yaml을 참고하세요.\n"
            "  3. 필수 필드가 모두 있는지 확인하세요.\n"
            "=" * 60
        )

        # 원본 오류도 디버그용으로 출력
        logger.debug(f"Original validation error: {e}")
        logger.debug(f"Configuration data keys: {list(config_data.keys())}")

        raise e


def load_text_file_with_guess_encoding(file_path: str) -> str | None:
    """
    Load a text file with guessed encoding.

    Parameters:
    - file_path (str): The path to the text file.

    Returns:
    - str: The content of the text file or None if an error occurred.
    """
    encodings = ["utf-8", "utf-8-sig", "gbk", "gb2312", "ascii", "cp936"]

    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as file:
                return file.read()
        except UnicodeDecodeError:
            continue
    # If common encodings fail, try chardet to guess the encoding
    try:
        with open(file_path, "rb") as file:
            raw_data = file.read()
        detected = chardet.detect(raw_data)
        if detected["encoding"]:
            return raw_data.decode(detected["encoding"])
    except Exception as e:
        logger.error(f"Error detecting encoding for config file {file_path}: {e}")
    return None


def save_config(config: BaseModel, config_path: Union[str, Path]):
    """
    Saves a Pydantic model to a YAML configuration file.

    Args:
        config: The Pydantic model to save.
        config_path: Path to the YAML configuration file.
    """
    config_file = Path(config_path)
    config_data = config.model_dump(
        by_alias=True, exclude_unset=True, exclude_none=True
    )

    try:
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f, allow_unicode=True)
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Error writing YAML file: {e}")


def save_partial_yaml(
    section_name: str,
    section_data: Dict[str, Any],
    config_path: str = "conf.yaml"
):
    """
    conf.yaml의 특정 섹션만 업데이트합니다.
    전체 파일을 읽은 뒤 해당 섹션만 변경하고 다시 저장합니다.

    Args:
        section_name: 업데이트할 섹션 이름 (예: "live_config")
        section_data: 새로운 섹션 데이터
        config_path: YAML 설정 파일 경로

    Raises:
        FileNotFoundError: 설정 파일이 없을 때
        yaml.YAMLError: YAML 파싱/쓰기 오류
    """
    # 전체 설정 읽기
    config_data = read_yaml(config_path)

    # 섹션 업데이트
    config_data[section_name] = section_data

    # 파일에 저장
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(
                config_data,
                f,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False
            )
        logger.debug(f"설정 섹션 '{section_name}'이 {config_path}에 저장되었습니다")
    except yaml.YAMLError as e:
        logger.error(f"YAML 파일 쓰기 오류: {e}")
        raise yaml.YAMLError(f"Error writing YAML file: {e}")


def scan_config_alts_directory(config_alts_dir: str) -> list[dict]:
    """
    Scan the config_alts directory and return a list of config information.
    Each config info contains the filename and its display name from the config.

    Parameters:
    - config_alts_dir (str): The path to the config_alts directory.

    Returns:
    - list[dict]: A list of dicts containing config info:
        - filename: The actual config file name
        - name: Display name from config, falls back to filename if not specified
    """
    config_files = []

    # Add default config first
    default_config = read_yaml("conf.yaml")
    config_files.append(
        {
            "filename": "conf.yaml",
            "name": default_config.get("character_config", {}).get(
                "conf_name", "conf.yaml"
            )
            if default_config
            else "conf.yaml",
        }
    )

    # Scan other configs
    for root, _, files in os.walk(config_alts_dir):
        for file in files:
            if file.endswith(".yaml"):
                config: dict = read_yaml(os.path.join(root, file))
                config_files.append(
                    {
                        "filename": file,
                        "name": config.get("character_config", {}).get(
                            "conf_name", file
                        )
                        if config
                        else file,
                    }
                )
    logger.debug(f"Found config files: {config_files}")
    return config_files


def scan_bg_directory() -> list[str]:
    bg_files = []
    bg_dir = "backgrounds"
    for root, _, files in os.walk(bg_dir):
        for file in files:
            if file.endswith((".jpg", ".jpeg", ".png", ".gif")):
                bg_files.append(file)
    return bg_files
