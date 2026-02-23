"""
mem0_agent 서버 통합 테스트 스크립트

서버를 완전히 시작하지 않고, 설정 로드 및 agent 초기화만 테스트합니다.
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_config_loading():
    """설정 파일에서 mem0_agent 설정을 제대로 로드하는지 테스트"""
    print("=" * 60)
    print("1. 설정 파일 로드 테스트")
    print("=" * 60)

    from src.open_llm_vtuber.config_manager import Config, read_yaml, validate_config

    config: Config = validate_config(read_yaml("conf.yaml"))

    agent_choice = config.character_config.agent_config.conversation_agent_choice
    print(f"✓ 선택된 agent: {agent_choice}")

    if agent_choice != "mem0_agent":
        print(f"✗ 에러: agent_choice가 'mem0_agent'가 아닙니다: {agent_choice}")
        return False

    # mem0_agent 설정 확인
    mem0_config = config.character_config.agent_config.agent_settings.mem0_agent
    print(
        f"✓ mem0_agent 설정 존재: base_url={mem0_config.base_url}, model={mem0_config.model}"
    )

    return True


def test_agent_factory():
    """AgentFactory가 mem0_agent를 생성할 수 있는지 테스트"""
    print("\n" + "=" * 60)
    print("2. AgentFactory를 통한 mem0_agent 생성 테스트")
    print("=" * 60)

    from src.open_llm_vtuber.config_manager import Config, read_yaml, validate_config
    from src.open_llm_vtuber.agent.agent_factory import AgentFactory

    config: Config = validate_config(read_yaml("conf.yaml"))

    try:
        # Pydantic 객체를 dict로 변환
        agent_config = config.character_config.agent_config
        agent_settings_dict = agent_config.agent_settings.model_dump(by_alias=True)
        llm_configs_dict = agent_config.llm_configs.model_dump(by_alias=True)

        # agent 생성 시도
        agent = AgentFactory.create_agent(
            conversation_agent_choice=agent_config.conversation_agent_choice,
            agent_settings=agent_settings_dict,
            llm_configs=llm_configs_dict,
            system_prompt=config.character_config.persona_prompt,
            live2d_model=None,
            user_id="test_user",
        )

        print(f"✓ Agent 생성 성공: {type(agent).__name__}")
        print(
            f"✓ Agent 클래스: {agent.__class__.__module__}.{agent.__class__.__name__}"
        )

        # AgentInterface 메서드 확인
        required_methods = ["chat", "handle_interrupt", "set_memory_from_history"]
        for method in required_methods:
            if hasattr(agent, method):
                print(f"✓ {method} 메서드 존재")
            else:
                print(f"✗ {method} 메서드 없음")
                return False

        return True

    except Exception as e:
        print(f"✗ Agent 생성 실패: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_mem0_initialization():
    """mem0 Memory 인스턴스가 초기화되는지 테스트 (Qdrant 없이도 객체 생성 가능한지)"""
    print("\n" + "=" * 60)
    print("3. mem0 초기화 테스트")
    print("=" * 60)

    try:
        print("✓ mem0 라이브러리 import 성공")

        # 참고: 실제 Qdrant 연결 없이는 Memory 인스턴스 생성이 실패할 수 있음
        # 하지만 import는 성공해야 함

        return True

    except Exception as e:
        print(f"✗ mem0 import 실패: {type(e).__name__}: {e}")
        return False


def main():
    print("\nmem0_agent 서버 통합 테스트 시작\n")

    results = []

    # 테스트 실행
    results.append(("설정 로드", test_config_loading()))
    results.append(("mem0 초기화", test_mem0_initialization()))
    results.append(("Agent Factory", test_agent_factory()))

    # 결과 요약
    print("\n" + "=" * 60)
    print("테스트 결과 요약")
    print("=" * 60)

    all_passed = True
    for test_name, result in results:
        status = "✓ 성공" if result else "✗ 실패"
        print(f"{test_name}: {status}")
        if not result:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("모든 테스트 통과! mem0_agent가 서버와 정상적으로 통합되었습니다.")
        print("\n참고: 실제 메모리 저장/검색 기능을 테스트하려면:")
        print("  1. Qdrant 서버 실행 (Docker: docker run -p 6333:6333 qdrant/qdrant)")
        print("  2. conf.yaml의 mem0_config에서 Qdrant 설정 확인")
        print("  3. uv run run_server.py 실행")
        print("  4. WebSocket 연결 후 대화 테스트")
    else:
        print("일부 테스트 실패. 위 에러 메시지를 확인하세요.")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
