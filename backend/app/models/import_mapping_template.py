"""导入字段映射模板：把「哪一列对应哪个系统字段」存下来，下次同格式台账直接套用

背景：历史台账每家客户/每个年份的表头都不一样（"故障描述" / "故障现象" / "报障内容"…），
      自动匹配猜不全，每次导入都要人工重配一遍。这里按「表头签名」记住一份映射：
      - 表头签名 = 规范化后的表头名排序拼接，改名、调列顺序、换文件都能命中
      - 同一签名可以存多份模板（比如「年度台账」「现场巡检台账」），按使用次数优先套用
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, JSON, String

from app.models.base import BaseModel


class ImportMappingTemplate(BaseModel):
    __tablename__ = "import_mapping_templates"

    name = Column(String(100), nullable=False, comment="模板名，如「XX客户年度台账」")
    scene = Column(String(40), nullable=False, default="work_order_excel",
                   comment="使用场景，目前只有 work_order_excel")
    header_signature = Column(String(500), nullable=False, comment="表头签名（规范化排序后拼接）")
    headers = Column(JSON, default=list, comment="保存时的原始表头，便于展示")
    mapping = Column(JSON, default=dict, comment="{系统字段key: 台账列名}")
    created_by = Column(Integer, index=True, comment="创建人 user id")
    creator_name = Column(String(100))
    use_count = Column(Integer, nullable=False, default=0, comment="被套用次数，越多越优先")
    last_used_at = Column(DateTime)

    __table_args__ = (
        Index("ix_import_mapping_templates_sig", "scene", "header_signature"),
    )

    def touch(self) -> None:
        self.use_count = int(self.use_count or 0) + 1
        self.last_used_at = datetime.now()

    def __repr__(self) -> str:
        return f"<ImportMappingTemplate(id={self.id}, name='{self.name}')>"
