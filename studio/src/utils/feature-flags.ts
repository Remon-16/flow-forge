/**
 * 诊断工具开关 — 正式发布时设为 false 即可隐藏计数器入口及路由。
 * Diagnostics toggle — set to false for release to hide the counter entry and route.
 *
 * 控制范围 / Scope:
 * - HomePage.vue 中的诊断卡片 / Diagnostic card in HomePage
 * - router 中的 /counter 路由 / /counter route in router
 */
export const ENABLE_DIAGNOSTICS = true

/** 允许在非 Windows 平台上 spawn 子进程（测试用途，默认关闭）。
 *  Allow spawning subprocesses on non-Windows platforms (for testing, disabled by default).
 *  开启后配合 Linux prctl / macOS kqueue 守护进程实现进行验证。
 *  Enable to test Linux prctl / macOS kqueue guardian implementations. */
export const ENABLE_NON_WINDOWS_SPAWN = false
