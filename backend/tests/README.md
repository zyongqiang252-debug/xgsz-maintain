# 自动化测试（pytest）

对应《测试方案》里的「最小可用自动化」四件套，全部跑在**已启动的后端**上（默认 `http://127.0.0.1:18080`，可用 `XGSZ_BASE` 覆盖）。

## 怎么跑

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install pytest          # 首次
.\.venv\Scripts\python.exe -m pytest tests -v             # 全部（含页面回归，约 1.5 分钟）
.\.venv\Scripts\python.exe -m pytest tests -m "not slow"  # 跳过浏览器，约 40 秒
```

前置：后端已启动、数据库可连、`admin/admin123` 可登录。**测试会自己建临时技术员并清理测试工单**，不依赖历史数据。

## 文件

| 文件 | 覆盖 | 数量 |
|---|---|---|
| `test_state_machine.py` | 11 状态 × 11 目标的状态机矩阵、挂起阻断、终态不可逆、同状态改派、远程跳过到场；**非法流转断言「400 + 状态不变 + 不写日志/通知」** | 87 |
| `test_workload.py` | 派工→拒收循环 3 次的工作量守恒、拒收不影响他人、接单/归档的扣减时点 | 4 |
| `test_concurrency.py` | 客户门户 10 并发报修的单号唯一性、同内容重复报修 | 2 |
| `test_page_smoke.py` | 16 个 PC 页面：零 console error、零失败请求（`-m slow`） | 1 |
| `conftest.py` | 管理员/临时技术员夹具、`OrderBuilder`（按状态机把工单推到任意状态）、DB 断言、数据清理 | — |

## 当前结果（2026-11-11）

- 106 passed / 4 xfailed / 2 failed（非 slow）
- **4 个 xfail 是已知缺陷**，`strict=True`：修好后会变成 XPASS 并**报错**，提醒回来删掉 xfail 标记：
  1. `test_hold_blocks_reassign` —— C-01 挂起中仍可改派
  2. `test_accept_keeps_workload` —— 接单就把工作量 -1，在办工作量被清零
  3. `test_archive_decrements_workload` —— 接单清零 + 归档不扣减
  4. `test_concurrent_customer_reports` —— C-04 并发报修撞单号（10 并发里 6 个 500）
- **2 个 failed 是既有用例**（`test_extract_error_codes.py` 的 `ALM-6401` 相关两条），与本次改动无关：实现里 `6401` 也会被单独抠出来，和测试期望不一致，需单独确认哪边是对的。

## 约定

- 测试数据统一 `PYTEST_` 前缀 + 每次运行随机串，会话结束在 `cleanup` 夹具里清库（含子表与外键解引用）；
- 断言尽量「接口 + 数据库」双查，避免只看到 200 就以为联动正确；
- 新增用例不要改历史数据，也不要用 `--keep` 之类的开关长期留脏数据。
