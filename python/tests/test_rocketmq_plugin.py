"""Tests for processors.rocketmq — BaseRocketMQPlugin, client manager, auto-registration."""

import json
from unittest.mock import MagicMock, patch

import pytest

from processors.base import (
    PostProcessor,
    PreProcessor,
    ProcessorError,
    _POST_PROCESSOR_REGISTRY,
    _PRE_PROCESSOR_REGISTRY,
)
from processors.rocketmq import (
    BaseRocketMQPlugin,
    RocketMQConnectionError,
    _ROCKETMQ_PLUGIN_REGISTRY,
    _RocketMQManager,
)


_CFG = {
    "processor_configs": {
        "rocketmq-order": {
            "namesrv_addr": "localhost:9876",
            "group_id": "test-producer-group",
        }
    }
}


@pytest.fixture(autouse=True)
def _clean_registries():
    """清理所有注册表，确保测试隔离。Clean all registries for test isolation."""
    _PRE_PROCESSOR_REGISTRY.clear()
    _POST_PROCESSOR_REGISTRY.clear()
    _ROCKETMQ_PLUGIN_REGISTRY.clear()
    _RocketMQManager._clients.clear()
    yield
    _PRE_PROCESSOR_REGISTRY.clear()
    _POST_PROCESSOR_REGISTRY.clear()
    _ROCKETMQ_PLUGIN_REGISTRY.clear()
    _RocketMQManager._clients.clear()


class TestBaseRocketMQPluginRegistration:
    """验证 BaseRocketMQPlugin 子类的自动注册。"""

    def test_registers_in_rocketmq_plugin_registry(self):
        class MyPlugin(BaseRocketMQPlugin):
            name = "my-rmq-plugin"

        assert "my-rmq-plugin" in _ROCKETMQ_PLUGIN_REGISTRY

    def test_auto_creates_pre_processor_wrapper(self):
        class MyPlugin(BaseRocketMQPlugin):
            name = "rmq-pre-test"

        assert "rmq-pre-test" in _PRE_PROCESSOR_REGISTRY
        assert issubclass(_PRE_PROCESSOR_REGISTRY["rmq-pre-test"], PreProcessor)

    def test_auto_creates_post_processor_wrapper(self):
        class MyPlugin(BaseRocketMQPlugin):
            name = "rmq-post-test"

        assert "rmq-post-test" in _POST_PROCESSOR_REGISTRY
        assert issubclass(_POST_PROCESSOR_REGISTRY["rmq-post-test"], PostProcessor)

    def test_raises_type_error_when_name_missing(self):
        with pytest.raises(TypeError, match="must define a 'name'"):
            class BadPlugin(BaseRocketMQPlugin):  # noqa: F841
                pass


class TestWrapperDelegation:
    """验证 Pre/PostProcessor 包装器正确委托到 BaseRocketMQPlugin。"""

    def test_pre_wrapper_delegates_to_before_request(self):
        class MyPlugin(BaseRocketMQPlugin):
            name = "rmq-delegate-pre"

            def before_request(self, headers, body, case_config, global_config):
                body["rmq_injected"] = True
                return headers, body

        pre_cls = _PRE_PROCESSOR_REGISTRY["rmq-delegate-pre"]
        instance = pre_cls()
        h, b = instance.process({}, {"key": "val"}, {}, {"processor_configs": {}})
        assert b["rmq_injected"] is True

    def test_post_wrapper_delegates_to_after_response(self):
        call_log = {}

        class MyPlugin(BaseRocketMQPlugin):
            name = "rmq-delegate-post"

            def after_response(self, rh, rb, rsh, rsb, cc, gc):
                call_log["resp"] = rsb

        post_cls = _POST_PROCESSOR_REGISTRY["rmq-delegate-post"]
        instance = post_cls()
        instance.process({}, {}, {}, {"data": "ok"}, {}, {"processor_configs": {}})
        assert call_log["resp"] == {"data": "ok"}


class TestRocketMQManager:
    """验证客户端按 namesrv_addr 缓存。"""

    def test_caches_client_by_namesrv_addr(self):
        with patch("processors.rocketmq.RocketMQClient") as mock_cls:
            mock_cls.side_effect = [MagicMock(), MagicMock()]
            c1 = _RocketMQManager.get_client("localhost:9876")
            c2 = _RocketMQManager.get_client("localhost:9876")
            c3 = _RocketMQManager.get_client("localhost:9877")

        assert c1 is c2
        assert c1 is not c3
        assert mock_cls.call_count == 2


class TestBaseRocketMQPluginConfig:
    """验证配置读取与错误处理。"""

    def test_missing_processor_configs_raises(self):
        class Plugin(BaseRocketMQPlugin):
            name = "rmq-missing-cfg"

        with pytest.raises(RocketMQConnectionError, match="global_config"):
            Plugin()._get_client({"processor_configs": None})

    def test_missing_namesrv_raises(self):
        class Plugin(BaseRocketMQPlugin):
            name = "rmq-no-namesrv"

        with pytest.raises(RocketMQConnectionError, match="namesrv"):
            Plugin()._get_client({"processor_configs": {"rmq-no-namesrv": {"group_id": "g"}}})

    def test_missing_group_raises(self):
        class Plugin(BaseRocketMQPlugin):
            name = "rmq-no-group"

        with pytest.raises(RocketMQConnectionError, match="group"):
            Plugin()._get_group({"processor_configs": {"rmq-no-group": {"namesrv_addr": "h:9876"}}})


