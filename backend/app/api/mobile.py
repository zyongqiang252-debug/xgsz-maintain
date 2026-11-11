"""客户端无关的移动端接口层 /api/v1/m/v1/*

设计目的：
- 钉钉 H5、微信小程序、App 都调这一层，不再把业务绑死在 /dingtalk 命名下
- 具体逻辑复用 dingtalk.py 里的实现（同一套状态机、同一套建单逻辑），避免复制
- 旧路径 /api/v1/dingtalk/* 保留不删，已发布的钉钉版本不受影响
"""
from fastapi import APIRouter

from app.api import dingtalk as dt

router = APIRouter(prefix="/m/v1", tags=["移动端"])

# 上报 / 队列 / 详情
router.add_api_route("/report", dt.mobile_report, methods=["POST"], summary="移动端上报")
router.add_api_route("/queue", dt.tech_queue, methods=["GET"], summary="移动端队列（分 tab + 工单池）")
router.add_api_route("/wo/{work_order_id}", dt.tech_detail, methods=["GET"], summary="移动端工单详情")

# 状态推进 / 抢单 / 接单 / 完成
router.add_api_route("/wo/{work_order_id}/transition", dt.tech_transition, methods=["POST"], summary="移动端状态推进")
router.add_api_route("/wo/{work_order_id}/claim", dt.tech_claim, methods=["POST"], summary="移动端抢单")
router.add_api_route("/wo/{work_order_id}/start", dt.tech_start_work, methods=["POST"], summary="移动端接单")
router.add_api_route("/wo/{work_order_id}/complete", dt.tech_complete_work, methods=["POST"], summary="移动端提交完成报告")
