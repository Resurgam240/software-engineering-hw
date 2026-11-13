# 实验二：软件设计与建模

```text
lab2/
├── README.md
├── .gitignore
├── tools/                  # 工具版本、官方安装脚本及本地运行文件
│   ├── README.md
│   ├── versions.json
│   ├── install.ps1
│   ├── plantuml.jar        # 仅本地，Git 忽略
│   └── drawio/             # 仅本地，Git 忽略
├── UML/                    # 4 张最终图及同名 PlantUML 源码
│   ├── UML类图.png / UML类图.puml
│   ├── UML组件图.png / UML组件图.puml
│   ├── UML用例图.png / UML用例图.puml
│   └── UML时序图.png / UML时序图.puml
├── UI界面/                 # 界面1.png ～ 界面7.png
└── src/
    ├── design.json         # 项目配色与绘图配置
    ├── build_ui.py         # 生成七张 UI 的可编辑源文件和 SVG
    ├── render.py           # 调用官方工具导出 UML/UI 的 PNG
    └── ui/
        ├── 校园二手交易系统.drawio  # 仅七个最终画板，控件可编辑
        ├── manifest.json
        └── 界面1.svg ～ 界面7.svg
```

## 图与功能

| UML 文件 | 内容 |
|---|---|
| UML类图 | 用户、商品、版本、审核批次、预约及历史快照 |
| UML组件图 | 七模块的职责、调用及数据访问关系 |
| UML用例图 | 游客、普通用户和管理员的业务目标及权限 |
| UML时序图 | 创建预约、重复请求及并发占用处理 |

| UI 文件 | 功能模块 | 代表界面 |
|---|---|---|
| 界面1.png | 账号与权限 | 注册与登录 |
| 界面2.png | 商品管理 | 我的商品 |
| 界面3.png | 审核与违规处理 | 商品审核 |
| 界面4.png | 商品查询 | 商品集市 |
| 界面5.png | 预约与成交 | 卖家预约工作台 |
| 界面6.png | 成交统计 | 成交统计 |
| 界面7.png | 历史与审计 | 管理员审计日志 |

## 修改和重绘

Python 代码只使用标准库，无需 pip 依赖。需要安装 Java，工具及字体准备见 [tools/README.md](tools/README.md)。在 `lab2` 下执行：

```powershell
# 根据 Python 绘图代码重新生成七个画板及 SVG，不改变 PNG
python src/build_ui.py

# 根据 UML/*.puml 导出四张 UML
python src/render.py --kind uml

# 从七画板 drawio 文件导出七张 UI
python src/render.py --kind ui

# 或一次导出所有图；使用 --output 可先输出到独立目录检查
python src/render.py --output build/review
```

UML 的可编辑绘图代码就是 `UML/*.puml`。UI 可直接在 diagrams.net 打开 `src/ui/校园二手交易系统.drawio` 修改，然后执行 `render.py --kind ui`；也可修改 `src/build_ui.py` 后重新生成。重新运行 `build_ui.py` 会覆盖 drawio 和 SVG，直接在绘图工具做过修改时应先保留修改版本。

最终 PNG 直接复制自课程提交目录，文件名与报告模块顺序保持一致；画面内的示例编号延用既有设计，属于示例内容。未选中的候选图、旧报告、缓存、下载 ZIP 和 LaTeX 中间文件不放入本目录。

2026-11-13 本地整理检查：源代码生成的 drawio、SVG 与保留的七页设计源文件逐字节相同；用固定版本工具重新导出的四张 UML 和七张 UI 与最终 PNG 逐像素相同。Git 可见文件共 32 个，约 4.2 MB；工具二进制不在其中。
