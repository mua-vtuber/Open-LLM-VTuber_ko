import time


from open_llm_vtuber.umsa.stream_context import StreamContext


def test_stream_context_init():
    ctx = StreamContext()
    assert ctx.current_topic == ""
    assert ctx.current_mood == "neutral"
    assert len(ctx.recent_events) == 0
    assert len(ctx.active_viewers) == 0


def test_update_with_chat_message():
    ctx = StreamContext()
    ctx.update(author="UserA", content="I love this game!", msg_type="chat")
    assert "UserA" in ctx.active_viewers
    assert ctx.message_count == 1


def test_update_with_superchat():
    ctx = StreamContext(max_events=5)
    ctx.update(
        author="UserB",
        content="Great stream!",
        msg_type="superchat",
        metadata={"amount": 5000, "currency": "KRW"},
    )
    assert len(ctx.recent_events) == 1
    assert ctx.recent_events[0].event_type == "superchat"
    assert ctx.recent_events[0].metadata["amount"] == 5000


def test_max_events_bounded():
    ctx = StreamContext(max_events=3)
    for i in range(5):
        ctx.update(author=f"User{i}", content="msg", msg_type="superchat")
    assert len(ctx.recent_events) == 3


def test_format_for_context():
    ctx = StreamContext()
    ctx.current_topic = "Minecraft Survival"
    ctx.current_mood = "excited"
    ctx.update(author="UserA", content="hello", msg_type="chat")
    text = ctx.format_for_context()
    assert "Minecraft Survival" in text
    assert "excited" in text
    assert "UserA" in text


def test_to_episode_dict():
    ctx = StreamContext()
    ctx.current_topic = "Building"
    ctx.update(author="A", content="hi", msg_type="chat")
    ctx.update(author="B", content="superchat!", msg_type="superchat")
    ep = ctx.to_episode_dict()
    assert "summary" in ep
    assert "topics" in ep
    assert "participant_count" in ep


def test_active_viewers_expire():
    ctx = StreamContext(viewer_timeout_seconds=0)
    ctx.update(author="OldUser", content="hi", msg_type="chat")
    time.sleep(0.01)
    ctx._prune_inactive_viewers()
    assert "OldUser" not in ctx.active_viewers


def test_clear_resets_state():
    ctx = StreamContext()
    ctx.current_topic = "Test"
    ctx.update(author="A", content="hi", msg_type="chat")
    ctx.clear()
    assert ctx.current_topic == ""
    assert ctx.message_count == 0
    assert len(ctx.active_viewers) == 0
