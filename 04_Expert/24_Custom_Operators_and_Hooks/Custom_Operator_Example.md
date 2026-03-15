# 24 — Custom Operators and Hooks: Custom Operator Example

## SlackNotificationOperator

A production-quality Slack notification operator with a dedicated `SlackHook`, `template_fields`, retry logic, and full unit test suite.

## 📂 Navigation
⬅️ **Prev:** | 🏠 **[Home](../../00_Learning_Guide/Learning_Path.md)** | ➡️ **Next:**

---

## SlackHook

```python
# hooks/slack_hook.py
"""
Hook for the Slack Web API.

Connection setup in Airflow UI:
    Conn ID:   slack_default
    Conn Type: HTTP
    Host:      https://slack.com
    Password:  xoxb-your-bot-token   (Bot User OAuth Token)

Or via environment variable:
    AIRFLOW_CONN_SLACK_DEFAULT='{"conn_type": "http", "host": "https://slack.com", "password": "xoxb-..."}'
"""
from __future__ import annotations

import json
import logging

import requests

from airflow.hooks.base import BaseHook
from airflow.exceptions import AirflowException

log = logging.getLogger(__name__)


class SlackHook(BaseHook):
    """
    Hook to interact with the Slack Web API.

    Uses the chat.postMessage endpoint to send messages.
    Reads the Bot User OAuth Token from the Airflow connection password field.
    """

    conn_name_attr = "slack_conn_id"
    default_conn_name = "slack_default"
    conn_type = "slack"
    hook_name = "Slack"

    # Slack API base URL
    BASE_URL = "https://slack.com/api"

    def __init__(self, slack_conn_id: str = default_conn_name) -> None:
        super().__init__()
        self.slack_conn_id = slack_conn_id
        self._token: str | None = None
        self._session: requests.Session | None = None

    def get_conn(self) -> requests.Session:
        """
        Returns a requests.Session pre-configured with the Slack Bot token.
        Session is cached — subsequent calls return the same object.
        """
        if self._session is None:
            conn = self.get_connection(self.slack_conn_id)
            if not conn.password:
                raise AirflowException(
                    f"Slack connection '{self.slack_conn_id}' has no token in the password field."
                )
            self._token = conn.password
            self._session = requests.Session()
            self._session.headers.update({
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json; charset=utf-8",
            })
        return self._session

    def post_message(
        self,
        channel: str,
        text: str,
        blocks: list[dict] | None = None,
        thread_ts: str | None = None,
        mrkdwn: bool = True,
    ) -> dict:
        """
        Send a message to a Slack channel.

        Args:
            channel:   Channel ID or name (e.g., "#alerts" or "C1234567890")
            text:      Message text (fallback for blocks, shown in notifications)
            blocks:    Optional Block Kit blocks list for rich formatting
            thread_ts: If set, posts as a reply to this thread timestamp
            mrkdwn:    Whether to parse Slack markdown

        Returns:
            Slack API response dict with 'ts' (message timestamp) on success

        Raises:
            AirflowException: If the Slack API returns an error
        """
        session = self.get_conn()
        payload: dict = {
            "channel": channel,
            "text": text,
            "mrkdwn": mrkdwn,
        }
        if blocks:
            payload["blocks"] = blocks
        if thread_ts:
            payload["thread_ts"] = thread_ts

        log.info("Posting Slack message to channel: %s", channel)
        response = session.post(
            f"{self.BASE_URL}/chat.postMessage",
            data=json.dumps(payload),
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()
        if not data.get("ok"):
            error = data.get("error", "unknown_error")
            raise AirflowException(
                f"Slack API error: {error}. Channel: {channel}. "
                f"Response: {json.dumps(data)}"
            )

        log.info("Message posted. Channel: %s, ts: %s", channel, data.get("ts"))
        return data

    def test_connection(self) -> tuple[bool, str]:
        """
        Test the connection by calling auth.test.
        Used by the Airflow UI "Test Connection" button.
        """
        try:
            session = self.get_conn()
            response = session.post(f"{self.BASE_URL}/auth.test", timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get("ok"):
                return True, f"Connected as {data.get('user')} in workspace {data.get('team')}"
            return False, f"Slack API error: {data.get('error')}"
        except Exception as e:
            return False, str(e)
```

---

## SlackNotificationOperator

