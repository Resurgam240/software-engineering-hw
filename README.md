# 拾光集市

面向校园闲置物品的二手交易系统，支持商品发布、审核、查询、预约和线下交易进度管理。普通用户可以同时作为买家和卖家，管理员负责商品审核与违规处理。

采用 Python 3.13、FastAPI 和 PostgreSQL 17，提供桌面浏览器界面。

## 功能

- **商品管理**：保存草稿、上传图片、提交审核、编辑重审、撤回与下架。
- **浏览与搜索**：按关键词、分类和价格筛选，支持价格排序和分页。
- **预约与交易**：买家提交预约，卖家确认或拒绝；支持取消及卖家标记完成。
- **审核与治理**：按审核批次处理商品，违规下架时同步终止有效预约。
- **统计与历史**：查询已完成交易的数量、预约时标价合计及历史商品快照。
- **权限与审计**：校验角色和对象归属，记录关键操作；管理员查看私人留言时保存访问记录。

系统记录线下交易进度，完成状态由卖家标记，统计金额取预约时标价；付款和交付由交易双方协商。

## 环境要求

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL 17，已启动并可连接
- Chrome 或 Edge 桌面浏览器

以下命令均在项目根目录执行。

## 安装与初始化

```powershell
uv sync --frozen  # 按 uv.lock 安装项目与开发依赖
uv run python tools/configure_database.py  # 交互式创建数据库、应用账号和 .env
uv run campus-market init  # 执行 Alembic 数据库迁移
uv run campus-market admin  # 创建管理员账号，密码不回显
```

数据库配置脚本需要 PostgreSQL 管理员凭据，默认连接 `127.0.0.1:5432`，创建 `campus_market` 和 `campus_market_test` 两个数据库。它会拒绝覆盖已有 `.env`、同名数据库或应用账号。

已有数据库环境可参考 [.env.example](.env.example) 手动配置 `.env`，再执行迁移。

### 配置项

| 变量 | 用途 | 默认值或要求 |
|---|---|---|
| `DATABASE_URL` | 应用数据库连接 | `postgresql+psycopg://` 连接串 |
| `TEST_DATABASE_URL` | 独立测试数据库连接 | 数据库名须为 `campus_market_test` |
| `APP_SECRET` | 业务请求摘要密钥 | 至少 32 个随机字符 |
| `ASSET_DIR` | 上传图片目录 | `var/images` |
| `COOKIE_SECURE` | 仅通过 HTTPS 发送 Cookie | 本地 HTTP 使用 `false`，HTTPS 使用 `true` |

凭据保存在 `.env`，数据库和图片目录需要具备写入权限。

## 启动与停止

```powershell
uv run campus-market serve  # 启动 http://127.0.0.1:8000
```

打开 [商品集市](http://127.0.0.1:8000/market)。使用 `--port` 参数指定端口；在运行终端按 `Ctrl+C` 停止应用。

```powershell
uv run campus-market serve --port 8080  # 在 8080 端口启动应用
```

Windows 下，`db-start` 和 `db-stop` 可管理固定目录中的 PostgreSQL：程序位于 `D:\PostgreSQL\17`，数据位于 `D:\PostgreSQL\data\campus-market`。使用其他安装位置时，通过 PostgreSQL 自身的服务或 `pg_ctl` 管理数据库。

```powershell
uv run campus-market db-start  # 启动上述目录中的 PostgreSQL 实例
uv run campus-market db-stop  # 停止该实例；执行前先停止应用和测试
```

## 演示数据

```powershell
uv run campus-market seed  # 创建演示账号和商品，重复执行不覆盖既有账号及商品
```

初始化后可使用以下账号，共同密码为 `CampusDemo2026!`：

| 用户名 | 角色与数据 |
|---|---|
| `admin_demo` | 管理员，审核与治理入口 |
| `seller_demo` | 普通用户，商品与卖家记录 |
| `buyer_demo` | 普通用户，预约记录 |
| `buyer_two` | 普通用户，可用于新增预约 |

演示数据覆盖草稿、待审核、在售、已预约和已成交等状态，便于体验不同流程。实际部署应创建独立账号和凭据。

## 测试与构建

```powershell
uv run pylint src/campus_market  # 检查生产 Python 代码风格
uv run pytest --junitxml=artifacts/pytest.xml  # 执行集成测试并输出 JUnit 报告
uv run python tools/acceptance.py  # 验证服务重启、并发查询和预约性能
uv run python tools/browser_smoke.py  # 在 Chrome 和 Edge 中执行完整业务流程
uv run campus-market verify  # 只读检查状态关联、历史快照和图片文件
uv run python tools/line_count.py  # 统计有效生产 Python 代码行数
uv build  # 构建 wheel 和源码发行包到 dist/
uv run python tools/verify_wheel.py  # 独立安装 wheel，验证服务及静态资源
```

**`pytest` 和 `acceptance.py` 会重建测试库的 `public` schema，二者应依次运行。**测试连接须指向独立的 `campus_market_test` 数据库。

- 集成测试覆盖权限、输入边界、状态转换、历史快照、幂等重试、并发竞争和事务回滚。
- 性能验证使用端口 `8001`，按五批、每批 20 并发执行查询和无冲突预约，并检查十次正常服务重启后的数据。
- 浏览器测试需要应用已在端口 `8000` 运行，使用 Windows 默认安装路径中的 Chrome 和 Edge；执行时会创建测试账号、商品和预约记录。
- wheel 验证使用独立虚拟环境和端口 `8002`，检查安装后的健康接口、页面及静态资源。
- 结构化结果保存在 `artifacts/`，JUnit 报告输出时自动移除主机名与项目绝对路径。

## 代码结构

```text
src/campus_market/
  models.py               数据模型、外键和唯一约束
  schemas.py              HTTP 输入类型
  auth.py                 密码、登录会话和角色校验
  product_commands.py     商品生命周期
  governance.py           审核与违规处理
  trade_commands.py       预约与成交
  commands.py             事务、幂等回执和成功日志
  queries.py              范围查询、历史与统计
  repository.py           对象读取、行锁和结果投影
  assets.py               图片校验、保存与授权访问
  integrity.py            只读数据完整性检查
  web.py                  HTTP 路由、CSRF 和异常映射
  templates/              Jinja2 页面
  static/                 CSS 与浏览器脚本
migrations/               Alembic 迁移
tests/                    PostgreSQL 集成测试
tools/                    初始化、测试和构建工具
```

应用采用模块化单体结构，业务命令统一提交事务。商品与预约按固定顺序加锁，部分唯一索引保证每件商品最多存在一条有效预约。内容版本和预约快照独立保留，商品后续修改不会覆盖历史内容及图片。

金额使用精确数值类型；时间按 UTC 存储，日期筛选按北京时间的完整自然日处理。

## API

运行后访问 [交互式 API 文档](http://127.0.0.1:8000/docs)。

- 登录身份来自服务端会话，受保护操作校验角色与对象归属。
- 写请求携带 `X-CSRF-Token`，先访问任一页面取得 `campus_csrf` Cookie，并使用其值；登录后该值会轮换。
- 业务变更请求另带 UUID 格式的 `Idempotency-Key` 和页面所见版本；审核操作还需当前审核批次。
- 请求结果未知时，复用原请求内容和操作标识重试；下一次独立业务操作使用新标识。
- 私人留言仅在授权详情中返回，管理员读取前须提交核查场景和原因。
