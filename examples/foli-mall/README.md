# examples/foli-mall — foli-mall 靶场示例用例集

**中文** | [English](README.en.md)

本目录是一组随 flow-forge 仓库发布的示例用例。被测系统是 B2C 电商靶场 [foli-mall](https://github.com/Remon-16/foli-mall)，这里收录了两条 AI 用例生成路径的真实产物，以及同一批用例从生成到修正的过程。

## 目录概览

| 目录 | 内容 |
|------|------|
| [agent-out/](./agent-out/) | flowforge-testing skill 配合强智能体（如 Codex）对购物车与订单模块的完整输出：`order/` 下含测试计划（plan.md）、YAML 用例（interfaces / single_cases / biz_flows）、执行配置（config/）与执行报告（report/） |
| [curated/](./curated/) | 由弱模型初版修正而来的可运行用例（YAML + 环境配置），可直接执行 |
| [raw/](./raw/) | Qwen3-8B-Q4_K_M 直接生成的原始输出（Excel），未做修正，与 curated/ 放在一起便于对比 |

浏览时建议按 agent-out → curated → raw 的顺序：前两个目录的用例可以直接运行，raw/ 保留了生成时的原始状态，与 curated/ 放在一起可以看到同一批用例修正前后的差异。修正过程记录在 [弱模型生成用例修改记录](./docs/weak-model-case-modification-record.md) 中。

## 快速开始（运行 curated 用例）

运行 curated/ 中的用例，需要先准备好被测系统：

1. 克隆并启动 foli-mall 后端：`git clone https://github.com/Remon-16/foli-mall.git`，在仓库根目录执行 `.\mvnw.cmd spring-boot:run`（Windows）或 `./mvnw spring-boot:run`（Linux/macOS）。启动后监听 8080 端口，并自动开启 H2 TCP 9092。
2. 初始化 H2 JDBC 驱动：在 flow-forge 仓库 `python/` 目录执行 `python tools/h2/init_h2.py`。
3. 准备 Python 环境并安装 `python/requirements.txt`（见 [python/README](../../python/README.md)）。

然后在 flow-forge 仓库 `python/` 目录执行：

```bash
python main.py --config ../examples/foli-mall/curated/config.yml --yamlDir ../examples/foli-mall/curated/cases --maxThread 1 --reportName foli_mall_demo
```

报告输出到 `python/report/`，示例报告见 [curated/report/foli_mall_demo_20260806.html](./curated/report/foli_mall_demo_20260806.html)。

curated/cases/ 中共 **74 条用例（65 单接口 + 9 业务链路）**，通过 `preprocessors` 使用 order-fixture / cart-fixture / return-fixture / balance-fixture / user-fixture / product-fixture 六个数据库前置插件（见 [插件指南](./docs/plugin-guide.md)）。`env-foli-mall.yml` 中 `processor_configs.*.db_url` 默认指向本地 foli-mall 的 H2 内存库，如果实例不同，可以同步修改。端到端执行结果为 **71 通过 + 3 条 foli-mall 缺陷证据用例按预期失败**（见 [foli-mall 缺陷记录](./docs/foli-mall-bugs-found.md)）。

## raw 用例的生成方式

- 模型：Qwen3-8B-Q4_K_M（llama.cpp 本地部署）
- 生成：flow-forge `agent/` 流水线 + OpenAI 兼容 API
- 配置：[weak-model-config.example.yaml](./raw/weak-model-config.example.yaml)（已脱敏），详细说明见 [raw/README.md](./raw/README.md)

raw/ 中的用例保留了生成时的原始状态，没有经过修正；想直接运行用例的话，用 curated/ 中的版本。

## 配套文档

| 文档 | 内容 |
|------|------|
| [弱模型生成用例修改记录](./docs/weak-model-case-modification-record.md) | 同一批用例从 AI 原始输出到修正的过程，含三个案例 |
| [前置数据插件指南](./docs/plugin-guide.md) | order / cart / return / balance / user / product 六个数据库夹具插件的功能与配置 |
| [foli-mall 缺陷记录](./docs/foli-mall-bugs-found.md) | 通过 API 测试实测确认的 foli-mall 业务缺陷与证据用例 |

## 目录结构

```text
examples/foli-mall/
├── agent-out/                 # skill + 强智能体生成（购物车与订单项目）
│   └── order/                 #   plan.md + cases/ + config/ + report/
├── curated/                   # 修正后的可运行用例
│   ├── cases/                 #   YAML 用例（每用例一文件）
│   ├── env-foli-mall.yml      #   环境配置（应用 + 用户 + 插件）
│   ├── config.yml             #   执行器配置
│   └── report/                #   示例 HTML 报告
├── raw/                       # 弱模型原始输出（未修正）
│   ├── order.xlsx
│   ├── return_chs_u_ds.xlsx
│   └── weak-model-config.example.yaml
└── docs/                      # 弱模型生成用例修改记录 / 插件指南 / 缺陷记录
```
