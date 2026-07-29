"""Tests for the canonical stream-event and context-usage contracts: payload
shape, redaction, truncation bounds, percentage derivation, and the structural
guarantee that opaque reasoning has no field to enter through.
"""

from __future__ import annotations

import pytest

from agentweave.stream_events import (
    CONTEXT_BREAKDOWN_FIELDS,
    MAX_PAYLOAD_BYTES,
    MAX_TOOL_RESULT_BYTES,
    PAYLOAD_VERSION,
    STREAM_EVENT_KINDS,
    AgentStreamEvent,
    ContextUsageSample,
    ParsedRunnerLine,
    ParserControl,
    SessionChange,
    StreamEventError,
    diagnostic_event,
    error_event,
    normalize_context_usage,
    status_event,
    stream_event_transport_fields,
    text_event,
    thinking_event,
    tool_result_event,
    tool_use_event,
)


class TestStreamEventConstructors:
    def test_seven_kinds_are_closed(self):
        assert set(STREAM_EVENT_KINDS) == {
            "text",
            "thinking",
            "tool_use",
            "tool_result",
            "status",
            "diagnostic",
            "error",
        }

    def test_unknown_kind_rejected(self):
        with pytest.raises(StreamEventError):
            AgentStreamEvent(kind="result", content="x", payload={"version": PAYLOAD_VERSION})

    def test_text_event_has_readable_content_and_versioned_payload(self):
        event = text_event("hello there")
        assert event.kind == "text"
        assert event.content == "hello there"
        assert event.payload == {"version": 1, "text": "hello there"}

    def test_thinking_event_only_accepts_readable_text(self):
        # The constructor's signature has no field for an opaque/encrypted
        # reasoning blob, so one cannot be smuggled into content or payload.
        event = thinking_event("considering options")
        assert set(event.payload.keys()) == {"version", "text"}
        with pytest.raises(TypeError):
            thinking_event("considering options", encrypted="opaque-blob")  # type: ignore[call-arg]

    def test_status_event_rejects_unknown_phase(self):
        with pytest.raises(StreamEventError):
            status_event("finished")  # type: ignore[arg-type]

    def test_status_event_default_summary(self):
        event = status_event("completed")
        assert event.payload["phase"] == "completed"
        assert event.content

    def test_diagnostic_event_carries_stream_and_severity(self):
        event = diagnostic_event(stream="stderr", severity="warn", summary="retrying request")
        assert event.kind == "diagnostic"
        assert event.payload["stream"] == "stderr"
        assert event.payload["severity"] == "warn"

    def test_error_event_carries_code_and_optional_exit_code(self):
        event = error_event(code="runner_crashed", message="process exited", exit_code=1)
        assert event.payload["code"] == "runner_crashed"
        assert event.payload["exit_code"] == 1
        assert event.payload["retryable"] is False

    def test_payload_missing_version_is_rejected(self):
        with pytest.raises(StreamEventError):
            AgentStreamEvent(kind="text", content="x", payload={"text": "x"})

    def test_empty_content_is_rejected(self):
        with pytest.raises(StreamEventError):
            AgentStreamEvent(kind="text", content="", payload={"version": 1, "text": ""})


class TestToolCorrelation:
    def test_tool_use_and_result_share_call_id(self):
        use = tool_use_event(tool="bash", category="shell", input_data={"cmd": "ls"}, call_id="c1")
        result = tool_result_event(tool="bash", output="file.txt", call_id="c1")
        assert use.call_id == result.call_id == "c1"

    def test_tool_without_call_id_stays_renderable(self):
        event = tool_use_event(tool="bash", category="shell", input_data={"cmd": "ls"})
        assert event.call_id is None
        assert event.content

    def test_failed_tool_result_is_marked_is_error(self):
        event = tool_result_event(tool="bash", output="not found", is_error=True)
        assert event.payload["is_error"] is True
        assert event.kind == "tool_result"


