# 绘图工具

采用 PlantUML 1.2026.9 和 diagrams.net Desktop（draw.io）32.6.10。版本、官方发布地址与本次工具文件的 SHA-256 存放在 `versions.json`。

本地已放置 `plantuml.jar` 和 `drawio/`，可直接离线重绘。工具运行文件、下载缓存已由 `lab2/.gitignore` 排除，不上传 GitHub；draw.io.exe 单文件约 246 MB，超过 GitHub 普通文件的 100 MiB 限制。保留工具自带的许可文件，不改动第三方程序。

在新的 Windows 环境中，先安装 Python 3.10+ 与 Java（本次使用 Java 23），再从 `lab2` 目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File tools/install.ps1
```

脚本只在本目录下载并解压官方工具，不修改系统设置。也可以加 `-Tool PlantUML` 或 `-Tool Drawio` 单独准备某个工具。下载后按记录的 SHA-256 校验；已存在且匹配的文件直接复用。若官方资产与记录不一致，脚本停止，不跳过校验。

手动安装时使用 `versions.json` 中的官方地址：将 PlantUML JAR 放到 `tools/plantuml.jar`，将 draw.io 的 Windows 免安装包解压到 `tools/drawio/`，确保存在 `tools/drawio/draw.io.exe`。中文字体采用 Windows 微软雅黑；其他系统或版本可能改变图的布局。

工具官网与许可信息：[PlantUML](https://plantuml.com/zh/)（本次使用官方 GPL 发行包）、[diagrams.net](https://www.drawio.com/) 与 [drawio-desktop](https://github.com/jgraph/drawio-desktop)（Apache-2.0；Electron/Chromium 许可随本地工具保留）。
