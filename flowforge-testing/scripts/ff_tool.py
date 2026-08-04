"""Flow Forge skill 工具 — validate / execute / convert 统一入口。

Flow Forge skill tool: unified entry for validate / execute / convert.

所有对外命令都通过解析出的 Python 解释器以子进程方式调用
python/main.py 与 python/converter_main.py，并带可配置超时。
All external commands run python/main.py and python/converter_main.py as
subprocesses through the resolved interpreter, with a configurable timeout.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import yaml

# 注入 scripts 与 shared/py 到 sys.path / Inject scripts and shared/py into sys.path
_SCRIPTS_DIR = Path(__file__).resolve().parent
_SHARED_DIR = Path(__file__).resolve().parents[2] / "shared" / "py"
for _p in (_SCRIPTS_DIR, _SHARED_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from flow_forge_schemas import (  # noqa: E402
    OPERATOR_LIST,
    REQUIRED_BIZ_FLOW,
    REQUIRED_BIZ_STEP,
    REQUIRED_SINGLE,
    VALID_HTTP_METHODS,
    VALID_TAGS,
    VALID_TYPES,
)
from i18n import _, set_lang  # noqa: E402
from resolve_python import find_skill_root, load_config, resolve_python  # noqa: E402

logger = logging.getLogger(__name__)

# 无需 processor_configs 即可运行的内置处理器 / Built-in processors that need no config
NO_CONFIG_PROCESSORS = {
    "timestamp",
    "print-demo",
    "print-demo-post",
    "response-time",
    "path-param-restore",
}

# inherit 中不允许的中文字符 / Chinese characters forbidden in inherit
_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")


def _locate_flowforge_root(config: dict) -> Path:
    """定位 flow-forge 仓库根目录。Locate the flow-forge repository root."""
    root = str(config.get("flowforge_root") or "").strip()
    return Path(root) if root else find_skill_root().parent


def _python_dir(config: dict) -> Path:
    """返回 python/ 子项目目录。Return the python/ subproject directory."""
    return _locate_flowforge_root(config) / "python"


def _collect_yaml_files(yaml_dir: str = "", yaml_files: str = "") -> List[Path]:
    """收集待校验的 YAML 文件列表。

    Collect the YAML files to validate, from a directory (recursive) or a
    comma-separated file list.
    """
    files: List[Path] = []
    if yaml_dir:
        root = Path(yaml_dir)
        if not root.is_dir():
            logger.warning(_("tool.yaml_dir_missing", path=yaml_dir))
            return files
        files = sorted(
            p for p in root.rglob("*") if p.suffix.lower() in (".yaml", ".yml")
        )
    if yaml_files:
        for raw in yaml_files.split(","):
            raw = raw.strip()
            if raw:
                p = Path(raw)
                if p.is_file():
                    files.append(p)
    return files


def _load_document(path: Path) -> Tuple[dict, str]:
    """加载单个 YAML 文件，返回 (文档, 错误信息)。

    Load one YAML file and return (document, error message).
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        return {}, f"invalid YAML: {e}"
    if data is None:
        return {}, "empty YAML document"
    if not isinstance(data, dict):
        return {}, f"top-level YAML must be a mapping, got {type(data).__name__}"
    return data, ""


def _infer_case_type(case: dict) -> str:
    """推断用例类型：显式 case_type > 结构推断 > interfaces。

    Infer the case type: explicit case_type > structural inference >
    interfaces.
    """
    case_type = str(case.get("case_type") or "").strip().lower()
    if case_type in ("single", "biz", "interfaces"):
        return case_type
    if "steps" in case:
        return "biz"
    if "test_id" in case:
        return "single"
    return "interfaces"


def _check_required(case: dict, required: List[str], prefix: str = "") -> List[str]:
    """检查必填字段。Check required fields."""
    errors = []
    for field in required:
        val = case.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            errors.append(f"{prefix}missing required field '{field}'")
    return errors


def _check_method(case: dict, prefix: str = "") -> List[str]:
    """检查 HTTP 方法合法性。Check HTTP method validity."""
    method = str(case.get("method") or "").strip().upper()
    if method and method not in VALID_HTTP_METHODS:
        return [f"{prefix}invalid HTTP method '{method}'"]
    return []


def _check_tag(case: dict, prefix: str = "") -> List[str]:
    """检查 tag 合法性（P0-P3）。Check tag validity (P0-P3)."""
    tag = str(case.get("tag") or "").strip()
    if tag and tag not in VALID_TAGS:
        return [f"{prefix}invalid tag '{tag}' (expected P0-P3)"]
    return []


