# iPhone-mcp

让 AI 通过 MCP 观察和控制真实 iPhone/iPad。独立 Git 项目，从 iPhoneMirror 的初版
MCP 适配器发展而来，复用 iPhoneMirror 本地 Automation API，不另建 USB/无线传输。

已在 Windows 上完成 Codex CLI → stdio MCP → 本地 API → USB iPhone 的实测，
验证了截图、OCR、点击、触控、文字、键盘和剪贴板。详细证据与能力对照见
[实测报告](docs/VALIDATION.md)和 [Windows MCP 能力对照](docs/WINDOWS_MCP_COMPARISON.md)。

## 让 AI 自动安装

把下面这段话和仓库地址交给 Codex 或其他能执行本地命令的 AI：

> 安装 https://github.com/RayrenSX/iPhone-mcp 。先读取 AGENTS.md 和 docs/SETUP.md，
> 自动检测依赖与 iPhoneMirror、执行配置、接入 MCP，并实际调用工具验证截图。
> 完成所有电脑端步骤；若需要手机连接、信任或解锁，再告诉我具体动作。

全新 Windows x64 环境，在已安装 Codex CLI 的情况下：

```powershell
git clone https://github.com/RayrenSX/iPhone-mcp.git
cd iPhone-mcp
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
```

脚本检测 Python，缺失时通过 winget 安装；没有运行中的兼容 iPhoneMirror 时，自动下载并
校验本仓库 `runtime-v0.2.1` 后台运行包。随后安装 MCP 依赖、注册 Codex，
通过 MCP 启动隐藏主窗口的应用、启用 API、准备投屏和反控，执行真实截图/OCR 诊断。
驱动安装改为命令行，AI 根据 `actionRequired` 提示连接、拔插 USB、解锁和管理员确认。
健康驱动直接跳过；缺失或异常组件由原生安装器诊断、安装或修复。完成后调用
`start_iphonemirror` 和 `snapshot` 验证。此流程需要包含 `driverSetupVersion: 1`
的新版原生驱动程序，`runtime-v0.2.1` 包含此入口和手机系统动作 API。
旧 runtime-v0.2.0 会返回升级要求，不打开 GUI。
实测证据见 [无界面驱动安装验证](docs/HEADLESS_DRIVER_VALIDATION.md)。
密钥留在当前用户 DPAPI，不写入 Codex 配置。
详细参数、主程序获取和排错见 [自动配置指南](docs/SETUP.md)。
手机连接、信任、解锁、开发者模式重启及 Windows 管理员确认仍可能需要人操作。
已有主程序可继续使用 `scripts/setup.ps1 -EnableAutomationApi`。

## 环境

- Python 3.11+；OCR 和本地密钥读取需要 Windows。
- 本仓库后台运行包；`start_iphonemirror` 自动启用本地 Automation API（默认 `127.0.0.1:17890`）。
- 已连接、信任的设备；MCP 自动准备投屏与反控，手机开发者模式等首次步骤仍需完成。
- Windows OCR 语言包；本机实测有 `en-US`、`zh-Hans-CN`。

