# AI 自动配置与排错

把 GitHub 地址交给 AI，并要求它读取根目录 AGENTS.md、完成安装和真实验证。
脚本不依赖创建者电脑上的目录，不依赖 windows-mcp，也不需要复制 API Key。

## 快速开始

```powershell
git clone https://github.com/RayrenSX/iPhone-mcp.git
cd iPhone-mcp
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -EnableAutomationApi
```

前提：Python 3.11+、Codex CLI，以及正在运行、支持 Automation API 的 iPhoneMirror。
主程序未启动时可增加 `-MirrorPath 'D:/apps/iPhoneMirror/iPhoneMirror.exe'`。
脚本通过 Windows UI Automation 连续调用版本按钮五次，开启开发者面板、勾选 API 并应用。
保持既有端口，不重新生成密钥，不操作手机内容。需要可交互的 Windows 桌面；
锁屏、远程无桌面或不同权限级别可能无法操作 UI，可在主程序手工打开开发者面板后重试。

没有 Python：用 winget 安装 Python.Python.3.13，或从 python.org 安装，再用
`-Python '绝对路径/python.exe'` 指定。没有 Codex CLI：使用 `-SkipCodex`，
导入生成的 `artifacts/mcp-config.json`；Codex 安装方式以官方说明为准。
`-SkipDoctor` 仅配置，不表示设备验证通过。可重复执行安装脚本，注册同名 MCP 会更新其命令。

## 获取主程序

主程序：[RayrenSX/iPhoneMirror](https://github.com/RayrenSX/iPhoneMirror)。
优先使用具有开发者面板 Automation API 的官方发布包；下载后验证同一 Release 的
SHA256SUMS.txt，完整解压或运行安装包。安装说明见主程序 docs/USER_GUIDE.md。
**MCP 不携带主程序、USB 驱动或无线运行库。**
如果已发布版本没有 API，需要从该项目支持 API 的源码构建；读取其
docs/DEVELOPMENT.md 并按该仓库的构建脚本执行，不要仅安装 MCP 后宣称接通。
本项目实测使用的是带 Automation API 的本地构建，不能据此保证每个旧 Release 都支持。

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
