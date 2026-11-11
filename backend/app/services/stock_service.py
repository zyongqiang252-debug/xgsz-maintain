"""库存变更的公共入口：加行锁、算变动前后、写流水

为什么要有这一层：
  原来 领用 / 入库 / 进货导入 三处各写一遍"改 stock_quantity 再记流水"，
  并发下没有行锁，两单同时校验通过就会超卖。统一走这里以后：
    1. 先 with_for_update() 锁住备件行，第二个事务排队等；
    2. 锁到之后重新读库存再校验，前面的改动不会被覆盖；
    3. 流水一定有 before/after/金额，对账时不用猜。
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.spare_part import SparePart
from app.models.stock_movement import StockMovement
from app.models.user import User
from loguru import logger


def normalize_qty(value: float):
    """库存列历史上是 Integer，但允许半件（卷/米），整数就存 int，别让库里出现 5.0"""
    return int(value) if float(value).is_integer() else float(value)


def lock_part(db: Session, part_id: int) -> Optional[SparePart]:
    """按 id 取备件并加行锁（SELECT ... FOR UPDATE）"""
    return (
        db.query(SparePart)
        .filter(SparePart.id == part_id)
        .with_for_update()
        .first()
    )


def available_qty(part: SparePart) -> float:
    """可用库存 = 现存 - 已预占（审批通过但还没出库的数量）"""
    return float(part.stock_quantity or 0) - float(getattr(part, "reserved_quantity", 0) or 0)


def apply_stock_change(
    db: Session,
    part: SparePart,
    movement_type: str,
    quantity: float,
    *,
    unit_price: Optional[float] = None,
    work_order_id: Optional[int] = None,
    operator: Optional[User] = None,
    remark: Optional[str] = None,
    set_to: Optional[float] = None,
    source_type: Optional[str] = None,
    source_id: Optional[int] = None,
    warehouse_id: Optional[int] = None,
) -> StockMovement:
    """改库存 + 写一条流水（调用方负责 commit）

    set_to 给定时按"盘到多少就设成多少"处理（盘点用），quantity 会被重算成差异量。
    source_type/source_id 是来源单据（期初/领用单/盘点单），有唯一索引兜底防重复记账。
    """
    before = float(part.stock_quantity or 0)
    if set_to is not None:
        after = float(set_to)
        quantity = after - before
    else:
        quantity = float(quantity)
        after = before + quantity

    price = float(part.unit_price or 0) if unit_price is None else float(unit_price)
    part.stock_quantity = normalize_qty(after)

    mv = StockMovement(
        part_id=part.id,
        part_code=part.part_code,
        part_name=part.part_name,
        movement_type=movement_type,
        quantity=quantity,
        before_qty=before,
        after_qty=after,
        unit_price=price,
        amount=round(price * quantity, 2),
        work_order_id=work_order_id,
        source_type=source_type,
        source_id=source_id,
        warehouse_id=warehouse_id if warehouse_id is not None else getattr(part, "warehouse_id", None),
        operator_id=operator.id if operator else None,
        operator_name=operator.real_name if operator else None,
        remark=remark,
    )
    db.add(mv)
    db.flush()
    _invalidate_part_cache(part.id)
    logger.info(
        f"[Stock] {movement_type} {part.part_code} x{quantity:g} "
        f"{before:g} -> {after:g}（流水 {mv.id}）"
    )
    _maybe_alert_low_stock(part, before, after, operator)
    return mv


def _invalidate_part_cache(part_id: int) -> None:
    """库存变了就把详情缓存清掉：原来只清 stock_alerts，详情页会显示旧库存 5 分钟"""
    try:
        from app.core.cache_service import cache_service
        cache_service.delete(f"spare_part:{part_id}")
    except Exception as e:  # 缓存不可用不影响库存业务
        logger.warning(f"[Stock] 清备件缓存失败（忽略）: {e}")


def _maybe_alert_low_stock(part: SparePart, before: float, after: float,
                           operator: Optional[User] = None) -> None:
    """出库后库存"刚跌破"安全库存才推群，已经低于安全库存的再出库不重复提醒"""
    try:
        safety = float(getattr(part, "safety_stock", 0) or 0)
        if safety <= 0 or after >= safety or before < safety:
            return
        from app.core.dingtalk_group import group_robot
        if not group_robot.enabled:
            return
        group_robot.stock_alert_event(
            part_code=part.part_code,
            part_name=part.part_name,
            stock=after,
            safety_stock=safety,
            unit=getattr(part, "unit", "") or "",
            location=getattr(part, "location", "") or "",
            operator=operator.real_name if operator else "",
        )
    except Exception as e:  # 推送失败绝不影响库存业务
        logger.warning(f"[Stock] 库存预警推送失败（忽略）: {e}")
