# 屏幕观察模式

`start_iphonemirror` 提供两个模式，AI 根据任务在 `capture_mode` 中选择：

| 模式 | 工作方式 | 优点 | 缺点 | 适合场景 |
|---|---|---|---|---|
| `on_demand`（默认） | 不建立持续视频流，需要观察时通过 USB 控制通道请求一张 PNG | 空闲时省去视频传输、解码和帧缓存工作 | 每次观察需要设备截图往返；需要按需截图补丁、USB、Developer Mode 和 DDI | 动作前后确认画面、低频 OCR、减少后台视频开销 |
| `continuous` | 建立持续采集会话并保留最新视频帧 | 截图可读取已有帧；适合高频观察和动画检测；可打开独立预览；兼容旧运行时 | 观察间隙仍有视频传输、解码和帧缓存开销 | 高频读取画面、跟踪动画、等待画面变化或打开投屏预览 |

上述开销和响应差异来自工作方式，尚未量化 CPU、内存、耗电或截图延迟。两种模式启动时都隐藏窗口；持续采集也可以完全在后台运行。单次快照和 OCR 不是连续视频分析，仍可能错过两次观察之间的短暂画面。

MCP 工具默认 `on_demand`；安装脚本为了兼容当前发布运行包，默认显式选择 `continuous`，也可通过 `-CaptureMode on_demand` 安装补丁运行包。安装时会显示所选模式，之后用户仍可以通过 AI 切换。

用户可以直接对 AI 说：

- “用按需截图模式，保留控屏。” → `capture_mode="on_demand"`
- “切到持续采集模式，方便频繁看画面。” → `capture_mode="continuous"`
- “帮我选，主要是偶尔截图、点击和输入。” → AI 简述取舍并选择 `on_demand`。

AI 优先遵循用户选择；没有偏好时再按任务选择，缺少按需截图支持时说明原因，不静默改用持续采集。切换前释放控制租约，切回按需模式前关闭该设备预览；启动后检查返回的 `capture_mode`、设备状态和新快照。

AI 选择规则：只需要在动作前后确认画面时用 `on_demand`；需要每秒多次观察、跟踪动画或实时预览时用 `continuous`。两种模式都支持直接控制手机，都必须先取得控制租约；截图或视频帧只证明观察结果，输入仍需新鲜几何和效果验证。

启动示例：

```json
{"capture_mode":"on_demand","enable_control":true}
```

```json
{"capture_mode":"continuous","enable_control":true}
```

按需模式准备成功时，设备状态应为 `capturing=false`、`capabilities.screenshot=true`；持续模式应为 `capturing=true`。调用 `open_independent_window` 会请求可见预览并切换到持续采集，关闭预览后重新调用 `start_iphonemirror(capture_mode="on_demand")` 才会回到按需模式。当前按需模式仅支持 USB；无线观察需使用运行时支持的持续采集连接。
