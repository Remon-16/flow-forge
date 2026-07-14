"""Kafka 订单事件处理器 — 前置发送订单事件到 Kafka topic。
Kafka order event processor — pre-send order event to Kafka topic.

测试场景：微服务架构中，API 调用后通过 Kafka 通知下游服务。
前置发送测试消息模拟该行为。

Test scenario: in microservice architecture, API calls notify downstream
services via Kafka. Pre-send test message to simulate this.

环境配置 / Env config (env-local.yml)::

    processor_configs:
      kafka-order-event:
        bootstrap_servers: "localhost:9092"
        topic: "order-topic"

用例 YAML / Test case YAML::

    preprocessors:
      - name: kafka-order-event
        config: {}
"""

from processors.kafka import BaseKafkaPlugin


class KafkaOrderEventPlugin(BaseKafkaPlugin):
    """Kafka 订单事件处理器：前置发送订单事件消息。
    Kafka order event processor: pre-send order event message.

    Kafka 消费由独立消费者服务处理，后置仅 print 确认。
    Consumption is handled by dedicated consumer services; post just prints confirmation.
    """

    name = "kafka-order-event"

    def before_request(self, headers, body, case_config, global_config):
        """发送订单事件到 Kafka topic。Send order event to Kafka topic."""
        # 合并配置 / Merge config
        proc_configs = global_config.get("processor_configs", {})
        if isinstance(proc_configs, dict):
            env_config = proc_configs.get(self.name, {})
        else:
            env_config = {}
        cfg = {**env_config, **case_config}

        topic = cfg.get("topic", "order-topic")
        key = cfg.get("key", "")

        self._send_message(
            topic=topic,
            body={"event": "order_created", "data": body},
            key=key or None,
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

        Kafka 消费由独立消费者服务处理，此处仅做确认记录。
        Consumption is handled by dedicated consumer services; here we just log confirmation.
        """
        print(f"[kafka-order-event] Message sent to Kafka successfully")
