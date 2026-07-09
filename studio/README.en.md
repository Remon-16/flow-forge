# Flow Forge Studio

[中文](README.md) | **English**

A desktop test-case workbench built with Vue 3 + Ant Design Vue + Tauri 2: visually edit Excel (.xlsx) and YAML (.yaml) test cases, and add interactive Markdown annotations to AI test plans.

## What It Can Do

- **Excel editor**: table-based editing of interface definitions / single-API test cases / business flows, with a built-in JSON tree editor, an advanced assertion rule editor, and real-time validation.
- **YAML editor**: form-based editing plus a split-view raw YAML panel on the right, with file-tree browsing, multiple tabs, and automatic syncing.
- **Markdown plan annotator**: select text on the rendered test plan to add structured annotations that are saved automatically for the agent to read and revise the plan; historical annotations can be reviewed.
- **Find and replace**: by cell in Excel and by raw text in YAML, with match-case / whole-word / regex options, including cross-file global search.
- **Full executor compatibility**: the Excel/YAML formats it reads and writes are identical to those of the [python/](../python/README.en.md) executor.

## Quick Start

```bash
cd studio
npm install

# Tauri desktop app dev mode (launches the desktop window automatically)
npm run dev
```

> Flow Forge Studio targets **desktop mode** — launch it with `npm run dev`.

## Common Commands

```bash
npm run dev        # Tauri desktop app dev mode
npm run build      # Tauri desktop app build (output in src-tauri/target/release/)
```

## Recommended Workflow

1. **AI generates Excel cases**: run the [Agent](../agent/README.en.md) with `--output-format excel` or `both`.
2. **Batch edit in Studio**: open the Excel file to bulk-adjust tags, fill in parameters, and modify assertions.
3. **Convert to YAML and diff**: run `python converter_main.py excel2yaml` to convert to YAML, then commit each file to Git.
4. **Run the executor**: use the [executor](../python/README.en.md) to run the YAML directory and get a report.

> Excel is ideal for batch editing; YAML is ideal for diffing (one file per case makes every change obvious during code review).

## Documentation Index

| Document | Contents |
|------|------|
| [Feature Guide](./docs/features.en.md) | Excel/YAML editors, Markdown annotator, find and replace, keyboard shortcuts |
| [Architecture & Development](./docs/architecture.en.md) | Component tree, data flow, project structure, development commands, extension development, executor compatibility |
| [Validation Rules & Assertion Reference](./docs/validation.en.md) | Excel/YAML validation rules, processor field validation, AssertRules operators and functions |
