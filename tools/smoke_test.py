# -*- coding: utf-8 -*-
"""xgsz-maintain 本地冒烟测试：导入三入口 + 工单生命周期两条链路

用法（backend 目录）：
    .venv\\Scripts\\python.exe ..\\tools\\smoke_test.py
报告：%TEMP%\\xgsz-smoke-report.json
"""
import json
import os
import sys
import tempfile
import time
from datetime import datetime

import requests
from openpyxl import Workbook

BASE = os.environ.get("XGSZ_BASE", "http://127.0.0.1:18080")
API = BASE + "/api/v1"
BACKUP = r"C:\Users\aaa\Desktop\xgsz-backup-20261104\data\uploads"
OUT = os.path.join(tempfile.gettempdir(), "xgsz-smoke-report.json")

report = {"started": datetime.now().isoformat(timespec="seconds"), "steps": [], "notes": []}


def step(name, fn):
    t0 = time.time()
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, f"异常: {type(e).__name__}: {e}"
    cost = round(time.time() - t0, 2)
    report["steps"].append({"step": name, "ok": bool(ok), "cost_s": cost, "detail": detail})
    flag = "OK " if ok else "FAIL"
    print(f"[{flag}] {name}  ({cost}s)  {json.dumps(detail, ensure_ascii=False)[:400]}")
    return ok, detail


def j(resp):
    try:
        return resp.json()
    except Exception:
        return {"_text": resp.text[:300]}


