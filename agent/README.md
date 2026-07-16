# Flow Forge — 接口自动化用例生成智能体

**中文** | [English](README.en.md)

基于 LangGraph 流水线的多智能体系统，读取**需求文档**和**接口文档**，经过「计划生成 → 人工审核 → 用例编排」流水线，自动生成符合执行器格式的 YAML 测试用例（可选导出 Excel）。

## 能做什么

- **多格式输入**：需求文档支持 Markdown / PDF / 纯文本；接口文档支持 OpenAPI 3.0（JSON/YAML）/ Markdown 表格。支持多文档并行输入（每个文件独立解析，保证质量）。
- **两类用例**：生成单接口用例和多步骤业务链路用例，支持简单等值断言（`assert_dict`）和高级多运算符断言（`assert_rules`）。
- **人工审核可控**：AI 生成测试计划后需人工确认（`y`/`n`/`r` 三种方式），确保质量后再生成用例。
- **反幻觉**：URL 纠错、输出数量校验、分批生成，把不可靠输出拦在生成阶段。
- **可插拔扩展**：插件（补充用例属性）+ 技能（注入领域知识），无需改代码即可定制。
- **LLM 兼容广**：兼容任意 OpenAI 兼容 API——云端强模型（如 DeepSeek）或本地弱模型（如 Ollama）均可。
- **断点续写**：用例生成中断后可恢复，需求变更后支持增量更新。

## 快速开始

```bash
cd agent
pip install -r requirements.txt

# 0) 安装共享数据模型（首次使用必须执行 / Required for first-time setup）
pip install -e ../shared/py

# 1) 配置 LLM：复制模板并填入 api_key / model / base_url
cp env.example.yaml env.yaml

# 2) 运行完整流水线（需求文档 + 接口文档）
python main.py --requirement docs/req.md --api docs/api.yaml

# 3) 人工审核测试计划：输入 y 批准 / n 文字反馈 / r 按批注文件修改
# 4) 审核通过后自动生成用例，输出到 ./output_<timestamp>/
```

生成的用例可直接交给 [执行器](../python/README.md) 运行，或用 [Studio](../studio/README.md) 可视化编辑。

## 常用命令

```bash
# 指定输出目录
python main.py --requirement docs/req.md --api docs/api.yaml --output my_output

# 仅输出 YAML（不导出 Excel）
python main.py --requirement docs/req.md --api docs/api.yaml --output-format yaml

# 仅生成单接口用例 / 仅生成业务链路用例
python main.py --requirement docs/req.md --api docs/api.yaml --case-type single
python main.py --requirement docs/req.md --api docs/api.yaml --case-type biz

# 自动模式：跳过所有人工审核（适合调试完毕后夜间批量生成）
python main.py --requirement docs/req.md --api docs/api.yaml --auto

# 从已有输出目录断点恢复（自动加载首次运行时的配置）
python main.py --resume --output output_20240101_120000

# 恢复时覆盖部分配置（若覆盖影响已完成阶段，会输出警告）
python main.py --resume --output output_20240101_120000 --case-type single -p "新的指导"

# 用例字段翻译兜底工具（弱模型输出中英混杂时使用）
python translate_cases.py output/cases/ --target-lang zh_CN
```

完整参数见 [配置与命令行参考](./docs/configuration.md)。

## 运行测试

```bash
python -m pytest tests/ -v
```

测试不产生任何 LLM API 费用（所有 LLM 调用均已 mock）。

## 文档索引

| 文档 | 内容 |
|------|------|
| [配置与命令行参考](./docs/configuration.md) | `env.yaml` 全字段、`translate_env.yaml`、全部 CLI 参数、翻译工具 |
| [工作原理](./docs/how-it-works.md) | 11 步流水线架构、审核模式 y/n/r、自动模式、上下文窗口管理与文档切分策略、目录结构、设计理念 |
| [插件与技能系统](./docs/plugins-and-skills.md) | 插件开发与配置、Skill 注入、官方插件与内置技能 |
| [反幻觉与错误处理](./docs/anti-hallucination.md) | URL 纠错、数量校验、重试策略（warn/retry/keep） |