def _check_status_code(case: dict, prefix: str = "") -> List[str]:
    """检查 status_code 范围。Check the status_code range."""
    sc = case.get("status_code")
    if sc is None:
        return []
    try:
        code = int(sc)
        if code < 100 or code > 599:
            return [f"{prefix}invalid status_code {code}"]
    except (ValueError, TypeError):
        return [f"{prefix}status_code must be int, got {type(sc).__name__}"]
    return []


def _check_url(case: dict, prefix: str = "") -> List[str]:
    """检查 url 基本约束。Check basic url constraints."""
    url = str(case.get("url") or "")
    if url and "\n" in url:
        return [f"{prefix}url contains newline"]
    return []


def _check_url_placeholder_sources(case: dict, prefix: str = "") -> List[str]:
    """检查 URL 占位符的来源：request_body 或本步 inherit 必须二选一。

    Check URL placeholders have a source: request_body or this step's
    inherit. A body key holding another placeholder for the same URL
    variable is an error (it produces a literal '#' fragment at runtime).
    """
    url = str(case.get("url") or "")
    if "{" not in url:
        return []
    body = case.get("request_body") or {}
    if not isinstance(body, dict):
        body = {}
    inherit = case.get("inherit")
    inherit_vars = set()
    if isinstance(inherit, dict):
        inherit_vars = {str(k) for k in inherit.keys()}
    elif isinstance(inherit, str) and inherit.strip():
        for pair in inherit.split(","):
            if "=" in pair:
                inherit_vars.add(pair.split("=", 1)[0].strip())

    errors = []
    for m in re.finditer(r"#\{(\w+)\}|\{(\w+)\}", url):
        var = m.group(1) or m.group(2)
        if var in body:
            val = body[var]
            if isinstance(val, str) and re.search(r"#\{\w+\}|\{\w+\}", val):
                errors.append(
                    f"{prefix}url placeholder '#{{{var}}}' duplicates request_body key "
                    f"'{var}' whose value is itself a placeholder; remove the body key "
                    "and declare the variable in inherit"
                )
            continue
        if var not in inherit_vars:
            errors.append(
                f"{prefix}url placeholder '#{{{var}}}' has no source: add '{var}' to "
                "request_body or declare it in this step's inherit"
            )
    return errors


def _check_dict_field(case: dict, field: str, prefix: str = "") -> List[str]:
    """检查 dict 或 JSON 字符串字段。Check dict or JSON-string fields."""
    val = case.get(field)
    if val is None:
        return []
    if isinstance(val, str):
        try:
            json.loads(val)
        except (json.JSONDecodeError, ValueError):
            return [f"{prefix}'{field}' is not valid JSON"]
    elif not isinstance(val, dict):
        return [f"{prefix}'{field}' must be dict or JSON string, got {type(val).__name__}"]
    return []


def _has_valid_operator(rule: str) -> bool:
    """判断断言规则是否匹配任一合法运算符。

    Check whether an assertion rule matches at least one valid operator.
    """
    for op in OPERATOR_LIST:
        if re.search(op["pattern"], rule):
            return True
    return False


def _check_assert_rules(case: dict, prefix: str = "") -> List[str]:
    """检查 assert_rules 格式与运算符。Check assert_rules format and operators."""
    ar = case.get("assert_rules")
    if ar is None or (isinstance(ar, list) and not ar):
        return []
    if isinstance(ar, str):
        try:
            ar = json.loads(ar)
        except (json.JSONDecodeError, ValueError):
            return [f"{prefix}assert_rules is not valid JSON"]
    if not isinstance(ar, list):
        return [f"{prefix}assert_rules must be a list, got {type(ar).__name__}"]
    errors = []
    for i, item in enumerate(ar):
        if not isinstance(item, str):
            errors.append(f"{prefix}assert_rules[{i}] must be a string, got {type(item).__name__}")
        elif not _has_valid_operator(item):
            errors.append(f"{prefix}assert_rules[{i}] has no valid operator: {item}")
        elif "typeof" in item:
            m = re.search(r"\s+typeof\s+(.+)$", item)
            if m and m.group(1).strip() not in VALID_TYPES:
                errors.append(
                    f"{prefix}assert_rules[{i}] invalid typeof type: {m.group(1).strip()}"
                )
    return errors


