# 拾光集市：校园二手交易系统

软件工程实验三。Python 3.13 + FastAPI + PostgreSQL 17；桌面浏览器界面。

## 本机快速启动

在本目录打开 PowerShell：

```powershell
uv sync --frozen  # 按锁文件安装项目依赖
uv run campus-market db-start  # 启动本项目的本地 PostgreSQL
uv run campus-market init  # 执行数据库迁移，保留既有数据
uv run campus-market serve  # 启动本地 Web 服务，默认端口 8000
```

访问 <http://127.0.0.1:8000>。服务停止用运行终端中的 Ctrl+C；不再使用数据库时执行 `uv run campus-market db-stop`。
数据库按需运行，未注册开机自启服务，未修改原有 MySQL。停止数据库前先停止应用和测试。

本机 PostgreSQL 二进制位于 `D:\PostgreSQL\17`，数据位于 `D:\PostgreSQL\data\campus-market`。
数据库限制回环地址访问，shared_buffers=64MB、work_mem=2MB、max_connections=50。
Python 虚拟环境位于本目录 `.venv`，可以删除后按锁文件重建。

## 演示账号

仅用于本机课程演示，共同密码为 `CampusDemo2026!`：

| 用户名      | 角色                       |
| ----------- | -------------------------- |
| admin_demo  | 管理员                     |
| seller_demo | 普通用户，含商品和卖家记录 |
| buyer_demo  | 普通用户，含预约记录       |
| buyer_two   | 普通用户，用于预约另一商品 |

`uv run campus-market seed` 初始化演示账号和商品；重复执行不重建既有商品，也不覆盖既有账号密码。
这是明确的虚构演示数据。不要把演示配置用于公网部署。创建个人管理员可执行 `uv run campus-market admin`，控制台隐藏密码输入。

## 在新电脑配置

1. 准备 Python 3.13、uv、PostgreSQL 17。使用 PostgreSQL 官方下载页提供的 Windows binaries；本机使用 EDB 发布的 17.7 版本，解压后保留 bin/lib/share。
2. 用 `initdb` 初始化独立数据目录，认证方式选择 SCRAM，监听 `127.0.0.1`，用 `pg_ctl` 手动启动；已有数据库端口冲突时选另一个端口，并同步连接配置。
3. `uv sync --frozen` 安装锁定依赖；运行 `uv run python tools/configure_database.py`，输入数据库管理员凭据，创建应用用户及独立开发/测试数据库并写入 `.env`。
4. `uv run campus-market init`、`uv run campus-market admin`，按需执行 `uv run campus-market seed`，最后 `uv run campus-market serve`。

`.env.example` 只有占位符，`.env`、`var/` 和数据库目录不加入 Git、不进入交付包。本机数据库初始化管理员密码保存在被忽略的 `var/postgres-admin.local`，仅供本机维护，不是应用账号密码。
当前无需再次运行配置脚本；它会拒绝覆盖已有 `.env` 或既有角色。

## 架构和设计对应

- `models.py` 实现类图实体、外键、部分唯一索引；`schemas.py` 定义拒绝额外字段的 HTTP 输入。
- `product_commands.py`、`governance.py`、`trade_commands.py` 实现商品、审核和预约状态机。
- `commands.py` 统一控制事务、幂等回执和成功日志；业务处理函数不能自行提交。
- `queries.py`、`repository.py` 实现角色范围、业务历史、快照读取及统计。
- `auth.py`、`assets.py` 实现认证、访问控制及不可变图片；`web.py` 是会话与 CSRF 边界。
- `integrity.py` 提供只读数据诊断，执行 `uv run campus-market verify`；不提供管理员手工改状态或自动修复接口。

API 文档在运行服务的 `/docs`。写接口需先访问一个页面取得 CSRF Cookie，再发送同值的 `X-CSRF-Token`。
登录后 CSRF 会轮换。业务写操作另需 UUID 格式的 `Idempotency-Key` 和界面所见版本。
请求失败且结果未知时，保留原请求内容和操作标识重试；明确开始下一次业务尝试时使用新标识。

相对实验二的实现细化：

1. 仍使用单体、单 PostgreSQL、不可变图片；浏览器使用原生 JS 调用接口，Jinja2 渲染共享页面壳。
2. `activeReservationId` 不重复存为商品列，而由有效预约唯一索引查询派生，避免双向指针失配；接口仍返回该字段。
3. 在固定“商品→预约”行锁顺序之前，增加“操作者+操作标识”的事务级 advisory lock，处理同标识跨对象并发复用。
4. 本机 HTTP 的 Cookie Secure=false；HTTPS 部署设置 COOKIE_SECURE=true。会话不自动超时，退出时服务器撤销会话。
5. 分类和成色采用实验二界面的固定选项；时间持久化使用 UTC，日期筛选按北京时间的完整自然日解释。

## 质量与复现命令

