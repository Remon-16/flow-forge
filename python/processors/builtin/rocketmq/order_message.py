"""RocketMQ 订单消息处理器 — 前置发送订单事件，后置消费校验（跨平台）。
RocketMQ order message processor — pre-send order event, post-consume and verify
(cross-platform).

测试场景：微服务架构中，API 调用后通过 RocketMQ 通知下游服务。
前置发送测试消息模拟该行为，后置从队列消费并校验消息内容。

Test scenario: in microservice architecture, API calls notify downstream
services via RocketMQ. The pre-processor sends a test message to simulate this,
and the post-processor consumes and verifies the message content.

提示 / Tip: 可通过 LoginManager.get_current_user() 获取当前 #{} 登录用户的配置。
Use LoginManager.get_current_user() to access the currently logged-in user's config.

环境配置 / Env config (env-local.yml)::

    processor_configs:
      rocketmq-order:
        namesrv_addr: "localhost:9876"
        group_id: "test-producer-group"
        topic: "order-topic"
        tag: "order_create"
        receive_timeout: 10   # 可选：消费校验超时（秒）/ optional receive timeout (seconds)

用例 YAML / Test case YAML::

    preprocessors:
      - name: rocketmq-order
        config: {}
    postprocessors:
      - name: rocketmq-order
        config: {}
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from i18n import _
from processors.base import ProcessorError
from processors.rocketmq import BaseRocketMQPlugin

logger = logging.getLogger(__name__)

# 内部元数据键（下划线前缀，沿用 _cleared_path_params 约定，不会发给业务方语义）
# Internal metadata keys (underscore-prefixed, following the _cleared_path_params
# convention; they carry no business meaning)
_QUEUE_ID_KEY = "_rocketmq_queue_id"
_OFFSET_KEY = "_rocketmq_offset"
_BROKER_KEY = "_rocketmq_broker"


class RocketMQOrderPlugin(BaseRocketMQPlugin):
    """RocketMQ 订单消息处理器：前置发送订单事件，后置消费校验。
    RocketMQ order processor: pre-send order event, post-consume and verify."""

    name = "rocketmq-order"

    def _merge_config(
        self,
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """合并 env 与 case 配置。Merge env config with case-level config."""
        proc_configs = global_config.get("processor_configs", {})
        env_config = proc_configs.get(self.name, {}) if isinstance(proc_configs, dict) else {}
        return {**env_config, **case_config}

    def before_request(
        self,
        headers: Dict[str, Any],
        body: Dict[str, Any],
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """发送订单事件，并把消费元数据注入请求体。
        Send the order event and inject consumption metadata into the body."""
        cfg = self._merge_config(case_config, global_config)
        topic = cfg.get("topic", "order-topic")
        tag = cfg.get("tag", "order_create")

        meta = self._send_message(
            topic=topic,
            body={"event": "order_created", "data": body},
            tag=tag,
            key=self.name,
            global_config=global_config,
        )
        # 记录发送位置，供后置处理器从同一偏移消费校验
        # Record the send position so the post-processor can pull from the same offset
        body[_QUEUE_ID_KEY] = meta["queue_id"]
        body[_OFFSET_KEY] = meta["queue_offset"]
        body[_BROKER_KEY] = meta["broker_addr"]
        return headers, body

    def after_response(
        self,
        request_headers: Dict[str, Any],
        request_body: Dict[str, Any],
        response_headers: Dict[str, Any],
        response_body: Any,
        case_config: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> None:
        """消费并校验消息，失败则抛 ProcessorError 使用例失败。
        Consume and verify the message; raise ProcessorError on failure."""
        cfg = self._merge_config(case_config, global_config)
        queue_id = request_body.get(_QUEUE_ID_KEY)
        offset = request_body.get(_OFFSET_KEY)
        broker_addr = request_body.get(_BROKER_KEY)
        if queue_id is None or offset is None:
            # 向后兼容：缺少元数据时仅提示，不失败
            # Backward compatible: just warn when metadata is missing
            logger.warning(_("rocketmq.missing_meta"))
            return

        topic = cfg.get("topic", "order-topic")
        tag = cfg.get("tag", "order_create")
        timeout = float(cfg.get("receive_timeout", 10))
        expected = {
            key: value
            for key, value in request_body.items()
            if not key.startswith("_rocketmq_")
        }

        msgs = self._receive_message(
            topic=topic,
            queue_id=int(queue_id),
            queue_offset=int(offset),
            broker_addr=broker_addr,
            tag=tag,
            timeout=timeout,
            global_config=global_config,
        )
        if not msgs:
            raise ProcessorError(
                _("rocketmq.receive_timeout", topic=topic, queue_id=queue_id,
                  offset=offset, timeout=timeout),
                processor_name=self.name,
            )
        match = self._find_match(msgs, expected)
        if match is None:
            raise ProcessorError(
                _("rocketmq.receive_mismatch", topic=topic),
                processor_name=self.name,
            )
        print(_("rocketmq.received", queue_id=queue_id, offset=offset))
        logger.info(_("rocketmq.received", queue_id=queue_id, offset=offset))

    @staticmethod
    def _find_match(msgs: List[Dict[str, Any]], expected: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """在消费到的消息中查找与预期内容匹配的消息。
        Find the message whose payload matches the expected content."""
        for msg in msgs:
            try:
                payload = json.loads(msg["body"].decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if payload.get("event") == "order_created" and payload.get("data") == expected:
                return msg
        return None