def _check_inherit(inherit, steps: List[dict], prefix: str = "") -> List[str]:
    """检查 inherit 引用与字符约束。

    Check inherit references and character constraints.
    """
    errors = []
    step_ids = {str(s.get("step_id") or "") for s in steps}

    def _check_entry(key: str, value: str) -> None:
        if _CHINESE_RE.search(key) or _CHINESE_RE.search(value):
            errors.append(f"{prefix}inherit must not contain Chinese characters: {key}={value}")
            return
        if not value:
            errors.append(f"{prefix}inherit key '{key}' has empty value")
            return
        dot_idx = value.find(".")
        if dot_idx > 0:
            ref_step = value[:dot_idx]
            if ref_step not in step_ids:
                errors.append(f"{prefix}inherit key '{key}' references unknown StepID '{ref_step}'")

    if isinstance(inherit, dict):
        for key, value in inherit.items():
            _check_entry(str(key).strip(), str(value).strip() if value else "")
    elif isinstance(inherit, str) and inherit.strip():
        for pair in inherit.split(","):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            key, value = pair.split("=", 1)
            _check_entry(key.strip(), value.strip())
    return errors


def _validate_single(case: dict, prefix: str = "") -> List[str]:
    """校验单接口用例。Validate a single API case."""
    errors = []
    errors.extend(_check_required(case, REQUIRED_SINGLE, prefix))
    errors.extend(_check_method(case, prefix))
    errors.extend(_check_tag(case, prefix))
    errors.extend(_check_status_code(case, prefix))
    errors.extend(_check_url(case, prefix))
    for field in ("request_head", "request_body"):
        errors.extend(_check_dict_field(case, field, prefix))
    errors.extend(_check_dict_field(case, "assert_dict", prefix))
    errors.extend(_check_assert_rules(case, prefix))
    errors.extend(_check_url_placeholder_sources(case, prefix))
    return errors


def _validate_biz(case: dict, prefix: str = "") -> List[str]:
    """校验业务链路用例。Validate a business flow case."""
    errors = []
    errors.extend(_check_required(case, REQUIRED_BIZ_FLOW, prefix))
    steps = case.get("steps") or []
    if not isinstance(steps, list) or not steps:
        errors.append(f"{prefix}steps must be a non-empty list")
        return errors
    seen_step_ids = set()
    for si, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"{prefix}steps[{si}] must be a mapping")
            continue
        sp = f"steps[{si}]."
        errors.extend(_check_required(step, REQUIRED_BIZ_STEP, sp))
        errors.extend(_check_method(step, sp))
        errors.extend(_check_tag(step, sp))
        errors.extend(_check_status_code(step, sp))
        errors.extend(_check_url(step, sp))
        for field in ("request_head", "request_body"):
            errors.extend(_check_dict_field(step, field, sp))
        errors.extend(_check_dict_field(step, "assert_dict", sp))
        errors.extend(_check_assert_rules(step, sp))
        errors.extend(_check_url_placeholder_sources(step, sp))
        step_id = str(step.get("step_id") or "")
        if step_id:
            if step_id in seen_step_ids:
                errors.append(f"{prefix}duplicate step_id '{step_id}'")
            seen_step_ids.add(step_id)
        errors.extend(_check_inherit(step.get("inherit"), steps, sp))
    return errors


def _validate_interface(case: dict, prefix: str = "") -> List[str]:
    """校验接口定义。Validate an interface definition."""
    errors = []
    # 接口定义仅强校验标识字段 / Interface defs only require identity fields
    errors.extend(_check_required(case, ["test_id", "api_name", "url"], prefix))
    errors.extend(_check_method(case, prefix))
    errors.extend(_check_url(case, prefix))
    return errors


def _validate_case(case: dict) -> List[str]:
    """按推断类型校验单个用例。Validate a single case by its inferred type."""
    case_type = _infer_case_type(case)
    if case_type == "single":
        return _validate_single(case)
    if case_type == "biz":
        return _validate_biz(case)
    return _validate_interface(case)


def _referenced_processors(cases: List[Tuple[Path, dict]]) -> List[Tuple[str, Path]]:
    """收集用例引用的处理器（排除接口定义）。

    Collect processors referenced by cases (excluding interface defs).
    """
    refs: List[Tuple[str, Path]] = []
    for path, case in cases:
        case_type = _infer_case_type(case)
        items = case.get("steps") or [] if case_type == "biz" else [case]
        for item in items:
            if not isinstance(item, dict):
                continue
            for section in ("preprocessors", "postprocessors"):
                for proc in item.get(section) or []:
                    if isinstance(proc, dict) and proc.get("name"):
                        refs.append((str(proc["name"]), path))
    return refs


