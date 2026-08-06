# raw — 弱模型原始输出（未修正）

本目录是 Qwen3-8B-Q4_K_M（llama.cpp 本地部署）通过 flow-forge `agent/` 流水线直接生成的原始用例，**未做任何修正**：

- `order.xlsx`：购物车 / 订单模块（生成时含 71 条单接口用例 + 10 条业务链路用例）
- `return_chs_u_ds.xlsx`：退货退款模块（生成时含 20 条单接口用例 + 5 条业务链路用例）

> **请注意：这些用例基本不能直接跑通。** 想运行可用的用例，请使用 [../curated/](../curated/)。原始输出与修正版的对应记录见 [../docs/weak-model-case-modification-record.md](../docs/weak-model-case-modification-record.md)。

## 弱模型配置（脱敏）

[weak-model-config.example.yaml](./weak-model-config.example.yaml) 是 `agent/env.yaml` 的脱敏版本。要点：

| 项 | 值 |
|----|----|
| 模型 | Qwen3-8B-Q4_K_M |
| 部署方式 | llama.cpp（llama-server，OpenAI 兼容 API） |
| 温度 | 0.3 |
| 上下文窗口 | 64000 |

启动 llama-server 的示例命令（路径与参数按你的环境调整）：

```bash
llama-server -m /path/to/Qwen3-8B-Q4_K_M.gguf --host 127.0.0.1 --port 8210 -c 64000
```

然后把 `weak-model-config.example.yaml` 复制为 `agent/env.yaml`，填写 `api_key` 与 `base_url`。任何 OpenAI 兼容端点（Ollama、vLLM 等）都可以替换。
