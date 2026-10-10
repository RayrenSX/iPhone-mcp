# 2026-10-10 本机直接验证

测试时间使用 Asia/Shanghai。测试对象为真实 USB iPhone，原始投屏尺寸为 **1082×2340**。
第二台 USB 设备被枚举到，但没有启用投屏或反控，未向其发送输入。

## 已确认的结果

本次 GitHub 发布前还实际执行了 `scripts/setup.ps1 -EnableAutomationApi`：
Windows PowerShell 5.1 通过主程序 UI 启用 API、安装包、检查依赖、更新 Codex 注册，
随后 stdio 诊断枚举 22 个工具，第一台设备截图 1082×2340、中文 OCR 和反控可用检查通过。
安装脚本重复执行两次均通过。第二台设备保持未投屏，诊断正确报告 screenshot=false。
发布前自动测试共 22 项（原 17 项加 5 项诊断就绪/隐私检查），wheel 构建通过。
原始设备身份与截图不发布。

| 验证项 | 直接证据 |
|---|---|
| Codex 发现 MCP | `codex mcp get iphone-mcp` 显示已启用 stdio，入口为独立项目 venv；配置不含明文密钥 |
| Codex 真实查询 | Codex CLI 会话调用 `list_devices`、两次 `get_device_status`、`screenshot`，得到两台设备和真实 Safari 图像 |
| Codex 真实操作 | Full access 测试调用 `snapshot → acquire_control → tap → wait → snapshot → release_control`；手机页面新增 `touchstart 1` 和 `touchend 0 []` |
| 点击/长按 | 手机已有的 Five-point hardware test 页面更新触摸日志；输入后保存截图 |
| 滑动/轨迹/拖动 | 截图中 touchmove 的触点编号随每个新手势变化；并非仅根据 API `dispatched` 判成功 |
| 按住/释放 | `touch_down` 后截图显示活动触点 1，`touch_up` 后显示活动触点 0，并增加 touchend |
| 原图/裁剪/缩放 | 原图 1082×2340；裁剪 [0,0,1082,1100] 后输出 800×813，返回独立 scaleX/scaleY |
| 英文/中文 OCR | Windows 当前安装 en-US、zh-Hans-CN；成功识别测试页面与中文 iOS 粘贴许可提示 |
| OCR 点击 | `click_element` 命中 `192.168.137.1`，实际打开 Safari 地址编辑界面；加入点击前重识别后再次真机验证通过 |
| 文本 | `type_text` 发出粘贴后出现 iOS Allow Paste；通过截图处理许可后，地址栏可见 `iphone-mcp-20261010`，未提交搜索 |
| 单键 | `BACKSPACE` 后可见 `iphone-mcp-2026101`；`ESCAPE` 已发送但没有关闭 Safari 地址编辑，不能声称其实现“取消编辑” |
| `type_at` | 聚焦+粘贴后再次出现许可；允许后画面可见 `iphone-mcp-type-at`，未提交搜索 |
| 剪贴板 | 写入测试文本后从手机读回相同文本；本轮读写恢复到该轮开始值，不涉及 Windows 剪贴板 |
| 条件等待 | `wait_for(text_exists, touchend)`、`wait_for(control_available)` 返回匹配；未声称所有条件都做过真机测试 |
| 自动测试 | 17 项通过：真实 stdio 握手、mock API、凭据隔离、无重试、截图格式、几何变化、裁剪变换、旧 OCR 框拒绝、组合输入部分失败 |

原始证据存于本机被 Git 忽略的 `artifacts/`：

- `codex-smoke.jsonl` / `codex-smoke-summary.txt`：首次直接 Codex 查询与截图。
- `codex-live-full-access.jsonl` / `codex-live-full-access-summary.txt`：Codex 真机操作与截图确认。
- `touch-observer/report.json`：点击、长按、滑动、轨迹、滚动和拖动的 MCP 测试计划结果。
- `held-touch/03-snapshot.png`、`06-snapshot.png`：按下与释放的真实画面。
- `focus-address-rechecked/`：加上文字位置重验证后的 OCR 点击结果。
- `allow-paste/`、`text-probe/`：许可提示、文本与退格结果；`text-probe/report.json` 为机器可读布尔验证。
- `type-at-permission/04-snapshot.png`：`type_at` 的真实插入结果。
- `final-state/`：取消地址编辑，恢复原有触摸测试页的截图。
- `codex-project.json`：通过当前 CLI 提供的 `project/create` 注册独立 Codex 本地项目的响应。

设备 opaque ID 可能包含来源身份信息，原始 Codex/HTTP 测试日志只留在忽略目录，
不要直接公开整份日志或个人屏幕截图。

## 实测中发现的条件

首次 CLI 验证在 `read-only` 下，查询与截图成功，`acquire_control` / `release_control`
被 CLI 权限策略拒绝：`MCP tool call requires approval, but approval policy is never`。
没有因此改弱 MCP 工具的副作用标注。随后在用户已授权的 Full access 测试会话中成功，
MCP、API 的权限及独占控制仍正常生效。未修改用户的全局 approval policy。

Codex 测试会话还调用了资源枚举（返回空列表），其摘要明确记录了这一额外调用；
不影响实际 MCP 工具调用证据，但不应宣称“仅调用了列出的七个工具”。

OCR 英文包未识别中文“允许粘贴”按钮，单凭英文 OCR 没有检测到该提示；
通过实际图像确认，再用中文 OCR 提供文字证据。OCR 可以把数字 0 和字母 O、
触点编号或页面图标识别错，不能作为完整语义树或触摸计数的唯一证明。

当前页面的系统栏固定显示 9:41；这不是测试时间，不能据此推断图像来源或实时性。
每次输入后触点编号和日志变化提供了设备响应证据。

测试粘贴会替换手机剪贴板。本次首次粘贴许可期间中止了测试，跨进程恢复时没有保存
最初用户剪贴板内容，故不能声称已恢复到首次测试前的用户内容。后续测试值已记录为
`iphone-mcp-20261010` / `iphone-mcp-type-at`。测试脚本现已增加当前用户 DPAPI 备份，
跨许可提示继续时可恢复原值；只有仍包含本次测试值时才恢复，避免覆盖用户后续复制。

未向其他应用提交文本/消息，没有通过 Safari 发起测试词的搜索；最后退出地址编辑。
Automation API、有线反控和投屏保留启用，MCP 控制租约在每个显式测试的 finally 中释放。

## 没有验证或没有实现

- 无线/BLE 输入、多设备并发控制、旋转或分辨率变化时的真机行为。
- 语义可访问性树、元素 enabled/focused、前台应用 bundle ID、应用启动/终止。
- iOS 系统日志、任意 shell、注册表、全系统文件和进程接口。
- modifier 组合键、真正 iOS 长按拖放、页面滚动距离精度。
- `wait_for` 的所有分支真机覆盖；图像变化仅是像素差异，可能受时钟/动画影响。

Windows MCP 的完整能力对照与原因见 [WINDOWS_MCP_COMPARISON.md](WINDOWS_MCP_COMPARISON.md)。
