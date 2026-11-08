# 本地运行说明（Windows · 无 Docker）

> 2026-11-08 在本机（Windows 10/11，非管理员账户，无 Docker）跑通的完整方案。
> 目标：验证「工单导入」与「工单生命周期」两条主线，不依赖 Milvus/RAGFlow/GPU。

## 一、这套环境由什么组成

| 组件 | 位置 / 版本 | 说明 |
|---|---|---|
| PostgreSQL 16.2 便携版 | `%LOCALAPPDATA%\xgsz-runtime\pgsql`，数据目录 `...\pgdata` | 取自 Maven Central 的 zonky 构建（22MB），**不含 psql**，只能走驱动连 |
| 数据库 | `xgsz_maintain` @ `localhost:15432`，用户 `admin`（trust） | 见 `backend/.env` |
| Python | `backend/.venv`（**3.12.14**） | `requirements-core.txt` + `greenlet` + `psycopg[binary]` |
| 前端构建产物 | `frontend/dist` | `npm install && npm run build` |
| Redis | 未安装 | 缓存/会话降级为进程内存，功能不受影响 |
| Milvus / 推理服务 8010 | 未部署 | 检索降级为 BM25 + 错误码精确匹配 |
| DeepSeek Key | 未配置 | AI 问答只返引用、不生成答案；PDF 抽取失败但不影响导入流程 |

## 二、首次搭建

```powershell
# 1) 便携版 PostgreSQL（下载 + 解压）
python tools\fetch_pg.py
& "$env:LOCALAPPDATA\xgsz-runtime\pgsql\bin\initdb.exe" -D "$env:LOCALAPPDATA\xgsz-runtime\pgdata" -U admin -A trust -E UTF8 --locale=C

# 2) 后端依赖（用 3.12，别用 3.13）
cd backend
py -3.12 -m venv .venv      # 或 uv venv --python 3.12
.\.venv\Scripts\python.exe -m pip install -r ..\requirements-core.txt
.\.venv\Scripts\python.exe -m pip install greenlet "psycopg[binary]"   # 迁移必需，否则 alembic 报错

# 3) 前端
cd ..\frontend
npm install
npm run build

# 4) 建库 + 建表 + 灌数据
cd ..\backend
.\.venv\Scripts\python.exe ..\tools\create_db.py
.\.venv\Scripts\python.exe -m alembic upgrade head
$env:PYTHONPATH="$PWD"
.\.venv\Scripts\python.exe "备份目录\config\scripts\restore_db.py" "备份目录\data\data.json"
```

## 三、日常启动 / 停止

```powershell
# 启动（PG + 后端，已在跑会自动跳过）
powershell -ExecutionPolicy Bypass -File tools\start-local.ps1

# 打开
#   http://127.0.0.1:18080        账号 admin / admin123
#   http://127.0.0.1:18080/docs   接口文档

# 停止
& "$env:LOCALAPPDATA\xgsz-runtime\pgsql\bin\pg_ctl.exe" -D "$env:LOCALAPPDATA\xgsz-runtime\pgdata" stop -m fast
# 后端：结束对应 python 进程（或关掉 start-local 起的隐藏窗口）
```

## 四、自检

```powershell
cd backend
.\.venv\Scripts\python.exe ..\tools\smoke_test.py          # 27 项，覆盖导入三入口 + 生命周期两条链路
.\.venv\Scripts\python.exe ..\tools\take_screenshots.py    # 用系统 Edge 截 6 张页面图
```

## 五、2026-11-08 实测结果

- **27/27 通过**（健康检查、登录、Excel 预检/导入/待确认/确认入库、CSV(GBK)、图片 OCR、PDF 解析、生命周期 A 全链路 8 条进度日志、生命周期 B、混合检索、知识库、AI 问答 SSE）
- 导入：xlsx 3 行 → 2 条待确认 + 1 条因缺故障描述被拦；GBK 编码 CSV 正常；图片 OCR 1.0s 识别 199 字
- 生命周期 A：`DRAFT→SUBMITTED→ASSIGNED→ACCEPTED→ARRIVED→INSPECTING→IN_PROGRESS→ARCHIVING→ARCHIVED`，归档完成度 100%
- 检索：无 Milvus 时 BM25 命中 1 条 score 0.97
- PDF：解析 2.1s 成功，LLM 抽取因无 Key 失败（属预期）
- 截图存于 `tools/screenshots/`（登录 / 驾驶舱 / 维修报表 / 工单详情 / 历史工单导入 / AI 问答）
- 验证脚本与结果：`tools/smoke_test.py`，报告落在 `%TEMP%\xgsz-smoke-report.json`

### 注意到的既有行为（非本次改动）

`PUT /work-orders/{id}` 在工单为 `DRAFT` 且已有故障描述/设备时会把状态直接置为 `IN_PROGRESS`（`app/api/work_orders.py:306`，上游作者原有逻辑）。
效果：页面里「新建 → 填表保存」会跳过 提交/派工/接单/到场/检查 五个状态；要走完整状态机必须用列表页的流转按钮，不要先保存表单。

## 六、换机器要注意

- `backend/.env` 不在版本库里（`.gitignore` 已排除），需从备份复制；`SECRET_KEY` 现在是本地值，上线前必须换
- `%LOCALAPPDATA%\xgsz-runtime` 不在版本库里，换机器要重新跑 `tools\fetch_pg.py` + `initdb`

## 七、推送到 GitHub

本机 `git` 直连 GitHub 会失败（schannel 握手 + 连接被重置），但**走本地代理可以**：

