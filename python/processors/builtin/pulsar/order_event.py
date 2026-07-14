"""Pulsar 订单事件处理器 — 前置发送订单事件到 Pulsar topic。
Pulsar order event processor — pre-send order event to Pulsar topic.

测试场景：微服务架构中，API 调用后通过 Pulsar 通知下游服务。
前置发送测试消息模拟该行为。

Test scenario: in microservice architecture, API calls notify downstream
services via Pulsar. Pre-send test message to simulate this.

环境配置 / Env config (env-local.yml)::

    processor_configs:
      pulsar-order-event:
        service_url: "pulsar://localhost:6650"
        topic: "order-topic"

用例 YAML / Test case YAML::

    preprocessors:
      - name: pulsar-order-event
        config: {}
"""

from processors.pulsar import BasePulsarPlugin


class PulsarOrderEventPlugin(BasePulsarPlugin):
    """Pulsar 订单事件处理器：前置发送订单事件消息。
    Pulsar order event processor: pre-send order event message.

    Pulsar 消费由独立消费者服务处理，后置仅 print 确认。
    Consumption is handled by dedicated consumer services; post just prints confirmation.
    """

    name = "pulsar-order-event"

    def before_request(self, headers, body, case_config, global_config):
        """发送订单事件到 Pulsar topic。Send order event to Pulsar topic."""
        # 合并配置 / Merge config
        proc_configs = global_config.get("processor_configs", {})
        if isinstance(proc_configs, dict):
            env_config = proc_configs.get(self.name, {})
        else:
            env_config = {}
        cfg = {**env_config, **case_config}

        topic = cfg.get("topic", "order-topic")

        self._send_message(
            topic=topic,
            body={"event": "order_created", "data": body},
            global_config=global_config,
        )

        return headers, body

    def after_response(
        self,
        request_headers,
        request_body,
        response_headers,
        response_body,
        case_config,
        global_config,
    ):
        """打印发送确认。Print send confirmation.

        Pulsar 消费由独立消费者服务处理，此处仅做确认记录。
        Consumption is handled by dedicated consumer services; here we just log confirmation.
        """
        print(f"[pulsar-order-event] Message sent to Pulsar successfully")
