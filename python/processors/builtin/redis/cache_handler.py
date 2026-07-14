"""缓存处理 Redis 处理器 — 前置写缓存 + 后置清缓存。
Cache handler Redis processor — pre-set + post-delete cache entries.

测试场景：API 从 Redis 缓存中读取数据（如商品列表、订单状态）。
在请求前写入测试缓存数据，请求后清理。

Test scenario: API reads data from Redis cache (e.g. product list, order status).
Pre-set test cache data before request, clean up after.
"""

from processors.redis import BaseRedisPlugin


class CacheHandlerPlugin(BaseRedisPlugin):
    """缓存处理处理器：前置写入测试缓存，后置清理。
    Cache handler: pre-set test cache entry, post-delete for cleanup.

    环境配置 / Env config (env-local.yml)::

        processor_configs:
          cache-handler:
            redis_url: "redis://localhost:6379/0"
            default_prefix: "test:cache:"
            ttl_seconds: 3600

    用例 YAML / Test case YAML::

        preprocessors:
          - name: cache-handler
            config: {}
        postprocessors:
          - name: cache-handler
            config: {}
    """

    name = "cache-handler"

    def before_request(self, headers, body, case_config, global_config):
        """写入测试缓存条目。Set a test cache entry.

        从配置读取 redis_prefix 和 ttl_seconds，向 Redis 写入测试缓存。
        Reads redis_prefix and ttl_seconds from config, sets test cache in Redis.
        """
        # 合并配置：case_config 覆盖 env 默认值 / Merge config: case_config overrides env defaults
        proc_configs = global_config.get("processor_configs", {})
        if isinstance(proc_configs, dict):
            env_config = proc_configs.get(self.name, {})
        else:
            env_config = {}
        cfg = {**env_config, **case_config}

        prefix = cfg.get("default_prefix", "test:cache:")
        ttl = int(cfg.get("ttl_seconds", 3600))

        client = self._get_client(global_config)

        # 为每个请求体中的关键字段创建缓存条目
        # Create cache entries for key fields in the request body
        if isinstance(body, dict):
            for key, value in body.items():
                if isinstance(value, (str, int, float, bool)):
                    cache_key = f"{prefix}{key}"
                    client.set(cache_key, str(value), ex=ttl)

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
        """清理测试缓存条目。Delete test cache entries.

        删除 before_request 中创建的所有测试缓存 key。
        Delete all test cache keys created in before_request.
        """
        proc_configs = global_config.get("processor_configs", {})
        if isinstance(proc_configs, dict):
            env_config = proc_configs.get(self.name, {})
        else:
            env_config = {}
        cfg = {**env_config, **case_config}
        prefix = cfg.get("default_prefix", "test:cache:")

        client = self._get_client(global_config)

        # 删除匹配前缀的测试缓存 key / Delete test cache keys matching prefix
        if isinstance(request_body, dict):
            for key in request_body:
                if isinstance(key, str) and isinstance(request_body[key], (str, int, float, bool)):
                    cache_key = f"{prefix}{key}"
                    client.delete(cache_key)
