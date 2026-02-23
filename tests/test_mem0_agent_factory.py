#!/usr/bin/env python3
"""
mem0_agent 생성 테스트 스크립트
agent_factory.create_agent()를 통해 mem0_agent 인스턴스가 정상적으로 생성되는지 확인
"""

import sys
from loguru import logger


def test_mem0_agent_creation():
    """agent_factory를 통한 mem0_agent 생성 테스트"""

    logger.info("=== mem0_agent 생성 테스트 시작 ===")

    try:
        # agent_factory import
        from src.open_llm_vtuber.agent.agent_factory import AgentFactory

        logger.success("✓ AgentFactory import 성공")

        # mem0_agent 설정 준비
        conversation_agent_choice = "mem0_agent"

        agent_settings = {
            "mem0_agent": {
                "base_url": "http://localhost:11434/v1",
                "model": "test-model",
                "faster_first_response": True,
                "segment_method": "pysbd",
                "mem0_config": {
                    "vector_store": {
                        "provider": "qdrant",
                        "config": {
                            "collection_name": "test_memories",
                            "host": "localhost",
                            "port": 6333,
                        },
                    }
                },
            }
        }

        llm_configs = {}  # mem0_agent는 llm_configs를 사용하지 않음
        system_prompt = "You are a helpful AI assistant with long-term memory."

        logger.info("설정 준비 완료")
        logger.debug(f"conversation_agent_choice: {conversation_agent_choice}")
        logger.debug(f"agent_settings: {agent_settings}")

        # agent 생성
        logger.info("agent_factory.create_agent() 호출...")
        agent = AgentFactory.create_agent(
            conversation_agent_choice=conversation_agent_choice,
            agent_settings=agent_settings,
            llm_configs=llm_configs,
            system_prompt=system_prompt,
            live2d_model=None,  # 테스트에서는 None
            tts_preprocessor_config=None,  # 테스트에서는 None
            user_id="test_user_123",
        )

        logger.success("✓ mem0_agent 인스턴스 생성 성공!")
        logger.info(f"생성된 agent 타입: {type(agent)}")
        logger.info(f"agent 클래스 이름: {agent.__class__.__name__}")

        # AgentInterface 상속 확인
        from src.open_llm_vtuber.agent.agents.agent_interface import AgentInterface

        if isinstance(agent, AgentInterface):
            logger.success("✓ agent는 AgentInterface를 올바르게 구현했습니다")
        else:
            logger.error("✗ agent가 AgentInterface를 구현하지 않았습니다")
            return False

        # 필수 메서드 존재 확인
        required_methods = ["chat", "handle_interrupt", "set_memory_from_history"]
        for method_name in required_methods:
            if hasattr(agent, method_name):
                logger.success(f"✓ {method_name} 메서드 존재")
            else:
                logger.error(f"✗ {method_name} 메서드 없음")
                return False

        # 내부 속성 확인
        if hasattr(agent, "_user_id"):
            logger.success(f"✓ _user_id 속성 존재: {agent._user_id}")
        if hasattr(agent, "_system"):
            logger.success("✓ _system 속성 존재")
        if hasattr(agent, "_model"):
            logger.success(f"✓ _model 속성 존재: {agent._model}")

        logger.success("\n=== 모든 테스트 통과! ===")
        return True

    except Exception as e:
        logger.error(f"✗ 테스트 실패: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return False


if __name__ == "__main__":
    logger.remove()  # 기본 핸들러 제거
    logger.add(sys.stderr, level="DEBUG")  # 디버그 레벨로 설정

    success = test_mem0_agent_creation()

    if success:
        print(
            "\n✅ 테스트 성공: agent_factory에서 mem0_agent를 정상적으로 생성할 수 있습니다."
        )
        sys.exit(0)
    else:
        print("\n❌ 테스트 실패: 위의 오류를 확인하세요.")
        sys.exit(1)
