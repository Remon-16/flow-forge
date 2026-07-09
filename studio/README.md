# Flow Forge Studio

**中文** | [English](README.en.md)

基于 Vue 3 + Ant Design Vue + Tauri 2 的桌面测试用例工作台：可视化编辑 Excel (.xlsx) 和 YAML (.yaml) 测试用例，以及对 AI 测试计划进行 Markdown 交互式批注。

## 能做什么

- **Excel 编辑器**：表格化编辑接口定义/单接口用例/业务链路，内置 JSON 树形编辑器、高级断言规则编辑器、实时校验。
- **YAML 编辑器**：表单化编辑 + 右侧原始 YAML 分屏视图，文件树浏览、多标签页、自动同步。
- **Markdown 计划批注器**：在渲染后的测试计划上选中文本添加结构化批注，自动保存，供智能体读取修改计划；支持查看历史批注。
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

## 常用命令

```bash
npm run dev        # Tauri 桌面应用开发模式
npm run build      # Tauri 桌面应用打包（产物在 src-tauri/target/release/）
```

## 推荐工作流

1. **AI 生成 Excel 用例**：运行 [Agent](../agent/README.md) 时用 `--output-format excel` 或 `both`。
2. **在 Studio 中批量编辑**：打开 Excel，批量调整 Tag、补全参数、修改断言。
3. **转换为 YAML 并做 diff**：用 `python converter_main.py excel2yaml` 转为 YAML，逐文件提交 Git。
4. **执行器运行**：用 [执行器](../python/README.md) 运行 YAML 目录，得到报告。

> Excel 适合批量编辑，YAML 适合做 diff（每个用例一个文件，代码评审时变更一目了然）。

## 文档索引

| 文档 | 内容 |
|------|------|
| [功能详解](./docs/features.md) | Excel/YAML 编辑器、Markdown 批注器、查找替换、快捷键 |
| [架构与开发](./docs/architecture.md) | 组件树、数据流、项目结构、开发命令、扩展开发、与执行器兼容性 |
| [校验规则与断言参考](./docs/validation.md) | Excel/YAML 校验规则、处理器字段校验、AssertRules 运算符与函数 |