def _load_env_processor_configs(config_dir: Path, env_name: str) -> set:
    """加载 env.yml 与 env-{envName}.yml 中的 processor_configs 名称。

    Load processor_configs names from env.yml and env-{envName}.yml.
    """
    names = set()
    for fname in ("env.yml", f"env-{env_name}.yml"):
        p = config_dir / fname
        if not p.is_file():
            continue
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        names.update((data.get("processor_configs") or {}).keys())
    return names


def _processor_warnings(
    cases: List[Tuple[Path, dict]], config_dir: Path, env_name: str
) -> List[str]:
    """检查处理器是否缺少 processor_configs 配置。

    Check whether referenced processors lack processor_configs entries.
    """
    refs = _referenced_processors(cases)
    if not refs:
        return []
    if not (config_dir / "env.yml").is_file() and not (
        config_dir / f"env-{env_name}.yml"
    ).is_file():
        logger.warning(_("tool.warning_env_config_not_found", path=str(config_dir)))
        return []
    configured = _load_env_processor_configs(config_dir, env_name)
    warnings = []
    for name, path in refs:
        if name not in configured and name not in NO_CONFIG_PROCESSORS:
            warnings.append(name)
            logger.warning(
                _(
                    "tool.warning_missing_processor_config",
                    name=name,
                    path=str(path),
                )
            )
    return warnings


def run_validate(args) -> int:
    """执行 validate 子命令。Run the validate subcommand."""
    config = load_config(args.config)
    set_lang(str(config.get("language") or "zh_CN"))
    env_name = args.env_name or str((config.get("executor") or {}).get("env_name") or "local")

    files = _collect_yaml_files(args.yamlDir, args.yamlFiles)
    if not files:
        logger.error(_("tool.yaml_files_empty"))
        return 2

    logger.info(_("tool.validate_start", count=len(files)))
    loaded: List[Tuple[Path, dict]] = []
    total_errors = 0
    for path in files:
        case, err = _load_document(path)
        if err:
            total_errors += 1
            logger.error(_("tool.file_invalid", path=str(path)))
            logger.error("  %s", err)
            continue
        loaded.append((path, case))
        errors = _validate_case(case)
        if errors:
            total_errors += 1
            logger.error(_("tool.file_invalid", path=str(path)))
            for e in errors:
                logger.error("  - %s", e)
        else:
            logger.info(_("tool.file_valid", path=str(path)))

    config_dir = Path(args.config_dir) if args.config_dir else _python_dir(config)
    _processor_warnings(loaded, config_dir, env_name)

    logger.info(_("tool.validate_summary", total=len(files), errors=total_errors))
    return 0 if total_errors == 0 else 1


def _build_execute_command(args, config: dict) -> Tuple[List[str], Path]:
    """构造执行器命令与其工作目录。Build the executor command and its cwd."""
    python = resolve_python(config)
    python_dir = _python_dir(config)
    if not python_dir.is_dir():
        raise RuntimeError(_("tool.python_dir_missing", path=str(python_dir)))
    cmd = [
        python,
        "main.py",
        "--yamlDir",
        args.yamlDir,
        "--envName",
        args.envName,
        "--apiMode",
        args.apiMode,
    ]
    if args.maxThread:
        cmd += ["--maxThread", str(args.maxThread)]
    return cmd, python_dir


def _run_child(cmd, cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    """以 UTF-8 输出运行子进程，避免 Windows 管道按 GBK 解码中文失败。

    Run a subprocess with UTF-8 output so Chinese logs do not break the pipe
    on Windows (see the known-issue note in the repository README).
    """
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        timeout=timeout,
        check=False,
        env=env,
    )


def _decode(data) -> str:
    """按 UTF-8 解码子进程输出，损坏字节以替换符处理。

    Decode subprocess output as UTF-8, replacing malformed bytes.
    """
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)


