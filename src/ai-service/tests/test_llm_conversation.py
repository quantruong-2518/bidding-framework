"""Phase 3.7d — stateful LLMConversation: cross-model memory + tier swap + compact()."""

from __future__ import annotations

import pytest

from tools.llm import (
    FakeLLMClient,
    LLMConversation,
    LLMMessage,
    ScriptedResponse,
    TokenUsage,
)
from tools.llm.errors import LLMError


# ---------------------------------------------------------------------------
# Memory accumulates and is sent on every turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_appends_user_and_assistant_messages() -> None:
    fake = FakeLLMClient([ScriptedResponse(text="hello back")])
    conv = LLMConversation(system="you are helpful", client=fake)

    response = await conv.send("hi")

    assert response.text == "hello back"
    assert [m.role for m in conv.messages] == ["system", "user", "assistant"]
    assert conv.messages[1].content == "hi"
    assert conv.messages[2].content == "hello back"


@pytest.mark.asyncio
async def test_history_grows_across_turns_and_is_resent() -> None:
    fake = FakeLLMClient(
        [
            ScriptedResponse(text="r1"),
            ScriptedResponse(text="r2"),
            ScriptedResponse(text="r3"),
        ]
    )
    conv = LLMConversation(system="sys", client=fake)

    await conv.send("turn 1")
    await conv.send("turn 2")
    await conv.send("turn 3")

    # Each call should see the full prefix of prior messages.
    assert [m.role for m in fake.calls[0].messages] == ["system", "user"]
    assert [m.role for m in fake.calls[1].messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert [m.role for m in fake.calls[2].messages] == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
    ]
    assert fake.calls[2].messages[-1].content == "turn 3"


# ---------------------------------------------------------------------------
# Tier swap mid-conversation — memory preserved
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_each_turn_uses_its_requested_tier() -> None:
    fake = FakeLLMClient(
        [
            ScriptedResponse(text="extracted",  model="openai/gpt-4o-mini",   provider="openai"),
            ScriptedResponse(text="grouped",    model="openai/gpt-4o-mini",   provider="openai"),
            ScriptedResponse(text="critiqued",  model="openai/gpt-4o",        provider="openai"),
            ScriptedResponse(text="planned",    model="openai/o1",            provider="openai"),
        ]
    )
    conv = LLMConversation(system="bid analyst", client=fake)

    await conv.send("extract", tier="nano")
    await conv.send("group", tier="small")
    await conv.send("critique", tier="flagship")
    await conv.send("plan", tier="deep")

    assert [c.tier for c in fake.calls] == ["nano", "small", "flagship", "deep"]
    # Last turn sees the full history of prior tiers — provider-agnostic
    # memory works because messages are plain text.
    assert fake.calls[-1].messages[1].content == "extract"
    assert fake.calls[-1].messages[3].content == "group"
    assert fake.calls[-1].messages[5].content == "critique"


@pytest.mark.asyncio
async def test_default_tier_is_used_when_send_omits_tier() -> None:
    fake = FakeLLMClient([ScriptedResponse(text="ok")] * 2)
    conv = LLMConversation(client=fake, default_tier="small")

    await conv.send("a")
    await conv.send("b", tier="deep")

    assert fake.calls[0].tier == "small"
    assert fake.calls[1].tier == "deep"


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_audit_records_tier_model_cost_tokens() -> None:
    fake = FakeLLMClient(
        [
            ScriptedResponse(
                text="r1",
                model="openai/gpt-4o-mini",
                provider="openai",
                cost_usd=0.0001,
                latency_ms=120,
                usage=TokenUsage(input_tokens=10, output_tokens=4, cache_read_tokens=8),
            ),
            ScriptedResponse(
                text="r2",
                model="openai/o1",
                provider="openai",
                cost_usd=0.05,
                latency_ms=4200,
                usage=TokenUsage(input_tokens=200, output_tokens=120),
            ),
        ]
    )
    conv = LLMConversation(client=fake)
    await conv.send("a", tier="nano")
    await conv.send("b", tier="deep")

    assert len(conv.turns) == 2
    nano, deep = conv.turns
    assert nano.tier == "nano" and nano.model == "openai/gpt-4o-mini"
    assert nano.cost_usd == 0.0001 and nano.latency_ms == 120
    assert nano.cache_read_tokens == 8

    assert deep.tier == "deep" and deep.model == "openai/o1"
    assert deep.cost_usd == 0.05

    assert conv.total_cost_usd == round(0.0001 + 0.05, 6)
    assert conv.total_input_tokens == 210
    assert conv.total_output_tokens == 124


