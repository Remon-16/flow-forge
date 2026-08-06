# raw — Raw weak-model output (unmodified)

This directory contains cases generated directly by Qwen3-8B-Q4_K_M (deployed locally with llama.cpp) through the flow-forge `agent/` pipeline, with **no correction at all**:

- `order.xlsx`: cart / order module (71 single-API cases + 10 business flows at generation time)
- `return_chs_u_ds.xlsx`: return/refund module (20 single-API cases + 5 business flows at generation time)

> **Please note: these cases mostly cannot run as-is.** For runnable cases, use [../curated/](../curated/). The record of raw vs. curated is in [../docs/weak-model-case-modification-record.md](../docs/weak-model-case-modification-record.md).

## Weak-model configuration (sanitized)

[weak-model-config.example.yaml](./weak-model-config.example.yaml) is a sanitized copy of `agent/env.yaml`. Key settings:

| Item | Value |
|------|-------|
| Model | Qwen3-8B-Q4_K_M |
| Deployment | llama.cpp (`llama-server`, OpenAI-compatible API) |
| Temperature | 0.3 |
| Context window | 64000 |

Example `llama-server` command (adjust paths and flags for your environment):

```bash
llama-server -m /path/to/Qwen3-8B-Q4_K_M.gguf --host 127.0.0.1 --port 8210 -c 64000
```

Then copy `weak-model-config.example.yaml` to `agent/env.yaml` and fill in `api_key` and `base_url`. Any OpenAI-compatible endpoint (Ollama, vLLM, etc.) can be used instead.
