# examples/foli-mall — Example cases for the foli-mall target

[中文](README.md) | **English**

This directory contains example cases that ship with the flow-forge repository. The system under test is the B2C e-commerce playground [foli-mall](https://github.com/Remon-16/foli-mall); the cases here are real output from both AI generation paths, and they also show how the same batch of cases goes from generation to correction.

## Directory overview

| Directory | Contents |
|-----------|----------|
| [agent-out/](./agent-out/) | The full output of the flowforge-testing skill with a strong agent (e.g. Codex) for the cart & order module: `order/` contains a test plan (`plan.md`), YAML cases (`interfaces` / `single_cases` / `biz_flows`), execution config (`config/`), and the execution report (`report/`) |
| [curated/](./curated/) | Runnable cases reworked from a weak-model first draft (YAML + environment config), ready to execute |
| [raw/](./raw/) | The unmodified raw output generated directly by Qwen3-8B-Q4_K_M (Excel), kept next to `curated/` for comparison |

A good order to browse is agent-out → curated → raw: the cases in the first two directories can be run as-is, while `raw/` preserves the original generation state so you can see the difference between the same batch before and after revision. The revision process is documented in the [weak-model case modification record](./docs/weak-model-case-modification-record.md).

## Quick start (running the curated cases)

Before running the cases in `curated/`, prepare the system under test:

1. Clone and start the foli-mall backend: `git clone https://github.com/Remon-16/foli-mall.git`, then run `.\mvnw.cmd spring-boot:run` (Windows) or `./mvnw spring-boot:run` (Linux/macOS) from the repo root. It listens on port 8080 and starts an H2 TCP server on port 9092.
2. Initialize the H2 JDBC driver: run `python tools/h2/init_h2.py` from the flow-forge `python/` directory.
3. Prepare a Python environment and install `python/requirements.txt` (see [python/README](../../python/README.md)).

Then, from the flow-forge `python/` directory:

```bash
python main.py --config ../examples/foli-mall/curated/config.yml --yamlDir ../examples/foli-mall/curated/cases --maxThread 1 --reportName foli_mall_demo
```

The report is written to `python/report/`; a sample report is available at [curated/report/foli_mall_demo_20260806.html](./curated/report/foli_mall_demo_20260806.html).

`curated/cases/` contains **74 cases (65 single-API + 9 business flows)** that use six database fixture plugins (order-fixture / cart-fixture / return-fixture / balance-fixture / user-fixture / product-fixture) through `preprocessors` (see the [plugin guide](./docs/plugin-guide.md)). The `processor_configs.*.db_url` entries in `env-foli-mall.yml` point to the local foli-mall H2 in-memory database by default; you can adjust them if your instance differs. The end-to-end result is **71 passed, plus 3 foli-mall bug-evidence cases failing as expected** (see [foli-mall bugs found](./docs/foli-mall-bugs-found.md)).

## How the raw cases were generated

- Model: Qwen3-8B-Q4_K_M (deployed locally with llama.cpp)
- Generation: the flow-forge `agent/` pipeline over an OpenAI-compatible API
- Config: [weak-model-config.example.yaml](./raw/weak-model-config.example.yaml) (sanitized); details in [raw/README.md](./raw/README.md)

The cases in `raw/` keep their original generated state and have not been modified; use the `curated/` versions if you want to run cases directly.

## Companion docs

| Doc | Content |
|-----|---------|
| [Weak-model case modification record](./docs/weak-model-case-modification-record.md) | How the same batch of cases went from raw AI output to correction, with three examples |
| [Database fixture plugin guide](./docs/plugin-guide.md) | The order / cart / return / balance / user / product fixture plugins: features and config |
| [foli-mall bugs found](./docs/foli-mall-bugs-found.md) | foli-mall business defects confirmed through API testing, with evidence cases |

## Directory layout

```text
examples/foli-mall/
├── agent-out/                 # skill + strong-agent output (cart & order project)
│   └── order/                 #   plan.md + cases/ + config/ + report/
├── curated/                   # curated, runnable cases
│   ├── cases/                 #   YAML cases (one file per case)
│   ├── env-foli-mall.yml      #   environment config (apps + users + plugins)
│   ├── config.yml             #   executor config
│   └── report/                #   sample HTML report
├── raw/                       # raw weak-model output (unmodified)
│   ├── order.xlsx
│   ├── return_chs_u_ds.xlsx
│   └── weak-model-config.example.yaml
└── docs/                      # weak-model case modification record / plugin guide / bugs found
```
