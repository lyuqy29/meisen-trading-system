# 看板开机自启（Windows）

目标：每次登录 Windows 后，自动在后台启动看板 `http://127.0.0.1:8777`，不弹黑窗、不需要管理员权限。

## 现在的状态

| 项目 | 值 |
|---|---|
| 机制 | 当前用户注册表 Run 键（`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`） |
| 值名 | `liuliu-trading-dashboard` |
| 值 | `"C:\WINDOWS\System32\wscript.exe" "D:\deepseek_harness\repos\liuliu-trading-system\dashboard\run-hidden.vbs"` |
| 触发 | 当前用户登录时 |
| 窗口 | 隐藏（wscript 以 style 0 拉起 cmd，python 继承无控制台） |
| 日志 | `dashboard\logs\dashboard.log`（UTF-8，直接追加） |

## 启动链路

```
登录
 └─ HKCU\...\Run → wscript.exe run-hidden.vbs      （无窗口）
      └─ cmd.exe /c start-hidden.cmd               （无窗口，输出重定向到日志）
           └─ start.cmd                            （找 Python、查端口占用）
                └─ python -u server.py             （127.0.0.1:8777）
```

关键点：

- **幂等**：`start.cmd` 先探一次端口，已在服务就打印 `[i] already running` 并退出，不会重复绑定。
- **不依赖固定 Python 路径**：依次尝试 `DSH_PYTHON` → `%USERPROFILE%\.dsh\dsh-runtimes\*\dependencies\python\python.exe` → `py -3` → `python`。DSH 升级换运行时也能找到。
- **日志可追**：自启失败时先看 `logs\dashboard.log`，里面有 Python 版本、端口和 traceback。
  读法：`Get-Content -Encoding UTF8 .\logs\dashboard.log -Tail 30`

## 为什么用 Run 键，而不是计划任务 / 启动文件夹

实测这台机器上：

| 机制 | 结果 |
|---|---|
| 计划任务 `schtasks /SC ONLOGON` | `Access is denied` —— 登录触发器需要管理员权限 |
| 启动文件夹快捷方式 | 需要在 `%APPDATA%\...\Startup` 写文件（DSH 沙箱内被拒；普通终端可写） |
| `HKCU\...\Run` 注册表值 | ✅ 可用，无需管理员，登录即触发 |

安装器三种都支持，`auto` 模式按 `Task → Run → Startup` 顺序尝试，谁成功用谁。

## 操作

```powershell
cd D:\deepseek_harness\repos\liuliu-trading-system\dashboard

# 安装（默认 auto，实测会落到 Run 键）
powershell -ExecutionPolicy Bypass -File .\install-autostart.ps1

# 指定机制
powershell -ExecutionPolicy Bypass -File .\install-autostart.ps1 -Method Run

# 查看当前装了什么
powershell -ExecutionPolicy Bypass -File .\install-autostart.ps1 -Status

# 立刻测试一次（不用重启；已在运行则自动跳过）
wscript.exe .\run-hidden.vbs

# 卸载
powershell -ExecutionPolicy Bypass -File .\install-autostart.ps1 -Uninstall
```

手工删除（如果脚本不在手边）：

```powershell
Remove-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'liuliu-trading-dashboard'
```

## 停掉正在跑的实例

```powershell
# 看谁占着 8777
netstat -ano | findstr :8777
# 按 PID 杀
Stop-Process -Id <PID> -Force
```

## 注意

- 自启的是「看板 Web 服务」，不含 DSH 自身；浏览器标签页需要你自己打开。
- 只监听 `127.0.0.1`，局域网内其他机器访问不到；要对外请看 `server.py` 里的绑定地址（改前想清楚风险）。
- `logs\dashboard.log` 只追加不清空；嫌大就定期删（删除后下次写入会重新创建）。
- 重装仓库或换目录后，Run 键里的路径会失效，重跑一次 `install-autostart.ps1` 即可。