# ---------------------------------------------------------------------------
# Failure handling — user message rolled back so retries don't double up
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_send_rolls_back_pending_user_message() -> None:
    fake = FakeLLMClient(
        [ScriptedResponse(raise_error=LLMError("boom"))]
    )
    conv = LLMConversation(system="sys", client=fake)
    with pytest.raises(LLMError):
        await conv.send("will fail")

    # System prompt remains; failed user turn was rolled back.
    assert [m.role for m in conv.messages] == ["system"]
    assert conv.turns == []


# ---------------------------------------------------------------------------
# Streaming send
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_stream_forwards_tokens_and_records_turn() -> None:
    fake = FakeLLMClient([ScriptedResponse(text="alpha beta gamma")])
    conv = LLMConversation(client=fake)

    received: list[str] = []

    async def collect(token: str) -> None:
        received.append(token)

    response = await conv.send_stream("go", on_token=collect, tier="nano")
    assert response.text == "alpha beta gamma"
    assert "".join(received).strip() == "alpha beta gamma"
    assert conv.turns[0].tier == "nano"


# ---------------------------------------------------------------------------
# Compaction — opt-in only, never auto-triggered
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compact_head_tail_drops_middle_messages() -> None:
    fake = FakeLLMClient([ScriptedResponse(text="r")] * 6)
    conv = LLMConversation(system="sys", client=fake)
    for i in range(6):
        await conv.send(f"turn {i}")
    # 1 system + 6 user + 6 assistant = 13 messages
    assert len(conv.messages) == 13

    await conv.compact(strategy="head_tail", keep_last_n=4)

    # 1 system + last 4 messages
    assert len(conv.messages) == 5
    assert conv.messages[0].role == "system"
    # Tail preserves the last user/assistant pairs verbatim.
    assert conv.messages[-1].role == "assistant"
    assert conv.messages[-2].role == "user"


@pytest.mark.asyncio
async def test_compact_summarize_replaces_middle_with_system_summary() -> None:
    main_responses = [ScriptedResponse(text="r") for _ in range(4)]
    summary_response = ScriptedResponse(text="- bullet 1\n- bullet 2", cost_usd=0.0001)
    fake = FakeLLMClient(main_responses + [summary_response])

    conv = LLMConversation(system="sys", client=fake)
    for i in range(4):
        await conv.send(f"turn {i}")

    await conv.compact(strategy="summarize", keep_last_n=2, summary_tier="nano")

    # 1 system + 1 summary + last 2 messages
    assert len(conv.messages) == 4
    assert conv.messages[0].role == "system"
    assert conv.messages[1].role == "system"
    assert conv.messages[1].content.startswith("[earlier-context-summary]")
    assert "bullet 1" in conv.messages[1].content
    # Summary call used nano tier with cache disabled.
    summary_call = fake.calls[-1]
    assert summary_call.tier == "nano"
    assert summary_call.cache_policy == "none"


@pytest.mark.asyncio
async def test_compact_noop_when_history_already_short() -> None:
    fake = FakeLLMClient([ScriptedResponse(text="r")])
    conv = LLMConversation(system="sys", client=fake)
    await conv.send("just one")

    await conv.compact(strategy="head_tail", keep_last_n=4)
    assert len(conv.messages) == 3  # untouched


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_to_dict_from_dict_round_trip_preserves_history() -> None:
    fake = FakeLLMClient([ScriptedResponse(text="hello", model="m", provider="p")])
    conv = LLMConversation(
        system="sys",
        client=fake,
        default_tier="small",
        trace_id="bid-123",
    )
    await conv.send("hi", tier="nano")

    snapshot = conv.to_dict()
    revived = LLMConversation.from_dict(snapshot, client=fake)

    assert revived.system == "sys"
    assert revived.default_tier == "small"
    assert revived.trace_id == "bid-123"
    assert [m.content for m in revived.messages] == [m.content for m in conv.messages]
    assert len(revived.turns) == 1
    assert revived.turns[0].tier == "nano"