```python
# operators/slack_notification_operator.py
"""
Operator that sends a Slack message with full template support.

Example usage in a DAG:

    from operators.slack_notification_operator import SlackNotificationOperator

    notify = SlackNotificationOperator(
        task_id="notify_team",
        channel="#data-alerts",
        message="Pipeline *{{ dag.dag_id }}* completed on {{ ds }}. "
                "Processed {{ ti.xcom_pull('count_task') }} rows.",
        slack_conn_id="slack_default",
        retries=3,
        retry_delay=timedelta(seconds=10),
    )

    # As a failure callback (static method pattern):
    def task_failure_callback(context):
        SlackNotificationOperator(
            task_id="slack_failure",
            channel="#data-alerts",
            message=f"FAILED: {context['dag'].dag_id}.{context['task'].task_id}",
        ).execute(context)
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from airflow.exceptions import AirflowException
from airflow.models import BaseOperator
from airflow.utils.context import Context

from hooks.slack_hook import SlackHook


class SlackNotificationOperator(BaseOperator):
    """
    Sends a message to a Slack channel via the Slack Web API.

    Supports Jinja templating for message, channel, username, and icon_emoji.
    Implements retry logic for transient Slack API errors (rate limits, timeouts).

    :param channel:        Slack channel (e.g., "#alerts" or "C1234567890"). Templatable.
    :param message:        Message text. Supports Slack markdown and Jinja templates.
    :param blocks:         Optional Block Kit blocks for rich formatting. Templatable.
    :param username:       Bot display name override. Templatable.
    :param icon_emoji:     Emoji for bot avatar (e.g., ":robot_face:"). Templatable.
    :param slack_conn_id:  Airflow connection ID for the Slack token.
    :param thread_ts:      Reply to this thread timestamp (for threading). Templatable.
    """

    template_fields = ("channel", "message", "username", "icon_emoji", "thread_ts")
    template_fields_renderers = {"message": "jinja"}
    ui_color = "#4a154b"   # Slack brand purple
    ui_fgcolor = "#ffffff"

    def __init__(
        self,
        channel: str,
        message: str,
        blocks: list[dict] | None = None,
        username: str = "Airflow",
        icon_emoji: str = ":airflow:",
        slack_conn_id: str = SlackHook.default_conn_name,
        thread_ts: str | None = None,
        **kwargs,
    ) -> None:
        # Default retry settings for Slack (handle rate limiting gracefully)
        kwargs.setdefault("retries", 3)
        kwargs.setdefault("retry_delay", timedelta(seconds=30))
        kwargs.setdefault("retry_exponential_backoff", True)

        super().__init__(**kwargs)
        self.channel = channel
        self.message = message
        self.blocks = blocks
        self.username = username
        self.icon_emoji = icon_emoji
        self.slack_conn_id = slack_conn_id
        self.thread_ts = thread_ts

    def execute(self, context: Context) -> dict[str, Any]:
        """
        Send the Slack message.

        Returns:
            Slack API response dict containing 'ts' (message timestamp)
            and 'channel' fields, useful for threading.
        """
        hook = SlackHook(slack_conn_id=self.slack_conn_id)

        self.log.info(
            "Sending Slack notification to %s: %.100s%s",
            self.channel,
            self.message,
            "..." if len(self.message) > 100 else "",
        )

        try:
            response = hook.post_message(
                channel=self.channel,
                text=self.message,
                blocks=self.blocks,
                thread_ts=self.thread_ts,
            )
        except AirflowException:
            # Re-raise AirflowException so Airflow retry mechanism triggers
            raise
        except Exception as e:
            raise AirflowException(f"Unexpected error sending Slack message: {e}") from e

        self.log.info(
            "Slack message sent. ts=%s channel=%s",
            response.get("ts"),
            response.get("channel"),
        )
        return response
```

---

## Unit Tests

