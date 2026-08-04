# 聚水潭只读 CLI 与 MCP

这个项目使用聚水潭新版开放平台的 `app_key + app_secret` 接入，只开放以下只读查询：

- 店铺
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

店铺查询不需要业务筛选，适合作为第一次认证测试：

```powershell
.\.venv\Scripts\jst.exe shops
```

其他示例：

```powershell
.\.venv\Scripts\jst.exe inventory --sku SKU001

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

- `jst_shops`
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

## 4. 当前边界

- 只实现新版 `app_key + app_secret` 协议。
- `openweb.jushuitan.com` 是文档站；正式 API 请求默认发往 `https://openapi.jushuitan.com`。
- 当前没有写接口。
- 采购入库查询用于获取实际入库单及其商品明细；采购单查询本身不能替代实际入库数据。
- 普通商品资料同时支持按 SKU 和按款式两种查询方式。
- 淘系、拼多多及隐私字段可能受到平台授权和奇门接口限制。

对应的聚水潭官方文档：

- [采购单查询](https://openweb.jushuitan.com/dev-doc?docType=6&docId=26)
- [采购入库查询](https://openweb.jushuitan.com/dev-doc?docType=7&docId=901)
- [商品库存查询](https://openweb.jushuitan.com/dev-doc?docType=3&docId=15)
- [普通商品资料按 SKU 查询](https://openweb.jushuitan.com/dev-doc?docType=2&docId=14)
- [普通商品资料按款式查询](https://openweb.jushuitan.com/dev-doc?docType=2&docId=13)
