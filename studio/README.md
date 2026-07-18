# Flow Forge Studio

**中文** | [English](README.en.md)

基于 Vue 3 + Ant Design Vue + Tauri 2 的桌面测试用例工作台：AI 用例生成、可视化编辑 Excel/YAML 用例、计划批注、用例执行与格式转换，一站式完成从生成到报告的完整工作流。

## 能做什么

- **AI 用例生成器**：在 Studio 中配置需求文档和接口文档，启动 AI 智能体自动生成测试用例，实时查看日志，交互式处理 LLM 提问和计划审核。
- **Excel 编辑器**：表格化编辑接口定义/单接口用例/业务链路，内置 JSON 树形编辑器、高级断言规则编辑器、实时校验。
- **YAML 编辑器**：表单化编辑 + 右侧原始 YAML 分屏视图，文件树浏览、多标签页、自动同步。
- **Markdown 计划批注器**：在渲染后的测试计划上选中文本添加结构化批注，自动保存，供智能体读取修改计划；支持查看历史批注。
- **用例执行器**：运行测试用例并生成 HTML 报告，支持多环境切换、多线程执行。
- **用例转换器**：Excel ↔ YAML 互转 + 导出 pytest 代码，支持批量转换。
- **查找替换**：Excel 按单元格、YAML 按原始文本，支持大小写/全词/正则，含跨文件全局搜索。
- **完全兼容执行器**：读写的 Excel/YAML 格式与 [python/](../python/README.md) 执行器完全一致。

## 快速开始

```bash
cd studio
npm install

# Tauri 桌面应用开发模式（自动启动桌面窗口）
npm run dev
```

> Flow Forge Studio 面向**桌面模式**使用，请通过 `npm run dev` 启动。

## 平台兼容性说明

**Flow Forge Studio 仅支持 Windows 平台。** Studio 的进程管理依赖 Windows Job Object 机制（`KILL_ON_JOB_CLOSE`）来保证子进程（agent / executor / converter）在任务终止或应用退出时被操作系统强制终止，这是 Windows 内核提供的功能，其他平台无等价替代。

- **Windows**：✅ 唯一支持平台。子进程自动终止（Job Object）、日志实时输出、进程树强制清理等全部功能完整可用。
- **Linux / macOS**：❌ 不支持。Studio 无法编译为 Linux/macOS 可执行文件，也不应在这些平台上运行。

> **非 Windows 用户请直接使用 [CLI 命令行](../python/README.md) 执行 agent / executor / converter 任务。** 命令行工具是跨平台的，在 Windows、Linux、macOS 上均可正常运行。

## 常用命令

```bash
npm run dev        # Tauri 桌面应用开发模式
npm run build      # Tauri 桌面应用打包（产物在 src-tauri/target/release/）
```

## 推荐工作流

1. **在 Studio 中启动 AI 生成 Excel 用例**：进入「AI 用例生成」，配置需求文档和接口文档路径，启动智能体生成 Excel 用例。生成前可在计划批注器中审核测试计划。
2. **在 Studio 中批量编辑**：打开生成的 Excel，批量调整 Tag、补全参数、修改断言。
3. **转换为 YAML 并做 diff**：用「用例转换器」将 Excel 转为 YAML，逐文件提交 Git。
4. **执行器运行**：用「用例执行器」运行 YAML 目录（或直接运行 Excel），得到 HTML 报告。

> Excel 适合批量编辑，YAML 适合做 diff（每个用例一个文件，代码评审时变更一目了然）。调试好 Skill 和插件后，可在 CLI 下用 `--auto` 模式批量生成。

## 文档索引

| 文档 | 内容 |
|------|------|
| [功能详解](./docs/features.md) | AI 用例生成、Excel/YAML 编辑器、计划批注器、用例执行器、用例转换器、查找替换、快捷键 |
| [架构与开发](./docs/architecture.md) | 组件树、数据流、项目结构、开发命令、扩展开发、与执行器兼容性 |
| [校验规则与断言参考](./docs/validation.md) | Excel/YAML 校验规则、处理器字段校验、AssertRules 运算符与函数 |
