"""RocketMQ 订单消息处理器 — 前置发送订单事件到 RocketMQ 主题。
RocketMQ order message processor — pre-send order event to RocketMQ topic.

测试场景：微服务架构中，API 调用后通过 RocketMQ 通知下游服务。
前置发送测试消息模拟该行为。

Test scenario: in microservice architecture, API calls notify downstream
services via RocketMQ. Pre-send test message to simulate this.

提示 / Tip: 可通过 LoginManager.get_current_user() 获取当前 #{} 登录用户的配置。
Use LoginManager.get_current_user() to access the currently logged-in user's config.

环境配置 / Env config (env-local.yml)::

    processor_configs:
      rocketmq-order:
        namesrv_addr: "localhost:9876"
        group_id: "test-producer-group"
        topic: "order-topic"
        tag: "order_create"

用例 YAML / Test case YAML::

    preprocessors:
      - name: rocketmq-order
        config: {}
"""

from processors.rocketmq import BaseRocketMQPlugin


class RocketMQOrderPlugin(BaseRocketMQPlugin):
    """RocketMQ 订单消息处理器：前置发送订单事件消息。
    RocketMQ order processor: pre-send order event message.

    RocketMQ 消费由独立消费者服务处理，后置仅 print 确认。
    Consumption is handled by dedicated consumer services; post just prints confirmation.
    """

    name = "rocketmq-order"

    def before_request(self, headers, body, case_config, global_config):
        """发送订单事件到 RocketMQ 主题。Send order event to RocketMQ topic."""
        # 合并配置 / Merge config
        proc_configs = global_config.get("processor_configs", {})
        if isinstance(proc_configs, dict):
            env_config = proc_configs.get(self.name, {})
        else:
            env_config = {}
        cfg = {**env_config, **case_config}

        topic = cfg.get("topic", "order-topic")
        tag = cfg.get("tag", "order_create")

        self._send_message(
            topic=topic,
            body={"event": "order_created", "data": body},
            tag=tag,
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

        RocketMQ 消费由独立消费者服务处理，此处仅做确认记录。
        Consumption is handled by dedicated consumer services; here we just log confirmation.
        """
        print(f"[rocketmq-order] Message sent to RocketMQ successfully")