```python
# tests/test_slack_notification_operator.py
"""
Unit tests for SlackNotificationOperator and SlackHook.

Run with: pytest tests/test_slack_notification_operator.py -v
"""
from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
import requests

from airflow.exceptions import AirflowException
from airflow.models import Connection

from hooks.slack_hook import SlackHook
from operators.slack_notification_operator import SlackNotificationOperator


# ──────────────────────────────────────────────
# SlackHook Tests
# ──────────────────────────────────────────────

class TestSlackHook:

    @patch("hooks.slack_hook.BaseHook.get_connection")
    def test_get_conn_sets_authorization_header(self, mock_get_conn):
        """get_conn() creates a session with Bearer token header."""
        mock_get_conn.return_value = Connection(
            conn_id="slack_default",
            conn_type="slack",
            password="xoxb-test-token",
        )
        hook = SlackHook()
        session = hook.get_conn()
        assert session.headers["Authorization"] == "Bearer xoxb-test-token"

    @patch("hooks.slack_hook.BaseHook.get_connection")
    def test_get_conn_raises_if_no_token(self, mock_get_conn):
        """get_conn() raises AirflowException if password is missing."""
        mock_get_conn.return_value = Connection(
            conn_id="slack_default",
            conn_type="slack",
            password=None,
        )
        hook = SlackHook()
        with pytest.raises(AirflowException, match="no token"):
            hook.get_conn()

    @patch("hooks.slack_hook.BaseHook.get_connection")
    def test_post_message_success(self, mock_get_conn):
        """post_message() returns response dict on success."""
        mock_get_conn.return_value = Connection(password="xoxb-test")
        hook = SlackHook()

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True, "ts": "1234567890.123456", "channel": "C123"}
        mock_session.post.return_value = mock_response
        hook._session = mock_session
        hook._token = "xoxb-test"

        result = hook.post_message(channel="#test", text="Hello")
        assert result["ok"] is True
        assert result["ts"] == "1234567890.123456"

    @patch("hooks.slack_hook.BaseHook.get_connection")
    def test_post_message_api_error_raises(self, mock_get_conn):
        """post_message() raises AirflowException on API error response."""
        mock_get_conn.return_value = Connection(password="xoxb-test")
        hook = SlackHook()

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": False, "error": "channel_not_found"}
        mock_session.post.return_value = mock_response
        hook._session = mock_session
        hook._token = "xoxb-test"

        with pytest.raises(AirflowException, match="channel_not_found"):
            hook.post_message(channel="#nonexistent", text="Hello")


# ──────────────────────────────────────────────
# SlackNotificationOperator Tests
# ──────────────────────────────────────────────

class TestSlackNotificationOperator:

    def _make_operator(self, **kwargs) -> SlackNotificationOperator:
        defaults = {
            "task_id": "test_slack",
            "channel": "#test",
            "message": "Test message",
        }
        defaults.update(kwargs)
        return SlackNotificationOperator(**defaults)

    def test_template_fields_declared(self):
        """All parameterizable fields are in template_fields."""
        assert "channel" in SlackNotificationOperator.template_fields
        assert "message" in SlackNotificationOperator.template_fields
        assert "icon_emoji" in SlackNotificationOperator.template_fields
        assert "username" in SlackNotificationOperator.template_fields

    def test_default_retries_set(self):
        """Operator defaults to 3 retries and 30s delay."""
        op = self._make_operator()
        assert op.retries == 3
        assert op.retry_delay == timedelta(seconds=30)

    def test_caller_can_override_retries(self):
        """DAG author can override default retry settings."""
        op = self._make_operator(retries=1, retry_delay=timedelta(seconds=5))
        assert op.retries == 1
        assert op.retry_delay == timedelta(seconds=5)

    @patch("operators.slack_notification_operator.SlackHook")
    def test_execute_success_returns_response(self, MockSlackHook):
        """execute() returns the Slack API response dict."""
        mock_hook = MagicMock()
        mock_hook.post_message.return_value = {
            "ok": True,
            "ts": "9999.0001",
            "channel": "C123",
        }
        MockSlackHook.return_value = mock_hook

        op = self._make_operator()
        result = op.execute(context={})

        assert result["ts"] == "9999.0001"
        mock_hook.post_message.assert_called_once_with(
            channel="#test",
            text="Test message",
            blocks=None,
            thread_ts=None,
        )

    @patch("operators.slack_notification_operator.SlackHook")
    def test_execute_raises_airflow_exception_on_api_error(self, MockSlackHook):
        """execute() propagates AirflowException from hook."""
        mock_hook = MagicMock()
        mock_hook.post_message.side_effect = AirflowException("channel_not_found")
        MockSlackHook.return_value = mock_hook

        op = self._make_operator()
        with pytest.raises(AirflowException, match="channel_not_found"):
            op.execute(context={})

    @patch("operators.slack_notification_operator.SlackHook")
    def test_execute_wraps_unexpected_exception(self, MockSlackHook):
        """execute() wraps non-Airflow exceptions in AirflowException."""
        mock_hook = MagicMock()
        mock_hook.post_message.side_effect = ConnectionError("network unreachable")
        MockSlackHook.return_value = mock_hook

        op = self._make_operator()
        with pytest.raises(AirflowException, match="network unreachable"):
            op.execute(context={})

    @patch("operators.slack_notification_operator.SlackHook")
    def test_execute_passes_thread_ts(self, MockSlackHook):
        """thread_ts is forwarded to hook.post_message."""
        mock_hook = MagicMock()
        mock_hook.post_message.return_value = {"ok": True, "ts": "1.1"}
        MockSlackHook.return_value = mock_hook

        op = self._make_operator(thread_ts="1234567890.000100")
        op.execute(context={})

        _, kwargs = mock_hook.post_message.call_args
        assert kwargs["thread_ts"] == "1234567890.000100"
```

---

## DAG Usage Example

```python
# dags/pipeline_with_notifications.py
from datetime import datetime, timedelta

from airflow.sdk import DAG
from airflow.operators.python import PythonOperator

from operators.slack_notification_operator import SlackNotificationOperator


def _on_failure(context):
    """Reusable failure callback — sends Slack alert."""
    SlackNotificationOperator(
        task_id="failure_alert",
        channel="#data-oncall",
        message=(
            ":red_circle: *Task Failed*\n"
            f"DAG: `{context['dag'].dag_id}`\n"
            f"Task: `{context['task'].task_id}`\n"
            f"Run: `{context['run_id']}`\n"
            f"Execution: `{context['ds']}`"
        ),
        slack_conn_id="slack_default",
    ).execute(context)


with DAG(
    dag_id="pipeline_with_notifications",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
        "on_failure_callback": _on_failure,
    },
) as dag:

    process = PythonOperator(
        task_id="process_data",
        python_callable=lambda: print("processing..."),
    )

    notify_success = SlackNotificationOperator(
        task_id="notify_success",
        channel="#data-ops",
        # Jinja template resolved at runtime
        message=(
            ":white_check_mark: *Pipeline Complete*\n"
            "DAG: `{{ dag.dag_id }}`\n"
            "Execution date: `{{ ds }}`"
        ),
        trigger_rule="all_success",
    )

    process >> notify_success
```