从本项目目录安装：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e .
```

## Codex 接入

推荐上面的自动配置脚本；手动注册时替换下面的绝对路径：

```powershell
codex mcp add iphone-mcp -- C:/path/to/iPhone-mcp/.venv/Scripts/python.exe -m iphonemirror_mcp --local-key-store
codex mcp get iphone-mcp
```

`--local-key-store` 读取当前 Windows 用户的 iPhoneMirror DPAPI 密钥及设置端口。
密钥不写进 Codex 配置、不返回模型；只读取当前用户。后台应用负责创建密钥和启用 API。
显式环境变量 `IPHONEMIRROR_API_KEY` 和 `IPHONEMIRROR_API_URL` 可以覆盖上述配置。

通用 MCP 客户端 JSON：

```json
{
  "mcpServers": {
    "iphone-mcp": {
      "command": "C:/path/to/iPhone-mcp/.venv/Scripts/python.exe",
      "args": ["-m", "iphonemirror_mcp", "--local-key-store"]
    }
  }
}
```

新会话会读取新 MCP 配置；已启动会话需要刷新 MCP 连接或重新打开会话。
本机 Codex CLI 的只读测试可以截图、查询，控制工具因权限策略被拒绝；
Full access 测试成功完成获取控制、点击、再次截图与释放。不需要在项目中保存模型 API 密钥。

## 26 个工具

| 类别 | 工具 |
|---|---|
| 应用与窗口 | `start_iphonemirror`, `get_app_status`, `open_independent_window` |
| 设备 | `list_devices`, `get_device_status` |
| 图像与文字观察 | `screenshot`, `snapshot` |
| 控制租约 | `acquire_control`, `release_control` |
| 触控 | `tap`, `long_press`, `swipe`, `touch_path`, `touch_down`, `touch_up` |
| 类似桌面操作 | `click_element`, `scroll`, `drag`, `type_at` |
| 输入与剪贴板 | `press_key`, `press_shortcut`, `type_text`, `read_clipboard`, `write_clipboard` |
| 等待 | `wait`, `wait_for` |

推荐流程：`start_iphonemirror` → `list_devices` → `snapshot` → 检查能力/画面 → `acquire_control`
→ 一次输入 → 等待界面稳定 → `snapshot` 验证 → `release_control`。

MCP 握手和工具枚举不要求应用已打开或密钥已存在。调用 `start_iphonemirror` 后，
主窗口保持隐藏，默认不打开独立窗口；唯一在线设备自动准备，多设备必须指定 `device_id`。
只观察可传 `enable_control=false`。需要可见画面时调用 `open_independent_window(device_id)`；
先释放控制租约。`get_app_status` 可确认窗口/API 状态。关闭 MCP 连接不会结束独立窗口。
运行包及完整对应源码见 [runtime-v0.2.1](https://github.com/RayrenSX/iPhone-mcp/releases/tag/runtime-v0.2.1)。

`snapshot` 同时返回状态、OCR 文本框、截图与坐标变换；OCR 文本框不是 UI 可访问性节点。
可以选择原始像素区域、显示宽度、文字标注与网格；OCR 在原始完整截图上执行。
`click_element` 必须引用当前快照 ID 和文字框 ID，快照有效期 30 秒，点击前重新检查几何和文字位置。

所有触控使用原始截图像素（左上角原点）；`geometry_version` 来自 `status.geometry.version`。
裁剪/缩放显示时，按 `imageTransform` 换算：
`nativeX = offsetX + imageX * scaleX`，`nativeY = offsetY + imageY * scaleY`。
手机布局可能变化，操作后必须重新观察；几何版本并不表示画面内容不会改变。

`scroll` 的方向表示内容滚动方向：向下滚动时手指向上滑；距离为原始像素。
`drag` 是连续触摸路径，不能保证 iOS 原生拖放语义。`type_at` 点击后粘贴，不自动清空字段或提交。
`wait_for` 支持 OCR 文本出现/消失、图像变化以及在线/投屏/反控可用条件；不提供焦点或 enabled 语义。

输入前显式获取控制（5–300 秒，默认 30 秒），再次获取可续租，完成后释放。
正常关闭服务会尝试释放；强制终止则由应用端 TTL 回收。用户可从主程序收回控制。
`dispatched` 只证明传输已发送；超时不自动重试输入。
长按/滑动/轨迹时长为 0.05–10 秒，持有触点最多 10 秒。

`press_shortcut(device_id, shortcut)` 接入 iPhoneMirror 的手机系统快捷动作：
`home`（主屏幕）、`app_switcher`（App 切换器）、`control_center`（控制中心）、
`notification_center`（通知中心）、`dock`、`siri`、`volume_up`、`volume_down`、`lock_screen`。
需要控制租约和 `keyboard.input` 权限；先检查 `status.capabilities.shortcuts`。
它通过指定设备的原生路由执行，不修改电脑快捷键设置，也不依赖窗口焦点。
`home` 是手机主屏幕动作，`press_key(HOME)` 仍是键盘 Home。
锁屏可能中断截图；返回 `dispatched` 后仍需观察实际效果。
原始 `runtime-v0.2.0` 没有这个 API，可升级到 `runtime-v0.2.1`，或应用
[快捷动作运行时补丁](runtime-patches/README.md#phone-system-shortcuts)。

文字操作会使用手机剪贴板；iOS 可能弹出“允许粘贴”，处理完成前不要更改剪贴板或发送后续按键。
测试证据已捕获这个提示，并在允许后确认文本出现。截图和剪贴板会交给所用 AI 客户端。

## 验证

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
# 默认只观察真实设备，不发送输入
.venv/Scripts/python.exe scripts/probe.py --output artifacts/probe
```

`scripts/plans/*.json` 是本机测试用的显式输入计划，坐标针对 1082×2340 的实测设备，
其中手机需已打开 iPhoneMirror 的触摸观察页或指定 Safari 地址编辑界面。
先观察并核对画面，再运行对应计划；不要在其他页面直接复用测试坐标。
原始截图和 Codex 调用日志保存在被 Git 忽略的 `artifacts/`，可能含设备身份和屏幕内容。

暂不提供任意 shell、iOS 注册表、全系统文件访问、应用生命周期、可访问性树或组合快捷键。
USB 实测不代表无线/BLE 或多设备输入已经验证。完整能力对照见报告。
