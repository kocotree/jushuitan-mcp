# 聚水潭只读 CLI 与 MCP

这个项目使用聚水潭新版开放平台的 `app_key + app_secret` 接入，只开放以下只读查询：

- 商品库存
- 订单
- 采购单管理
- 采购入库明细
- 普通商品资料（按 SKU 查询）
- 普通商品资料（按款式查询）

不会提供发货、取消订单、修改库存等写操作。

## 1. 安装

在 PowerShell 中运行：

```powershell
cd D:\kk\jushuitan_review
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

编辑 `.env`，只填写你自己的值：

```dotenv
JST_APP_KEY=你的应用Key
JST_APP_SECRET=你的应用Secret
JST_ENDPOINT=https://openapi.jushuitan.com
```

`.env` 已被 `.gitignore` 排除。不要把真实 Key、Secret 或 Token 发到聊天、提交到 Git，或写进 MCP 配置文件。

## 2. 先验证 CLI

使用一个已知商品编码验证认证和接口连接：

```powershell
.\.venv\Scripts\jst.exe inventory --sku SKU001
```

其他示例：

```powershell
.\.venv\Scripts\jst.exe orders `
  --modified-begin "2026-08-01 00:00:00" `
  --modified-end "2026-08-02 00:00:00"

.\.venv\Scripts\jst.exe purchase --po-id PO12345

.\.venv\Scripts\jst.exe purchase-inbound `
  --modified-begin "2026-08-04 00:00:00" `
  --modified-end "2026-08-04 23:59:59" `
  --date-type 2

.\.venv\Scripts\jst.exe product-skus --exact-name "椰椰小岛两栖泳衣三件套"

.\.venv\Scripts\jst.exe product-styles --i-id STYLE001
```

时间范围按聚水潭接口要求最长七天。订单和库存的大批量同步应使用 `ts/start_ts` 防止翻页期间数据变化造成漏单。

程序会自动获取、缓存和刷新 Token。默认缓存位置为：

```text
%LOCALAPPDATA%\jst-connector\token.json
```

## 3. 运行 MCP

```powershell
.\.venv\Scripts\jst-mcp.exe
```

这是 STDIO MCP Server，提供以下工具：

- `jst_inventory`
- `jst_orders`
- `jst_purchase`
- `jst_purchase_inbound`
- `jst_product_skus`
- `jst_product_styles`

MCP 客户端应直接启动 `D:\kk\jushuitan_review\.venv\Scripts\python.exe`，参数为：

```text
-m jst_connector.mcp_server
```

程序会按安装位置读取 `D:\kk\jushuitan_review\.env`，不要求把密钥复制进 MCP 客户端配置。

本机 Codex 可运行：

```powershell
codex mcp add jushuitan -- "D:\kk\jushuitan_review\.venv\Scripts\python.exe" -m jst_connector.mcp_server
codex mcp get jushuitan
```

当前电脑已经添加了名为 `jushuitan` 的全局 MCP 配置。如需移除：

```powershell
codex mcp remove jushuitan
```

### 远程 HTTP 入口

远程 HTTP 入口已启用标准 MCP OAuth，并使用飞书完成员工登录。STDIO 入口不受影响。重新执行可编辑安装以生成 `jst-mcp-http` 命令：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\jst-mcp-http.exe
```

默认只监听 `127.0.0.1:8000`：

```text
健康检查：http://127.0.0.1:8000/health
MCP 地址：http://127.0.0.1:8000/mcp
```

可通过环境变量覆盖：

```dotenv
JST_MCP_HOST=127.0.0.1
JST_MCP_PORT=8000
JST_MCP_PATH=/mcp
JST_MCP_PUBLIC_URL=https://jushuitan-mcp.kktree.cn
JST_MCP_OAUTH_DB_PATH=/data/oauth.db
FEISHU_APP_ID=飞书应用的App ID
FEISHU_APP_SECRET=飞书应用的App Secret
FEISHU_ALLOWED_TENANT_KEY=公司tenant_key
FEISHU_REDIRECT_URI=https://jushuitan-mcp.kktree.cn/oauth/feishu/callback
```

`FEISHU_ALLOWED_TENANT_KEY` 是公司的租户标识，不是部门 ID。部门限制继续由飞书应用的“可用范围”负责；服务端会额外拒绝 tenant_key 不匹配的其他企业账号。OAuth 客户端、授权码和 MCP token 保存在 SQLite 中，其中授权码和 token 只保存哈希值。

单次 MCP access token 有效 1 小时；refresh token 可以轮换，同一登录会话最多持续 30 天，之后必须重新完成飞书登录，以便应用可用范围的人员变更定期生效。为兼容客户端并发刷新，旧 refresh token 在轮换后保留 60 秒复用宽限期，超过宽限期后失效。

## 4. 手动 Docker 部署

服务器部署目录只需要项目文件和服务器自己的 `.env`。不要上传本机 `.env`、Token 缓存或 SSH 私钥。

在服务器复制模板并通过安全渠道填写聚水潭凭证：

```bash
cp .env.example .env
docker compose config
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 jushuitan-mcp
```

Compose 默认把服务绑定到服务器回环地址：

```dotenv
JST_MCP_BIND_ADDRESS=127.0.0.1
JST_MCP_PUBLIC_PORT=18090
```

部署后先在本机建立 SSH 隧道测试，不要直接开放公网端口：

```powershell
ssh -i "$env:USERPROFILE\.ssh\jst_mcp_deploy" `
  -p SSH端口 `
  -L 18090:127.0.0.1:18090 `
  部署账户@服务器地址
```

隧道建立后，本机访问：

```text
http://127.0.0.1:18090/health
http://127.0.0.1:18090/mcp
```

Traefik 只把域名请求转发到该服务；`/mcp` 会要求 Bearer token，未登录客户端会通过 OAuth 元数据发现飞书登录入口。

## 5. 当前边界

- 只实现新版 `app_key + app_secret` 协议。
- `openweb.jushuitan.com` 是文档站；正式 API 请求默认发往 `https://openapi.jushuitan.com`。
- 当前没有写接口。
- HTTP MCP 使用飞书登录、公司 tenant_key 校验和飞书应用可用范围限制；仅部门成员可完成登录。
- 采购入库查询用于获取实际入库单及其商品明细；采购单查询本身不能替代实际入库数据。
- 普通商品资料同时支持按 SKU 和按款式两种查询方式。
- 淘系、拼多多及隐私字段可能受到平台授权和奇门接口限制。

对应的聚水潭官方文档：

- [采购单查询](https://openweb.jushuitan.com/dev-doc?docType=6&docId=26)
- [采购入库查询](https://openweb.jushuitan.com/dev-doc?docType=7&docId=901)
- [商品库存查询](https://openweb.jushuitan.com/dev-doc?docType=3&docId=15)
- [普通商品资料按 SKU 查询](https://openweb.jushuitan.com/dev-doc?docType=2&docId=14)
- [普通商品资料按款式查询](https://openweb.jushuitan.com/dev-doc?docType=2&docId=13)