class TestSendAndReceive:
    """验证 _send_message / _receive_message 委托给纯 Python 客户端。"""

    def test_send_message_uses_client_and_returns_meta(self):
        class Plugin(BaseRocketMQPlugin):
            name = "rocketmq-order"

        plugin = Plugin()
        fake_client = MagicMock()
        fake_client.send_message.return_value = {
            "broker_addr": "192.168.1.157:10911",
            "queue_id": 0,
            "queue_offset": 1,
            "msg_id": "M",
        }
        with patch.object(BaseRocketMQPlugin, "_get_client", return_value=fake_client):
            meta = plugin._send_message(
                "order-topic", {"event": "order_created"}, tag="order_create",
                key="rocketmq-order", global_config=_CFG,
            )

        fake_client.send_message.assert_called_once()
        _, kwargs = fake_client.send_message.call_args
        assert kwargs["topic"] == "order-topic"
        assert kwargs["tags"] == "order_create"
        assert kwargs["keys"] == "rocketmq-order"
        assert kwargs["group"] == "test-producer-group"
        assert json.loads(kwargs["body"].decode("utf-8")) == {"event": "order_created"}
        assert meta["queue_offset"] == 1

    def test_receive_message_uses_dedicated_verify_group(self):
        class Plugin(BaseRocketMQPlugin):
            name = "rocketmq-order"

        plugin = Plugin()
        fake_client = MagicMock()
        fake_client.receive_message.return_value = []
        with patch.object(BaseRocketMQPlugin, "_get_client", return_value=fake_client):
            plugin._receive_message(
                "order-topic", 0, 5, broker_addr="192.168.1.157:10911",
                tag="order_create", global_config=_CFG,
            )

        _, kwargs = fake_client.receive_message.call_args
        assert kwargs["group"] == "test-producer-group-verify"
        assert kwargs["queue_id"] == 0
        assert kwargs["offset"] == 5
        assert kwargs["tags"] == "order_create"

    def test_send_message_requires_global_config(self):
        class Plugin(BaseRocketMQPlugin):
            name = "rocketmq-order"

        with pytest.raises(ProcessorError, match="global_config"):
            Plugin()._send_message("t", {"a": 1})


class TestRocketMQOrderPlugin:
    """验证内置 rocketmq-order 插件的前置发送与后置消费校验。"""

    def test_before_request_sends_and_injects_metadata(self):
        from processors.builtin.rocketmq.order_message import RocketMQOrderPlugin

        plugin = RocketMQOrderPlugin()
        meta = {"broker_addr": "192.168.1.157:10911", "queue_id": 0, "queue_offset": 1, "msg_id": "M"}
        with patch.object(RocketMQOrderPlugin, "_send_message", return_value=meta) as mock_send:
            headers, body = plugin.before_request(
                {"Content-Type": "application/json"}, {"username": "admin"}, {}, _CFG,
            )

        mock_send.assert_called_once()
        assert body["_rocketmq_queue_id"] == 0
        assert body["_rocketmq_offset"] == 1
        assert body["_rocketmq_broker"] == "192.168.1.157:10911"
        assert body["username"] == "admin"
        assert headers == {"Content-Type": "application/json"}

    def test_after_response_verifies_matching_message(self, capsys):
        from processors.builtin.rocketmq.order_message import RocketMQOrderPlugin

        plugin = RocketMQOrderPlugin()
        body = {
            "username": "admin",
            "_rocketmq_queue_id": 0,
            "_rocketmq_offset": 1,
            "_rocketmq_broker": "192.168.1.157:10911",
        }
        payload = json.dumps({"event": "order_created", "data": {"username": "admin"}}).encode("utf-8")
        msgs = [{"body": payload}]
        with patch.object(RocketMQOrderPlugin, "_receive_message", return_value=msgs) as mock_recv:
            plugin.after_response({}, body, {}, {}, {}, _CFG)

        mock_recv.assert_called_once()
        out = capsys.readouterr().out
        assert ("queue_id" in out) or ("received" in out)

    def test_after_response_raises_on_timeout(self):
        from processors.builtin.rocketmq.order_message import RocketMQOrderPlugin

        plugin = RocketMQOrderPlugin()
        body = {"username": "admin", "_rocketmq_queue_id": 0, "_rocketmq_offset": 1, "_rocketmq_broker": "h:10911"}
        with patch.object(RocketMQOrderPlugin, "_receive_message", return_value=None):
            with pytest.raises(ProcessorError, match="receive_timeout|未收到消息|No message received"):
                plugin.after_response({}, body, {}, {}, {}, _CFG)

    def test_after_response_raises_on_mismatch(self):
        from processors.builtin.rocketmq.order_message import RocketMQOrderPlugin

        plugin = RocketMQOrderPlugin()
        body = {"username": "admin", "_rocketmq_queue_id": 0, "_rocketmq_offset": 1, "_rocketmq_broker": "h:10911"}
        payload = json.dumps({"event": "order_created", "data": {"username": "other"}}).encode("utf-8")
        with patch.object(RocketMQOrderPlugin, "_receive_message", return_value=[{"body": payload}]):
            with pytest.raises(ProcessorError, match="receive_mismatch|不一致|does not match"):
                plugin.after_response({}, body, {}, {}, {}, _CFG)

    def test_after_response_skips_when_metadata_missing(self):
        from processors.builtin.rocketmq.order_message import RocketMQOrderPlugin

        plugin = RocketMQOrderPlugin()
        with patch.object(RocketMQOrderPlugin, "_receive_message") as mock_recv:
            plugin.after_response({}, {"username": "admin"}, {}, {}, {}, _CFG)
        mock_recv.assert_not_called()
