# 干净 Windows 首次使用测试

2026-10-10，在本机创建独立 VirtualBox Windows 11 企业评估版虚拟机，
验证首次安装与真实 stdio MCP 调用。结果：安装与 MCP/API 接入通过，
USB 真机采集失败，未完成“零驱动 Windows → 截图与控制可用”的全流程。

## 干净起点

Windows 镜像来自 Microsoft，直连下载并核对官方 SHA256。虚拟机使用独立本地用户，
没有复制宿主机的配对、设备身份、应用设置、API 密钥或客户端认证。
安装 iPhone 组件前检查得到 `clean=true`：

- 没有运行中的 iPhoneMirror，也没有应用或运行包用户目录。
- 没有安装本仓库源码、MCP 或 Codex CLI。
- Apple/iPhone/采集过滤驱动数量为 0，驱动存储也没有相关包。

已保存 `clean-windows-no-iphone-components` 快照。
基线 `pythonPresent=true` 只表示命令可发现，包含 Windows 应用执行别名，
不能证明有可用解释器；测试随后独立安装了 Python 3.13。

## 已验证结果

| 阶段 | 实测结果 |
|---|---|
| Python 与 MCP 安装 | Python 首次安装遇到 MSI 1618 并回滚；重试后成功，独立 venv 安装与 pip check 通过 |
| 第一次直接 MCP 调用 | 官方 MCP SDK 的真实 stdio 会话握手成功，枚举 26 个工具 |
| 第一次 `start_iphonemirror` | 返回 `RUNTIME_NOT_INSTALLED`；工具本身不会下载运行包，需要 bootstrap |
| bootstrap 直连 | 获取 GitHub 校验清单时连接关闭 |
| bootstrap 代理重试 | 清单可用；curl 下载 ZIP 遇到 `CRYPT_E_REVOCATION_OFFLINE` |
| 下载绕行后 bootstrap | curl 对离线吊销服务使用 `--ssl-revoke-best-effort` 下载；bootstrap 仍核对发布包 SHA256，安装成功 |
| 配置与后台启动 | 生成无密钥 MCP JSON，隐藏应用启动成功，API 可连接 |
| 未连接手机时诊断 | `ready=false`、设备列表为空，提示连接/解锁/信任；不能记为真机通过 |
| USB 直通 | 单一 iPhone 接入虚拟机，Windows 已枚举 Apple iPhone 和 USB 复合设备 |
| 驱动管理器 | 手动刷新后识别设备；人工确认 UAC 后 Apple USB 支持与采集过滤驱动安装成功 |
| 过滤驱动安装日志 | `install-filter` 退出 0，`filter_install_verified`，`success=True`、`requires_replug=True` |
| 安装后 USB 重新枚举 | VirtualBox 原连接失效，重新接入并增加仅匹配该手机的精确直通规则 |
| 人工手机步骤 | 用户已解锁并实体拔插 USB，没有出现信任提示；VirtualBox 日志确认重新接入 |
| 安装后设备准备 | MCP/API 可用，但截图未成功，`controlReady=false` |
| 原生采集错误 | `UsbConnection / DeviceReenumeration / -2102`：QuickTime 激活时设备移除，但精确接口未在超时前返回 |
| 重启虚拟机复查 | Windows 正常枚举 Apple USB/WPD；Apple Mobile Device Service 运行，27015 端口监听；只读配对探测返回 `apple_device_not_found`，MCP 设备列表为空 |

代理仅用于 GitHub 运行包下载；没有修改虚拟机系统代理。测试过程中宿主机已有的
iPhone 驱动没有卸载或重装。VirtualBox 安装了自身 USB 支持。

## 失败边界与尚未验证

在已完成驱动安装、实体重连及虚拟机重启后，采集仍未可用。
错误发生在 USB 配置切换/接口重新枚举阶段；证据指向 VirtualBox 直通兼容性，
但本测试不足以断定物理干净 Windows 上也会失败。不要把虚拟机失败归因于
用户未解锁或未确认 UAC，也不要把宿主机现有驱动的成功当作干净环境通过。

尚未验证虚拟机真实截图、OCR、输入控制或系统动作效果。没有发送手机输入。
没有在虚拟机验证 Codex 模型的实际工具调用；当前只验证真实 stdio 客户端。

公开 `runtime-v0.2.0` 不包含新增的手机系统动作 API。
干净安装使用公开包，不能用宿主机补丁运行时的动作测试结果替代。

原始日志与基线 JSON 位于 Git 忽略的 `artifacts/clean-first-use-vm/`。
虚拟机凭据、设备身份、配对与截图不随报告提交。

测试结束后正常关闭虚拟机，并停用精确 USB 自动捕获规则。干净快照与安装后磁盘
均保留以便复查；手机已回到宿主机，宿主机实际 MCP 截图再次成功。
这项恢复检查只证明宿主机观察可用，不计入干净虚拟机的通过结果。