# ---------------------------------------------------------------------------
# Trace propagation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trace_id_is_propagated_into_each_request() -> None:
    fake = FakeLLMClient([ScriptedResponse(text="r")] * 2)
    conv = LLMConversation(client=fake, trace_id="bid-xyz")
    await conv.send("a")
    await conv.send("b")

    assert all(c.trace_id == "bid-xyz" for c in fake.calls)


# ---------------------------------------------------------------------------
# Sanity: imported LLMMessage is the same class throughout
# ---------------------------------------------------------------------------


def test_messages_are_llm_message_instances() -> None:
    conv = LLMConversation(system="sys", client=FakeLLMClient())
    assert isinstance(conv.messages[0], LLMMessage)


# ---------------------------------------------------------------------------
# Concurrency — lock prevents user/assistant message scrambling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_sends_do_not_scramble_message_order() -> None:
    """Without the lock, two concurrent ``send`` calls would interleave
    user/assistant messages (u1, u2, a1, a2 instead of u1, a1, u2, a2).
    The :attr:`_lock` serialises them so each turn's user message is
    immediately followed by its own assistant reply."""
    import asyncio

    fake = FakeLLMClient(
        [
            ScriptedResponse(text="reply-1", model="m", provider="p"),
            ScriptedResponse(text="reply-2", model="m", provider="p"),
        ]
    )
    conv = LLMConversation(system="sys", client=fake)

    await asyncio.gather(
        conv.send("first"),
        conv.send("second"),
    )

    # Strict alternation: system, user, assistant, user, assistant.
    roles = [m.role for m in conv.messages]
    assert roles == ["system", "user", "assistant", "user", "assistant"]
    # Whichever turn won the lock first, its user msg is paired with the
    # next assistant — no cross-pairing.
    pairs = list(zip(conv.messages[1::2], conv.messages[2::2]))
    assert all(u.role == "user" and a.role == "assistant" for u, a in pairs)


@pytest.mark.asyncio
async def test_compact_does_not_race_with_in_flight_send() -> None:
    """When ``compact`` is called concurrently with ``send``, the lock
    ensures compact waits for the send to finish (or vice versa) — the
    compact never sees a half-written history (user without assistant)."""
    import asyncio

    # Slow generate so compact is forced to wait on the lock.
    started = asyncio.Event()
    release = asyncio.Event()

    class _SlowClient(FakeLLMClient):
        async def generate(self, request):  # type: ignore[override]
            started.set()
            await release.wait()
            return await super().generate(request)

    slow = _SlowClient(
        [ScriptedResponse(text="r")] * 6
    )
    conv = LLMConversation(system="sys", client=slow)
    # Pre-fill some history so compact has something to drop.
    for _ in range(4):
        # Fast path — let each send complete before the next.
        release.set()
        await conv.send("x")
        release.clear()
    assert len(conv.messages) == 9  # 1 system + 4*(user+assistant)

    # Now race: send + compact concurrently.
    send_task = asyncio.create_task(conv.send("blocking"))
    await started.wait()  # send is mid-flight, holds the lock
    compact_task = asyncio.create_task(
        conv.compact(strategy="head_tail", keep_last_n=2)
    )
    # compact_task is queued behind the lock; release send.
    release.set()
    await asyncio.gather(send_task, compact_task)

    # Final state: compact ran AFTER send completed → strict alternation
    # remains; no orphan user message.
    roles = [m.role for m in conv.messages]
    assert roles[0] == "system"
    for prev, curr in zip(roles[1:], roles[2:]):
        # No two user-in-a-row, no two assistant-in-a-row.
        assert not (prev == "user" and curr == "user")
        assert not (prev == "assistant" and curr == "assistant")


# ---------------------------------------------------------------------------
# Pydantic validator integrity — tier set via alias still validates
# ---------------------------------------------------------------------------


def test_role_alias_assigns_through_pydantic_not_dict_hack() -> None:
    """Regression: previously the validator wrote into ``__dict__`` to
    bypass re-validation. Now it assigns ``self.tier = mapped`` directly;
    this test asserts the model's reported field-set treats the result
    consistently (tier appears as set, value is a valid LLMTier)."""
    from tools.llm.types import LLMRequest, LLMMessage

    req = LLMRequest(messages=[LLMMessage(role="user", content="x")], role="extraction")
    assert req.tier == "nano"
    # Round-trip through model_dump preserves the aliased tier.
    assert req.model_dump()["tier"] == "nano"
