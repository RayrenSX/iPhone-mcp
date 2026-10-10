# Windows MCP 能力迁移研究

核对的是本机已安装且可调用的 Windows MCP：
`%LOCALAPPDATA%/Programs/WindowsMCP/venv/Lib/site-packages/windows_mcp`。
并非仅凭工具名设计。本次读了 `tools/input.py`、`tools/snapshot.py`、
`tools/_snapshot_helpers.py`、`tools/app.py` 等入口，且用实际 Snapshot、App、Click
观察并操作了 iPhoneMirror Windows 界面。

没有复制 Windows MCP 源码。独立项目继续遵循源项目 iPhoneMirror 的 GPL-3.0-only。

## 对照

| Windows MCP 工具 | iPhone 对应 | 实现条件/验证边界 |
|---|---|---|
| Screenshot | `screenshot` | 真机原始 PNG；不是桌面窗口截图，已验证 |
| Snapshot | `snapshot` | 状态、截图、裁剪、缩放变换、网格、Windows OCR；没有 iOS UIA 树 |
| Click | `tap`, `click_element`, `long_press` | 原始像素点击或 OCR 框中心；实测聚焦 Safari 地址框，点击前重识别文字 |
| Type | `type_text`, `type_at` | 通过已有手机 pasteboard 粘贴；实测遇到 iOS 许可提示，允许后可见文本 |
| Scroll | `scroll` | wheel 改为 touch swipe；真机触摸轨迹已验证，页面滚动距离不等价于 wheel 次数 |
| Move | `drag`, `touch_path` | 连续触控路径已验证；不提供鼠标 hover，不保证长按后的 iOS 拖放会话 |
| Shortcut | `press_key`, `press_shortcut` | 单键已验证；手机系统快捷动作经补丁接入，按租约调用指定设备原生路由；不接受任意 modifier chord |
| Clipboard | `read_clipboard`, `write_clipboard` | 手机纯文本读写已验证，不操作 Windows 剪贴板；受 API scopes 限制 |
| Wait | `wait` | 异步等待，限制 30 秒，不续租 |
| WaitFor | `wait_for` | OCR 文本出现/消失、图像变化、连接能力；已实测文本和反控可用，没有 UIA 焦点/启用状态 |
| DisplayInventory | `list_devices`, `get_device_status` | 多个手机来源、原始帧几何及坐标空间已验证；无 Windows DPI/显示器概念 |
| App | 目前需视觉导航 | 可点击现有图标/界面，但无按 bundle ID 启动、前台应用元数据、resize 或终止应用接口 |
| MultiEdit | 暂不暴露 | 可由 AI 按字段逐步调用 `type_at`；遇到 Allow Paste/焦点变化需重新观察，不能可靠盲批处理 |
| MultiSelect | 暂不暴露 | 手机 UI 选择语义不同；单联系人/多触点不等于文件 Ctrl 多选，未验证 |
| PowerShell | 不迁移 | Windows shell 在主机执行，不能代表 iPhone shell；当前传输没有 iOS shell 能力 |
| FileSystem | 不迁移全系统访问 | 需要单独 AFC/应用容器访问契约和权限；现有 API 没有文件端点 |
| Process | 不迁移 | iOS 进程枚举/终止需额外服务，不能映射到主机进程 |
| Registry | 无直接对应 | iOS 没有 Windows Registry；不暴露主机注册表作为手机工具 |
| Notification | 暂不提供 | Windows toast 不等于手机通知；当前传输无 iOS 通知接口 |
| Scrape | 暂不提供手机 DOM | 主机 HTTP 抓取不能证明 Safari 当前 DOM/session；OCR 可观察屏幕，不能伪装成 DOM |

## 实现差异

Windows MCP 的元素 ID 来自 Windows UI Automation / 浏览器树。本项目 `element_id`
来自当前原始截图的 OCR 文本行，明确带 `source: ocr`，不能判断该文字是否为可点击按钮。
引入快照 ID、30 秒有效期、几何检查及点击前重新识别，是为了避免复用错位的文字框。

Windows MCP 会限制输出图像尺寸，因此显式给出坐标缩放比例。
本项目保留原始 screenshot，并让 snapshot 返回独立 `scaleX/scaleY` 与裁剪偏移，
避免四舍五入后的宽高比例被误当成一个完全相同的系数。

Windows MCP 的滚动属于鼠标 wheel。本项目的滚动由一次滑动执行，内容方向与手指方向相反，
超出帧边界的端点直接拒绝，避免自动裁切产生与请求不符的操作。

Windows MCP 的 modifier shortcuts 不能直接替换为多次单键。
iPhoneMirror 手机系统动作已通过补充运行时的 `/input/shortcut` 接入，支持主屏幕、
App 切换器、控制中心、通知中心、Dock、Siri、音量增减和锁屏。
MCP、原生模拟路由和失败/取消释放已有测试；这些测试不代表每项动作的真机 UI 效果均已验证。
它们沿用控制租约、每设备输入锁和键盘会话锁；有线 App 切换器复用两次 Home 脉冲，
有线控制中心等动作保持 Globe consumer 报告和普通键盘 usage 重叠。
后续若增加组合键，应在现有设备输入仲裁中增加原子 modifier+usage 请求、测试释放和取消，
再在 MCP 层暴露；不应绕过主程序的独占控制租约。