def run_execute(args) -> int:
    """执行 execute 子命令。Run the execute subcommand."""
    config = load_config(args.config)
    set_lang(str(config.get("language") or "zh_CN"))
    executor_cfg = config.get("executor") or {}
    args.envName = args.envName or str(executor_cfg.get("env_name") or "local")
    args.apiMode = args.apiMode or str(executor_cfg.get("api_mode") or "all")
    args.maxThread = args.maxThread or executor_cfg.get("max_thread") or 0
    timeout = args.timeout or int(executor_cfg.get("timeout_seconds") or 1800)

    try:
        cmd, python_dir = _build_execute_command(args, config)
    except RuntimeError as e:
        logger.error(str(e))
        return 2

    logger.info(_("tool.execute_start", command=" ".join(cmd)))
    try:
        res = _run_child(cmd, python_dir, timeout)
    except subprocess.TimeoutExpired:
        logger.error(_("tool.execute_timeout", timeout=timeout))
        return 124
    sys.stdout.write(_decode(res.stdout))
    sys.stderr.write(_decode(res.stderr))
    logger.info(_("tool.execute_exit", code=res.returncode))
    return res.returncode


def _build_convert_command(args, config: dict) -> Tuple[List[str], Path]:
    """构造转换器命令与其工作目录。Build the converter command and its cwd."""
    python = resolve_python(config)
    python_dir = _python_dir(config)
    if not python_dir.is_dir():
        raise RuntimeError(_("tool.python_dir_missing", path=str(python_dir)))
    cmd = [python, "converter_main.py", args.subcommand]
    if args.subcommand == "excel2yaml":
        cmd += ["--input", args.input, "--output", args.output]
    else:
        for flag, key in (
            ("--interfaces", "interfaces"),
            ("--single-cases", "single_cases"),
            ("--biz-flows", "biz_flows"),
        ):
            val = getattr(args, key, None)
            if val:
                cmd += [flag, val]
        cmd += ["--output", args.output]
    return cmd, python_dir


def run_convert(args) -> int:
    """执行 convert 子命令。Run the convert subcommand."""
    config = load_config(args.config)
    set_lang(str(config.get("language") or "zh_CN"))
    try:
        cmd, python_dir = _build_convert_command(args, config)
    except RuntimeError as e:
        logger.error(str(e))
        return 2
    logger.info(_("tool.convert_start", command=" ".join(cmd)))
    res = _run_child(cmd, python_dir, 300)
    sys.stdout.write(_decode(res.stdout))
    sys.stderr.write(_decode(res.stderr))
    logger.info(_("tool.convert_exit", code=res.returncode))
    return res.returncode


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """添加通用参数。Add common arguments."""
    parser.add_argument("--config", default="", help="Path to flowforge.config.yaml")


def build_parser() -> argparse.ArgumentParser:
    """构造 CLI 解析器。Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Flow Forge skill tool")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    vp = sub.add_parser("validate", help="Validate YAML cases against the schema")
    vp.add_argument("--yamlDir", default="", help="YAML case directory (recursive)")
    vp.add_argument("--yamlFiles", default="", help="Comma-separated YAML file paths")
    vp.add_argument("--config-dir", default="", help="Directory of env.yml / env-{name}.yml")
    vp.add_argument("--env-name", default="", help="Environment name for processor config check")
    _add_common_args(vp)
    vp.set_defaults(func=run_validate)

    ep = sub.add_parser("execute", help="Run the executor on YAML cases")
    ep.add_argument("--yamlDir", required=True, help="YAML case directory (recursive)")
    ep.add_argument("--envName", default="", help="Environment name (default from config)")
    ep.add_argument("--apiMode", default="", choices=["", "single", "biz", "all"], help="API mode")
    ep.add_argument("--maxThread", type=int, default=0, help="Max threads")
    ep.add_argument("--timeout", type=int, default=0, help="Subprocess timeout in seconds")
    _add_common_args(ep)
    ep.set_defaults(func=run_execute)

    cp = sub.add_parser("convert", help="Convert cases between YAML and Excel")
    csub = cp.add_subparsers(dest="subcommand", required=True)
    y2x = csub.add_parser("yaml2excel", help="YAML to Excel")
    y2x.add_argument("--interfaces", default="", help="Interface YAML directory")
    y2x.add_argument("--single-cases", default="", help="Single case YAML directory")
    y2x.add_argument("--biz-flows", default="", help="Biz flow YAML directory")
    y2x.add_argument("--output", required=True, help="Output .xlsx path")
    _add_common_args(y2x)
    y2x.set_defaults(func=run_convert)
    x2y = csub.add_parser("excel2yaml", help="Excel to YAML")
    x2y.add_argument("--input", required=True, help="Input .xlsx path")
    x2y.add_argument("--output", required=True, help="Output YAML directory")
    _add_common_args(x2y)
    x2y.set_defaults(func=run_convert)
    return parser


def main(argv=None) -> int:
    """CLI 入口。CLI entry."""
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