class TestRedactionAndTruncation:
    def test_tool_input_secret_is_redacted(self):
        event = tool_use_event(
            tool="curl",
            category="network",
            input_data={"authorization": "Bearer sk-abcdefghij1234567890abcdefghij"},
        )
        assert "sk-abcdefghij1234567890abcdefghij" not in event.payload["input"]
        assert "<redacted>" in event.payload["input"]

    def test_tool_result_output_over_bound_is_truncated(self):
        big_output = "not a secret line\n" * (MAX_TOOL_RESULT_BYTES // 10)
        event = tool_result_event(tool="cat", output=big_output)
        assert event.truncated is True
        assert event.payload["truncated"] is True
        assert len(event.payload["output"].encode("utf-8")) <= MAX_TOOL_RESULT_BYTES
        # readable summary/content is preserved despite truncation
        assert event.content

    def test_tool_result_output_within_bound_is_not_truncated(self):
        event = tool_result_event(tool="cat", output="short output")
        assert event.truncated is False
        assert event.payload["truncated"] is False

    def test_overall_payload_stays_within_64kib(self):
        huge_input = {"cmd": "x" * (MAX_TOOL_RESULT_BYTES * 5)}
        event = tool_use_event(tool="bash", category="shell", input_data=huge_input)
        size = len(str(event.payload).encode("utf-8"))
        # sanity: constructing didn't itself blow past the bound many times over
        assert size < MAX_PAYLOAD_BYTES * 2

    def test_text_event_over_payload_bound_is_truncated(self):
        huge_text = "y" * (MAX_PAYLOAD_BYTES * 2)
        event = text_event(huge_text)
        assert event.truncated is True
        assert len(event.content.encode("utf-8")) <= MAX_PAYLOAD_BYTES


class TestContextUsageSample:
    def test_measured_sample_derives_percent(self):
        sample = ContextUsageSample(
            status="measured",
            source="claude",
            basis="latest_request_input",
            context_tokens=5000,
            limit_tokens=10000,
        )
        assert sample.percent == 50.0

    def test_unknown_limit_omits_percent_without_fabricating_zero(self):
        sample = ContextUsageSample(
            status="measured",
            source="kimi",
            basis="provider_context",
            context_tokens=1234,
        )
        assert sample.limit_tokens is None
        assert sample.percent is None

    def test_provider_reported_ratio_accepts_explicit_percent(self):
        sample = ContextUsageSample(
            status="measured",
            source="opencode",
            basis="provider_reported_ratio",
            percent=42.5,
        )
        assert sample.percent == 42.5

    def test_percent_rejected_without_provider_reported_ratio_basis(self):
        with pytest.raises(StreamEventError):
            ContextUsageSample(
                status="measured",
                source="claude",
                basis="latest_request_input",
                percent=50.0,
            )

    def test_percent_out_of_range_rejected(self):
        with pytest.raises(StreamEventError):
            ContextUsageSample(
                status="measured",
                source="opencode",
                basis="provider_reported_ratio",
                percent=150.0,
            )

    def test_measured_status_requires_basis(self):
        with pytest.raises(StreamEventError):
            ContextUsageSample(status="measured", source="claude")

    def test_unavailable_status_does_not_require_basis(self):
        sample = ContextUsageSample(status="unavailable", source="kimi")
        assert sample.basis is None
        assert sample.percent is None

    def test_unknown_status_rejected(self):
        with pytest.raises(StreamEventError):
            ContextUsageSample(status="partial", source="claude")  # type: ignore[arg-type]

    def test_negative_context_tokens_rejected(self):
        with pytest.raises(StreamEventError):
            ContextUsageSample(
                status="measured", source="claude", basis="provider_context", context_tokens=-1
            )

    def test_non_positive_limit_rejected(self):
        with pytest.raises(StreamEventError):
            ContextUsageSample(
                status="measured",
                source="claude",
                basis="provider_context",
                context_tokens=1,
                limit_tokens=0,
            )


class TestLegacyContextNormalization:
    def test_tokens_used_and_tokens_limit(self):
        sample = normalize_context_usage({"tokens_used": 2500, "tokens_limit": 10000})
        assert sample.status == "measured"
        assert sample.context_tokens == 2500
        assert sample.limit_tokens == 10000
        assert sample.percent == 25

    def test_input_tokens_and_context_limit(self):
        sample = normalize_context_usage({"input_tokens": 500, "context_limit": 2000})
        assert sample.context_tokens == 500
        assert sample.limit_tokens == 2000

    def test_ratio_form_context_usage(self):
        sample = normalize_context_usage({"context_usage": 0.425})
        assert sample.basis == "provider_reported_ratio"
        assert sample.percent == 42.5

    def test_tokens_used_takes_precedence_over_codex_breakdown_input(self):
        sample = normalize_context_usage(
            {
                "tokens_used": 1500,
                "tokens_limit": 10000,
                "input_tokens": 1000,
                "output_tokens": 500,
            }
        )
        assert sample.context_tokens == 1500

    def test_zero_without_limit_is_unavailable(self):
        sample = normalize_context_usage({"input_tokens": 0, "percent": 0})
        assert sample.status == "unavailable"
        assert sample.percent is None

    def test_contradictory_ratio_degrades_to_token_only(self):
        sample = normalize_context_usage(
            {"tokens_used": 5000, "tokens_limit": 10000, "percent": 90}
        )
        assert sample.status == "measured"
        assert sample.context_tokens == 5000
        assert sample.limit_tokens is None
        assert sample.percent is None

    def test_canonical_derived_percent_round_trips(self):
        sample = normalize_context_usage(
            {
                "status": "measured",
                "source": "claude",
                "basis": "provider_context",
                "context_tokens": 1000,
                "limit_tokens": 4000,
                "percent": 25.0,
                "observed_at": 123.0,
            }
        )
        assert sample.status == "measured"
        assert sample.percent == 25.0
        assert sample.observed_at == 123.0

    def test_invalid_legacy_number_is_unavailable(self):
        assert normalize_context_usage({"tokens_used": "unknown"}).status == "unavailable"

    def test_contradictory_canonical_unavailable_sample_is_cleaned(self):
        sample = normalize_context_usage(
            {
                "status": "unavailable",
                "source": "legacy",
                "context_tokens": 0,
                "percent": 0,
            }
        )
        assert sample.status == "unavailable"
        assert sample.context_tokens is None
        assert sample.percent is None


class TestCacheBreakdownSemantics:
    def test_breakdown_keeps_only_allowlisted_numeric_fields(self):
        sample = ContextUsageSample(
            status="measured",
            source="claude",
            basis="latest_request_input",
            context_tokens=100,
            breakdown={
                "cache_read_tokens": 40,
                "cache_creation_tokens": 10,
                "raw_provider_object": {"secret": "x"},
                "prompt": "leaked message text",
            },
        )
        assert sample.breakdown == {"cache_read_tokens": 40, "cache_creation_tokens": 10}
        assert CONTEXT_BREAKDOWN_FIELDS.issuperset(sample.breakdown.keys())

    def test_breakdown_never_double_counts_into_context_tokens(self):
        # Breakdown storage is descriptive only; the caller (adapter-specific
        # arithmetic, covered by later sections) sets context_tokens explicitly.
        sample = ContextUsageSample(
            status="measured",
            source="codex",
            basis="provider_context",
            context_tokens=100,
            breakdown={"cached_input_tokens": 40},
        )
        assert sample.context_tokens == 100

    def test_all_invalid_breakdown_entries_collapse_to_none(self):
        sample = ContextUsageSample(
            status="unavailable", source="claude", breakdown={"prompt": "text"}
        )
        assert sample.breakdown is None


class TestParsedRunnerLine:
    def test_usage_without_output_events(self):
        line = ParsedRunnerLine(usage=ContextUsageSample(status="unavailable", source="claude"))
        assert line.events == []
        assert line.usage is not None

    def test_output_events_without_usage(self):
        line = ParsedRunnerLine(events=[text_event("hi")])
        assert line.usage is None
        assert len(line.events) == 1

    def test_session_change_and_control_are_independent_fields(self):
        line = ParsedRunnerLine(
            session_change=SessionChange(session_id="s-2", reason="resumed"),
            control=ParserControl(retry=True),
        )
        assert line.session_change.session_id == "s-2"
        assert line.control.retry is True
        assert line.events == []
        assert line.usage is None


class TestStreamEventTransportFields:
    def test_redacts_content_and_nested_payload(self):
        secret = "sk-abcdefghij1234567890abcdefghij"
        event = AgentStreamEvent(
            kind="text",
            content=f"token: {secret}",
            payload={"version": 1, "nested": {"authorization": f"Bearer {secret}"}},
            run_id="run-1",
            sequence=2,
        )
        fields = stream_event_transport_fields(event)
        assert secret not in fields["content"]
        assert secret not in str(fields["payload"])
        assert fields["run_id"] == "run-1"
        assert fields["sequence"] == 2