def main():
    s = requests.Session()
    tmp = tempfile.mkdtemp(prefix="xgsz-smoke-")
    tag = datetime.now().strftime("%H%M%S")

    def health():
        r = s.get(BASE + "/health", timeout=30)
        return r.status_code == 200 and j(r).get("status") == "healthy", j(r)

    def login():
        r = s.post(API + "/auth/login-by-password", json={"username": "admin", "password": "admin123"}, timeout=30)
        d = j(r)
        tk = d.get("token") or d.get("access_token")
        if tk:
            s.headers["Authorization"] = f"Bearer {tk}"
        return r.status_code == 200 and bool(tk), {"status": r.status_code, "role": d.get("role")}

    step("健康检查 /health", health)
    step("登录 admin/admin123", login)

    # ================= 导入三入口 =================
    xlsx = os.path.join(tmp, "工单台账-冒烟.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.title = "维修台账"
    ws.append(["工单号", "设备编号", "故障描述", "故障现象", "维修人", "维修工时", "报修时间", "备注"])
    ws.append([f"WO-SMOKE-{tag}-101", "CNC-L-001", "主轴异响，转速超 8000 转后明显", "主轴异响", "张伟", 2.5, "2026-11-01 09:30", "冒烟"])
    ws.append([f"WO-SMOKE-{tag}-102", "CNC-M-002", "冷却液压力不足，报警 E1023", "压力低", "张伟", 1.0, "2026-11-02 14:00", ""])
    ws.append([f"WO-SMOKE-{tag}-103", "AC-003", "", "", "", "", "", "缺故障描述，应被拦下"])
    wb.save(xlsx)

    def excel_inspect():
        with open(xlsx, "rb") as f:
            r = s.post(API + "/work-order-imports/excel/inspect",
                       files={"file": (os.path.basename(xlsx), f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                       timeout=120)
        d = j(r)
        return r.status_code == 200, {"headers": d.get("headers"), "row_count": d.get("row_count"),
                                      "mapped": len(d.get("mapping", {}))}

    step("① Excel 预检（表头识别 + 字段映射）", excel_inspect)

    batch = {}

    def excel_upload():
        with open(xlsx, "rb") as f:
            r = s.post(API + "/work-order-imports/upload-excel",
                       files={"file": (os.path.basename(xlsx), f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                       timeout=120)
        d = j(r)
        batch["id"] = d.get("batch_id")
        return r.status_code == 200, {"batch_id": d.get("batch_id"), "pending": d.get("pending"),
                                      "failed": d.get("failed"), "rows": d.get("results")}

    step("① Excel 导入（逐行校验）", excel_upload)

    items = {}

    def list_items():
        r = s.get(API + "/work-order-imports/items", params={"batch_id": batch["id"], "status": "PENDING"}, timeout=30)
        d = j(r)
        items["rows"] = d.get("items", [])
        return r.status_code == 200, {"pending": len(items["rows"])}

    step("① 待确认清单", list_items)

    def confirm_first():
        rows = items.get("rows") or []
        if not rows:
            return False, "无待确认记录"
        r = s.post(API + f"/work-order-imports/items/{rows[0]['id']}/confirm", timeout=60)
        d = j(r)
        return r.status_code == 200, {"work_order_id": d.get("work_order_id"), "msg": d.get("message")}

    step("① 确认入库（写工单）", confirm_first)

    csv_path = os.path.join(tmp, "工单台账-gbk.csv")
    with open(csv_path, "w", encoding="gbk", newline="") as f:
        f.write("工单号,设备编号,故障描述,维修人,维修工时\n"
                f"WO-SMOKE-{tag}-201,CNC-L-001,编码器信号丢失，参考电压 4.8V,张伟,1.5\n")

    def csv_upload():
        with open(csv_path, "rb") as f:
            r = s.post(API + "/work-order-imports/upload-excel",
                       files={"file": (os.path.basename(csv_path), f, "text/csv")}, timeout=120)
        d = j(r)
        return r.status_code == 200, {"pending": d.get("pending"), "failed": d.get("failed")}

    step("① CSV（GBK）导入", csv_upload)

    png = os.path.join(BACKUP, "image_import", "20261104_3733748e6915.png")

    def image_upload():
        if not os.path.exists(png):
            return False, "样本图片缺失"
        with open(png, "rb") as f:
            r = s.post(API + "/work-order-imports/upload-images",
                       files=[("files", (os.path.basename(png), f, "image/png"))], timeout=300)
        d = j(r)
        return r.status_code == 200, {"results": d.get("results")}

    step("② 图片 OCR 导入（RapidOCR 本地）", image_upload)

    pdf = os.path.join(BACKUP, "pdf_import", "20261104_5242d93f5290.pdf")

    def pdf_upload():
        if not os.path.exists(pdf):
            return False, "样本 PDF 缺失"
        with open(pdf, "rb") as f:
            r = s.post(API + "/work-order-imports/upload",
                       files=[("files", (os.path.basename(pdf), f, "application/pdf"))], timeout=300)
        d = j(r)
        return r.status_code == 200, {"batch_id": d.get("batch_id"), "results": d.get("results")}

    step("③ PDF 导入（pdfplumber + LLM 抽取）", pdf_upload)

    # ================= 生命周期 A：严格状态机 =================
    wo = {}

    def create_draft():
        r = s.post(API + "/work-orders/", json={
            "device_code": "CNC-L-001",
            "fault_description": "冒烟A：主轴异响，转速 8000 转以上周期性咔哒声",
            "fault_code": "SMOKE-A",
        }, timeout=30)
        d = j(r)
        wo["id"], wo["no"] = d.get("id"), d.get("work_order_no")
        return r.status_code == 200, {"id": wo["id"], "no": wo["no"], "state": d.get("status")}

    step("A-1 创建草稿", create_draft)

    def do_transition(to_status, remark):
        def _fn():
            r = s.post(API + f"/work-orders/{wo['id']}/transition",
                       json={"to_status": to_status, "remark": remark, "source": "WEB"}, timeout=60)
            d = j(r)
            return r.status_code == 200, {"state": d.get("status"), "detail": d.get("detail")}
        return _fn

    for idx, (st, note) in enumerate([
        ("SUBMITTED", "提交报修"), ("ASSIGNED", "主管派工"),
        ("ACCEPTED", "维修员接单"), ("ARRIVED", "到达现场"),
        ("INSPECTING", "开始检查"), ("IN_PROGRESS", "开始维修"),
    ], start=2):
        step(f"A-{idx} 流转 {st}", do_transition(st, note))

    def fill_archive():
        r = s.put(API + f"/work-orders/{wo['id']}", json={
            "fault_phenomenon": "主轴 8000rpm 以上周期性咔哒异响，负载 60% 加剧",
            "root_cause": "主轴前端轴承磨损，滚道剥落产生周期性冲击",
            "solution_steps": "1) 停机断电挂牌；2) 拆主轴前端端盖；3) 更换 7014C 轴承并重新预紧；4) 空载 8000rpm 试运行 30 分钟",
            "repair_result": "PERMANENT_FIX",
            "work_hours": 3.5,
        }, timeout=30)
        d = j(r)
        return r.status_code == 200, {"state": d.get("status"), "work_hours": d.get("work_hours"),
                                      "repair_result": d.get("repair_result")}

    step("A-8 补齐归档必填五项", fill_archive)
    step("A-9 流转 ARCHIVING", do_transition("ARCHIVING", "维修完成，待归档"))

    def archive_check():
        r = s.post(API + f"/work-orders/{wo['id']}/archive-check", timeout=30)
        d = j(r)
        return d.get("passed") is True, {"passed": d.get("passed"), "completeness": d.get("completeness"),
                                         "missing": d.get("missing_fields")}

    step("A-10 归档校验", archive_check)

    def archive_complete():
        r = s.post(API + f"/work-orders/{wo['id']}/archive-complete", timeout=60)
        d = j(r)
        return r.status_code == 200 and d.get("archived") is True, {"state": d.get("status"),
                                                                    "completeness": d.get("completeness"),
                                                                    "detail": d.get("detail")}

    step("A-11 归档完成", archive_complete)

    def progress():
        r = s.get(API + f"/work-orders/{wo['id']}/progress", timeout=30)
        d = j(r)
        logs = d.get("progress_logs", [])
        chain = [f"{x.get('from_status')}→{x.get('to_status')}" for x in logs]
        return r.status_code == 200 and len(logs) >= 7, {"logs": len(logs), "chain": chain}

    step("A-12 进度日志全链路留痕", progress)

    # ================= 生命周期 B：状态机不再被编辑"偷偷跳变" =================
    wo2 = {}

    def form_flow():
        r = s.post(API + "/work-orders/", json={"device_code": "CNC-M-002",
                                                "fault_description": "冒烟B：冷却液压力不足"}, timeout=30)
        wo2["id"] = j(r).get("id")
        r2 = s.put(API + f"/work-orders/{wo2['id']}", json={
            "fault_phenomenon": "压力表读数 0.2MPa，低于 0.4MPa 下限",
            "root_cause": "冷却液泵密封圈老化渗漏",
            "solution_steps": "更换密封圈并补液至标准液位",
            "repair_result": "TEMPORARY_FIX",
            "work_hours": 1.0,
        }, timeout=30)
        d2 = j(r2)
        return r2.status_code == 200 and d2.get("status") == "DRAFT", {"after_put_state": d2.get("status")}

    step("B-1 保存草稿后仍为 DRAFT（不再自动跳 IN_PROGRESS）", form_flow)

    def complete_blocked():
        r = s.post(API + f"/work-orders/{wo2['id']}/complete", timeout=60)
        return r.status_code == 400, {"status": r.status_code, "detail": j(r).get("detail")}

    step("B-2 未推进状态直接提交完成被拒", complete_blocked)

    step("B-3 提交报修 SUBMITTED", lambda: (lambda r: (r.status_code == 200 and j(r).get("status") == "SUBMITTED",
                                                       {"state": j(r).get("status")}))(
        s.post(API + f"/work-orders/{wo2['id']}/transition", json={"to_status": "SUBMITTED"}, timeout=30)))

    def cleanup_b():
        r = s.delete(API + f"/work-orders/{wo2['id']}", timeout=30)
        return r.status_code == 200, {"status": r.status_code}

    step("B-4 清理测试工单", cleanup_b)

    # ================= 检索 / 知识 =================
    def hybrid_search():
        r = s.post(API + "/search/hybrid", json={"query": "主轴异响", "top_k": 5, "mode": "hybrid"}, timeout=180)
        d = j(r)
        res = d.get("results", [])
        return r.status_code == 200, {"hits": len(res), "strategies": d.get("strategies_used"),
                                      "scores": [round(float(x.get("score") or 0), 3) for x in res[:5]]}

    step("④ 混合检索（无 Milvus，应降级 BM25）", hybrid_search)

    def knowledge_list():
        r = s.get(API + "/knowledge/", params={"page": 1, "page_size": 5}, timeout=30)
        d = j(r)
        return r.status_code == 200, {"total": d.get("total")}

    step("④ 知识库列表", knowledge_list)

    def answer_stream():
        r = s.post(API + "/search/answer/stream", json={"question": "主轴异响怎么修"}, timeout=180, stream=True)
        first = ""
        for chunk in r.iter_content(chunk_size=256, decode_unicode=True):
            if chunk:
                first = chunk[:200]
                break
        return r.status_code == 200, {"status": r.status_code, "first_chunk": first}

    step("④ AI 问答 SSE（无 Key，预期只返引用/报生成失败）", answer_stream)

    report["finished"] = datetime.now().isoformat(timespec="seconds")
    report["ok_count"] = sum(1 for x in report["steps"] if x["ok"])
    report["fail_count"] = sum(1 for x in report["steps"] if not x["ok"])
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n=== 汇总：{report['ok_count']} 通过 / {report['fail_count']} 失败 -> {OUT}")
    return 0 if report["fail_count"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
