# 审计脚本

2026-11-08 对 xgsz-maintain 做全面检查时用的脚本，结论见
`项目说明/代码审计与测试报告-20261108.md`。

| 脚本 | 用途 |
|---|---|
| `audit_routes.py` | AST 扫描所有路由的鉴权依赖（OPEN / AUTH 清单） |
| `audit_auth.py` | 匿名探测 148 个接口 + 与 OpenAPI security 声明比对 |
| `audit_anon.py` | 匿名读工单 / 写知识 / 传文件实证，**自带清理** |
| `audit_perm.py` | 角色权限矩阵 + 状态机边界 |
| `audit_import.py` | 导入 7 类边界用例 + 接口性能 |
| `audit_frontend.py` | 13 个页面控制台报错 / 失败请求 / 加载耗时（复用系统 Edge） |
| `audit_code.py` | 代码质量静态扫描（裸 except / print / utcnow / 硬编码） |

运行前先起后端（`tools/start-local.ps1`），脚本里默认 `http://127.0.0.1:18080`。
输出写在 `%TEMP%\xgsz-audit-*.txt`。

⚠️ 部分脚本会写库（`audit_anon.py`、`audit_perm.py`、`audit_import.py`），
跑完请执行 `restore_db.py` 还原演示数据：

```powershell
cd backend
$env:PYTHONPATH = $PWD
.venv\Scripts\python.exe "<备份目录>\config\scripts\restore_db.py" "<备份目录>\data\data.json"
```