```powershell
# 先确认代理在跑（Clash 默认 7897）
Test-NetConnection 127.0.0.1 -Port 7897

# git 手动推（把 <TOKEN> 换成自己的 PAT）
git -c http.proxy=http://127.0.0.1:7897 push https://<TOKEN>@github.com/zyongqiang252-debug/xgsz-maintain.git master
```

推荐用脚本（自动判断有无写权限，没有就 fork 到自己账号再推）：

```powershell
# token 存到 C:\Users\<你>\gh_token.txt（文件里只放一行 ghp_xxx）
cd backend
.venv\Scripts\python.exe ..\tools\push_to_github.py --dry-run     # 只看要推什么
.venv\Scripts\python.exe ..\tools\push_to_github.py --delete-token-file
```

PAT 权限：
- classic：勾 `repo`
- fine-grained：Repository access 选该仓库，Contents = Read and write（看不到该仓库说明你不是协作者，需先 fork）

## 八、钉钉群机器人推送（新工单 / 派工 / 归档 → 群里弹消息）

无需公网、无需钉钉应用审批，只要一个群机器人 webhook。

### 配置

1. 钉钉群 → 群设置 → 智能群助手 → 添加机器人 → **自定义**
2. 安全设置勾 **加签**（不建议用"关键词"，容易漏发）
3. 复制 **Webhook 地址** 和 **加签密钥**，填进 `backend/.env`：

```ini
DINGTALK_GROUP_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=xxxxxxxx
DINGTALK_GROUP_SECRET=SECxxxxxxxxxxxxxxxx
```

4. 重启后端

### 触发时机

| 事件 | 时机 |
|---|---|
| `created` | 新建工单 |
| `submitted` | 提交报修 |
| `assigned` | 主管派工 |
| `rejected` | 工单被退回 |
| `archived` | 归档完成 |

### 自检

```powershell
# 看配置是否生效（webhook 会打码）
curl -H "Authorization: Bearer <token>" http://127.0.0.1:18080/api/v1/dingtalk/group/status

# 往群里发一条测试消息
curl -X POST -H "Authorization: Bearer <token>" http://127.0.0.1:18080/api/v1/dingtalk/group/test
```

### 说明

- 推送在**后台线程**发送，群机器人慢或挂掉**不会拖慢/弄失败**业务接口
- 未配置 webhook 时全部逻辑直接跳过，本地开发不会有任何副作用
- 加签算法：`sign = base64(HMAC-SHA256(secret, timestamp + "\n" + secret))`，已按钉钉文档实现并实测校验一致
- 目前只推**工单事件**；库存预警、请假审批如需推送，可在对应位置调用 `group_robot.send_markdown_async(...)`

## 九、网页上接入第三方 API（推荐，不用改 .env）

管理员登录 → 左侧「系统管理 → 系统设置」（`/system-settings`）

| 能配 | 效果 |
|---|---|
| AI 大模型（DeepSeek）：API Key / Base URL / 模型 | 保存即生效，AI 问答、PDF 抽取、知识自动收录立刻可用 |
| 钉钉群机器人：Webhook / 加签密钥 | 保存即生效，新工单/派工/归档自动推群 |

特点：

- **存数据库**（`sys_configs` 表），重启自动加载，不用再动 `.env`
- **优先级**：数据库 > `.env` > 代码默认值
- **密钥只写不读**：接口返回一律打码（`sk-a****7890`）
- **测试连接**：AI 会真的发一条最小请求，返回延迟/模型/错误原因；群机器人会往群里发一条测试消息
- **仅管理员**可见可改（维修员/匿名 403/401）
- 短信、钉钉扫码、Milvus 属于启动期配置，仍需改 `.env` 后重启，页面里只做状态展示

对应的接口：

```
GET    /api/v1/system-settings/overview
GET    /api/v1/system-settings/ai
PUT    /api/v1/system-settings/ai            {api_key?, base_url?, model?}
POST   /api/v1/system-settings/ai/test
GET    /api/v1/system-settings/dingtalk-group
PUT    /api/v1/system-settings/dingtalk-group {webhook?, secret?}
POST   /api/v1/system-settings/dingtalk-group/test
```

### 9.1 密钥安全（重要）

网页里填的 API Key / 群机器人 Webhook / 加签密钥，**不是明文存库**：

| 暴露面 | 情况 |
|---|---|
| 页面 / 接口返回 | 只给打码值（`sk-a****7890`），连管理员也读不到明文 |
| 数据库直连 / 数据库备份 | **Fernet 密文**（`enc:v1:...`），看不到明文 |
| 后端日志 | 只记「更新了哪些字段」，不记值 |
| 浏览器 localStorage / F12 | 不落明文，保存后输入框清空 |
| 抓包 | ⚠️ 本机是 HTTP 明文传输，生产必须上 HTTPS |
| 拿到服务器（进程 + env） | ⚠️ 服务端必须能解密，这类攻击无法只靠加密防御 |

加密密钥来源：

```ini
# 不填则用 SECRET_KEY 派生（简单，但换 SECRET_KEY 会导致旧密文解不开）
SETTINGS_ENC_KEY=
# 建议生成一把独立的：
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

注意：
- 换 `SECRET_KEY` 或 `SETTINGS_ENC_KEY` 后，已存的密文将无法解密 → 重新在页面录入 Key 即可（日志会告警，不会崩）
- `backend/.env` 里的 `DEEPSEEK_API_KEY` 仍是明文，**建议留空**、统一走网页配置
- 历史明文配置（改造前写入的）会在程序启动读取时**自动加密迁移**
