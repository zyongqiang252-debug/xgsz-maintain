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

### 注意到的既有行为（非本次改动）

`PUT /work-orders/{id}` 在工单为 `DRAFT` 且已有故障描述/设备时会把状态直接置为 `IN_PROGRESS`（`app/api/work_orders.py:306`，上游作者原有逻辑）。
效果：页面里「新建 → 填表保存」会跳过 提交/派工/接单/到场/检查 五个状态；要走完整状态机必须用列表页的流转按钮，不要先保存表单。

## 六、换机器要注意

- `backend/.env` 不在版本库里（`.gitignore` 已排除），需从备份复制；`SECRET_KEY` 现在是本地值，上线前必须换
- `%LOCALAPPDATA%\xgsz-runtime` 不在版本库里，换机器要重新跑 `tools\fetch_pg.py` + `initdb`
