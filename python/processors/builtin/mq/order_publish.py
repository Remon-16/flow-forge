"""订单事件发布 MQ 处理器 — 前置发布消息 + 后置消费验证。
Order event publish MQ processor — pre-publish message + post-consume verify.

基于 Kombu 多 MQ 抽象，支持 RabbitMQ / Redis / SQS 等。
Built on Kombu multi-MQ abstraction, supports RabbitMQ, Redis, SQS, etc.

测试场景：API 调用触发订单创建后，系统应向 MQ 发送订单事件。
前置发布测试消息模拟上游事件，后置消费验证。

Test scenario: after order creation API call, system should send order event to MQ.
Pre-publish test message to simulate upstream event, post-consume to verify.
"""

from processors.mq import BaseMQPlugin


class OrderPublishPlugin(BaseMQPlugin):
    """订单发布处理器：前置发布订单消息，后置消费验证。
    Order publish processor: pre-publish order message, post-consume verify.

    环境配置 / Env config (env-local.yml)::

        processor_configs:
          order-publish:
            mq_url: "amqp://guest:guest@localhost:5672//"
            queue_name: "order.create"
            exchange_name: ""
            routing_key: "order.create"

    用例 YAML / Test case YAML::

        preprocessors:
          - name: order-publish
            config: {}
        postprocessors:
          - name: order-publish
            config: {}
    """

    name = "order-publish"

    def before_request(self, headers, body, case_config, global_config):
        """发布订单创建事件消息。Publish an order-created event message.

        向指定队列发送 JSON 消息，携带请求体中的订单信息。
        Send JSON message to the configured queue with order info from request body.
        """
        # 合并配置 / Merge config
        proc_configs = global_config.get("processor_configs", {})
        if isinstance(proc_configs, dict):
            env_config = proc_configs.get(self.name, {})
        else:
            env_config = {}
        cfg = {**env_config, **case_config}

        queue_name = cfg.get("queue_name", "order.create")
        routing_key = cfg.get("routing_key", queue_name)
        exchange_name = cfg.get("exchange_name", "")

        self._publish(
            queue_name=queue_name,
            body={"event": "order_created", "data": body},
            routing_key=routing_key,
            exchange_name=exchange_name,
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
        """消费并打印消息确认。Consume and print message confirmation.

        从队列获取消息并打印，作为验证/调试用途。
        Get message from queue and print for verification/debugging.
        """
        proc_configs = global_config.get("processor_configs", {})
        if isinstance(proc_configs, dict):
            env_config = proc_configs.get(self.name, {})
        else:
            env_config = {}
        cfg = {**env_config, **case_config}
        queue_name = cfg.get("queue_name", "order.create")

        msg = self._get_message(
            queue_name=queue_name,
            timeout=5,
            global_config=global_config,
        )
        if msg is not None:
            print(f"[order-publish] Consumed message: {msg}")
        else:
            print("[order-publish] No message consumed (timeout or empty queue)")