```powershell
uv run pylint src/campus_market  # 检查生产 Python 代码风格
uv run pytest --junitxml=artifacts/pytest.xml  # 执行测试并保存报告（重建测试库）
uv run python tools/line_count.py  # 统计有效生产 Python 代码行数
uv run python tools/acceptance.py  # 验证重启与性能（重建测试库）
uv run python tools/browser_smoke.py  # 使用 Chrome 和 Edge 验证完整业务流程
uv build  # 构建 wheel 和源码发行包
uv run python tools/verify_wheel.py  # 在独立环境安装 wheel 并验证启动
uv run campus-market verify  # 只读检查业务数据关联与图片完整性
```

- **pytest 和 acceptance 会重建 `campus_market_test` 的 public schema。**数据库名带精确保护，不得配置成开发库；两项测试应依次运行，不要并行重建同一测试库。
- acceptance 使用独立服务端口 8001，真实 HTTP 请求执行 5批×20并发；验证 10 次正常进程重启，并保存全部200个性能样本，包含失败/超时。
- 浏览器脚本需主应用在 8000 运行，使用已安装 Chrome/Edge，真实创建验收账号、商品和预约；不清理这些历史。测试账号名称和商品标题明确带有验收用途。
- 并发测试覆盖五类竞争各10轮，其中多人竞争每轮20个不同买家；故障注入仅为测试配置中的内部服务参数，无公开 HTTP 开关。
- `line_count.py` 只统计 `src/campus_market` Python token 所在物理行，排除空行、注释、文档字符串；不计测试、迁移、工具、页面代码、依赖和自动生成代码。
- 代码风格只对路由工厂共享局部变量数量和语句数量作局部豁免；ORM/Pydantic 数据类型允许无公开方法。其余 Pylint 规则照常检查。

真实结果保存在 `artifacts/`。原始运行记录可能含测试账号标识，但不包含认证凭据、密码哈希或完整用户私人留言。
已由一位真实使用者试用注册、预约、确认、取消和发布商品流程，未报告问题；多位首次使用者的正式易用性试验尚未执行。浏览器结果仅适用于记录的本机版本，尚未取得实验一 REQ-025 所要求的甲方设备确认。

## 构建与打包

`uv build` 产生 wheel 和 sdist；`tools/verify_wheel.py` 在独立虚拟环境安装 wheel 后启动服务验证，排除仅源码可运行的错误。
`tools/package_submission.py` 复制允许的源码/配置/证据，排除秘密、虚拟环境、数据库、Git 元数据和缓存；检查报告 PDF 与四组 UML 后生成同名 ZIP。
LaTeX 工作区独立于源码；重新编译不会重写正文文件。报告源文件位于单独的 LaTeX 工作区。

## Git 与本地材料

GitHub 上传暂缓，审阅后再整合到既有仓库，保留远程旧内容和历史。
不在仓库正文中保存课程实名、账户别名或其他可关联身份的信息。

```powershell
git status  # 查看当前文件修改及暂存状态
git log --oneline --decorate  # 查看提交历史和分支指向
git diff  # 查看未暂存的代码差异
git show <commit>  # 查看指定提交的修改内容
uv run python tools/check_public.py --history  # 检查受跟踪文件和可达历史的本机路径及排除项
```

原始控制台输出存放在被忽略的 `var/local-evidence/`，避免公开本机路径。
测试结束时自动从 JUnit XML 移除 `hostname` 和项目绝对路径；结构化测试结果仍可用于核验。
检查姓名、学号等额外关键词时，可通过 `--private-terms` 传入仓库外的本地词表；词表本身不要提交。
真实使用者的账号、订单截图仅放在仓库外的报告工作区，不进入公开代码目录。
`.env`、`var/`、数据库、虚拟环境、报告和课程实名提交包都不应加入公开 Git 仓库。

## 初始化与打包命令说明

```powershell
uv run python tools/configure_database.py  # 首次配置独立数据库和本地凭据；拒绝覆盖
uv run campus-market admin  # 在控制台创建管理员，密码不回显
uv run campus-market seed  # 载入虚构演示数据，重复执行不覆盖既有数据
uv run campus-market db-stop  # 停止本项目的 PostgreSQL；请先停止应用和测试
uv run python tools/sync_report_evidence.py  # 同步报告证据和演示截图，不改写正文
uv run python tools/package_submission.py --help  # 查看报告、UML目录及提交名参数
```

打包时通过本地命令传入 `--name` 和 `--uml-directory`，不在脚本中硬编码个人信息。
不要将含真实提交名或个人绝对路径的命令记录提交到公开仓库。

## 参考

- FastAPI: <https://fastapi.tiangolo.com/>
- SQLAlchemy: <https://docs.sqlalchemy.org/en/20/>
- PostgreSQL 锁与事务: <https://www.postgresql.org/docs/17/explicit-locking.html>
- PostgreSQL Windows 下载: <https://www.postgresql.org/download/windows/>
- uv: <https://docs.astral.sh/uv/>
- Pylint: <https://pylint.readthedocs.io/>
