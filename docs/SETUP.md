# AI 自动配置与排错

把 GitHub 地址交给 AI，并要求它读取根目录 AGENTS.md、完成安装和真实验证。
脚本不依赖创建者电脑上的目录，不依赖 windows-mcp，也不需要复制 API Key。

## 快速开始

没有用过 iPhoneMirror 的用户也从本仓库开始。支持 Windows 10/11 x64（ARM64 不支持）。
已有 Codex CLI 时，运行：

```powershell
git clone https://github.com/RayrenSX/iPhone-mcp.git
cd iPhone-mcp
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/bootstrap.ps1 -OpenDriverManager
```

不想安装 Git，可在 GitHub 选择 Code → Download ZIP，完整解压后进入目录执行同一命令。
Bootstrap 会检测 Python 3.11+；缺少时通过 winget 安装 Python 3.13。
没有运行中的主程序时，它会下载 **iPhoneMirror v1.8.5-pre2 官方便携版**（约 203 MiB），
按同一 Release 的 SHA256SUMS.txt 校验完整性，完整解压到
`%LOCALAPPDATA%/iPhone-mcp/runtime/v1.8.5-pre2/app` 并启动。
当前正式版 v1.8.3 没有 Automation API，因此不能使用 GitHub 的 latest 正式版链接。
Bootstrap 使用正在运行的主程序，不关闭或替换它；旧版缺少 API 时先正常退出再重跑。

随后创建 .venv、安装依赖并注册 Codex MCP。脚本通过 Windows UI Automation
连续调用版本按钮五次，开启开发者面板、勾选 API 并应用。
保持既有端口，不重新生成密钥，不操作手机内容。需要可交互的 Windows 桌面；
锁屏、远程无桌面或不同权限级别可能无法操作 UI，可在主程序手工打开开发者面板后重试。

没有 winget 时从 python.org 安装 Python 3.13，再用 `-Python '绝对路径/python.exe'` 指定。
没有 Codex CLI：给 bootstrap 增加 `-SkipCodex`，
导入生成的 `artifacts/mcp-config.json`；Codex 安装方式以官方说明为准。
下载网络失败可指定 `-Proxy 'http://127.0.0.1:你的代理端口'`，只用于主程序下载，不修改系统代理。
`-SkipDoctor` 仅配置，不表示设备验证通过。可重复执行安装脚本，注册同名 MCP 会更新其命令。
已有兼容主程序：直接运行 `scripts/setup.ps1 -EnableAutomationApi`；
指定路径可用 bootstrap/setup 的 `-MirrorPath 'D:/apps/iPhoneMirror/iPhoneMirror.exe'`。

## 首次连接手机：必须完成的准备

1. 用能传输数据的 USB 线连接 iPhone，解锁，在手机点“信任此电脑”并输入锁屏密码。
2. Bootstrap 的 `-OpenDriverManager` 会打开驱动管理器。也可从主程序左侧“驱动”进入。
   确认当前手机后点 **“一键安装全部驱动”**，按 Windows 提示确认管理员权限。
   它检查并补齐 Apple USB 支持和设备采集过滤驱动，不需要自行寻找驱动包。
   驱动安装涉及系统变更，bootstrap 不在后台静默执行这一步；已有正常链路无需重装。
3. 在主程序刷新/选择手机，点击 **“开始投屏”**，确认有画面。
4. 要让 AI 点击/输入，再开启 **“有线控制”**，按提示绑定设备、开启 iPhone 开发者模式，
   必要时重启并再次确认。主程序首次会下载并挂载匹配的 DDI，需网络。
   只投屏不代表反控已经可用。
5. 运行 `.venv/Scripts/python.exe scripts/doctor.py`，检查 ready、controlReady 和 ocr。
   Bootstrap 在手机准备完成前的诊断失败是待完成状态，不等于 MCP 安装失败。
6. 打开新的 Codex 会话，调用 list_devices / snapshot 验证。先观察再执行具体控制任务。

AI 可自动准备依赖、下载主程序、启动界面并配置 MCP；USB 插线、手机解锁/信任、
开发者模式重启和 Windows 安全桌面的 UAC 提示需要用户完成。驱动/反控失败时
使用主程序“关于 → 诊断”，不要使用 Zadig 替换 Apple 父驱动。

AirPlay 观察无需 USB 驱动，但要同一局域网并在手机选择屏幕镜像；输入另需受支持的
无线或蓝牙控制连接。初次使用优先按上面已实测的 USB 路径操作。

## 获取主程序

主程序：[RayrenSX/iPhoneMirror](https://github.com/RayrenSX/iPhoneMirror)。
Bootstrap 固定使用已含 API 的
[v1.8.5-pre2 预览版](https://github.com/RayrenSX/iPhoneMirror/releases/tag/v1.8.5-pre2)，
不自动追逐未经此项目验证的新版本。安装说明见主程序 docs/USER_GUIDE.md。
**MCP 不携带主程序、USB 驱动或无线运行库。**
如果已发布版本没有 API，需要从该项目支持 API 的源码构建；读取其
docs/DEVELOPMENT.md 并按该仓库的构建脚本执行，不要仅安装 MCP 后宣称接通。
本项目已实际下载、校验并启动 v1.8.5-pre2 官方 ZIP，完成截图、OCR 和反控可用诊断；
不能据此保证旧 Release 都支持 API。

USB 驱动配置、手机信任、投屏和反控连接使用主程序流程。手机需要物理连接/解锁时，
AI 应在完成电脑端配置后说明具体缺少的动作。不要通过修改运行中 settings.json 绕过应用。

## 诊断

```powershell
.venv/Scripts/python.exe scripts/doctor.py
codex mcp get iphone-mcp
```

诊断实际启动 stdio MCP、握手、枚举工具和设备，读取状态，获取截图并尝试 OCR。
JSON 不输出设备 ID、画面文字或密钥，不保存截图，也不申请控制/发送输入。
`ready=true` 和退出码 0 表示至少一台设备截图成功；`controlReady` 表示对应设备报告
反控可用，仍需实际输入任务验证效果；`ocr` 表示 OCR 请求成功，不要求屏幕必须有文字。
退出码 2：API/设备未就绪。查看 failedStage 和 action：

| 现象 | 处理 |
|---|---|
| mcp_start | 检查 DPAPI 密钥属于当前用户，API 已在主程序启用；重跑 setup 安装依赖 |
| api_devices | 检查主程序进程、API 监听端口、密钥/端口是否被环境变量覆盖 |
| devices 为空 / screenshot=false | 在主程序连接设备、信任电脑并开始投屏 |
| controlReady=false | 在主程序建立受支持的 USB/BLE 反控连接，不能从截图推断可控制 |
| ocr=false | 安装 Windows OCR 语言包；可用 snapshot(use_ocr=false) 观察 |
| Codex 不显示工具 | 开新会话/刷新 MCP 连接；全局注册不会即时改变已启动会话的工具列表 |
| 输入被拒绝 | 根据用户任务在客户端选择允许设备输入的权限策略；安装脚本不修改权限策略 |

密钥读取：当前用户 `%LOCALAPPDATA%/iPhoneMirror/automation-key.bin`，Windows DPAPI。
环境变量 IPHONEMIRROR_API_KEY / IPHONEMIRROR_API_URL 可覆盖；避免把密钥写入仓库或日志。
端口默认 17890，默认从本地 settings.json 读取。只接受 localhost/127.0.0.1 HTTP origin。
