from sqlalchemy import Column, String, Date, Text, Integer, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class Device(BaseModel):
    __tablename__ = "devices"

    device_code = Column(String(50), unique=True, nullable=False, index=True)
    device_name = Column(String(200), nullable=False)
    device_type = Column(String(100))
    model = Column(String(100))
    manufacturer = Column(String(200))
    location = Column(String(200))
    purchase_date = Column(Date)
    warranty_expiry = Column(Date)
    remark = Column(Text)

    # ========== GPU 服务器专有字段 ==========
    serial_no = Column(String(100), index=True, comment="设备序列号 SN")
    room = Column(String(50), index=True, comment="机房")
    rack_no = Column(String(50), comment="机柜号")
    rack_unit = Column(String(50), comment="U 位（如 U12-U19）")
    bmc_ip = Column(String(50), comment="BMC/带外管理 IP")
    business_ip = Column(String(50), comment="业务网 IP")
    gpu_model = Column(String(100), comment="GPU 型号（如 H100 80G SXM5）")
    gpu_count = Column(Integer, comment="GPU 数量")
    gpu_serial = Column(Text, comment="各卡序列号（换行分隔）")
    driver_version = Column(String(50), comment="驱动版本")
    cuda_version = Column(String(50), comment="CUDA 版本")
    firmware_version = Column(String(100), comment="固件/BMC 版本")
    cpu_model = Column(String(100), comment="CPU 型号")
    memory_gb = Column(Integer, comment="内存容量 GB")
    os_version = Column(String(100), comment="操作系统版本")
    project = Column(String(100), comment="所属项目/客户")

    # ========== 设备监控字段（预留，后续接外部故障上报系统） ==========
    # 运行状态：证据驱动四态，缺证据用 UNKNOWN（避免瞎猜为 ONLINE）
    # ONLINE 在线正常 / OFFLINE 离线 / ALARM 告警仍运行 / FAULT 故障停机 / UNKNOWN 未知
    run_status = Column(String(20), default="UNKNOWN", comment="运行状态 ONLINE/OFFLINE/ALARM/FAULT/UNKNOWN")
    last_heartbeat = Column(TIMESTAMP, comment="最后心跳时间")
    fault_tags = Column(JSONB, comment="故障标签数组 [{'code','name','level'}]")
    ext_system_id = Column(String(100), comment="外部监控系统关联ID（唯一）")
    status_source = Column(String(50), comment="状态来源：manual 手动/external 外部系统/auto 自动推断")
    status_reason = Column(String(200), comment="状态原因/证据说明（证据链，便于反推）")
    last_sync_time = Column(TIMESTAMP, comment="与外部系统最后同步时间")
    monitor_extra = Column(JSONB, comment="监控扩展字段，对接外部系统时按需写入")

    work_orders = relationship("WorkOrder", back_populates="device")

    def __repr__(self):
        return f"<Device(device_code='{self.device_code}', device_name='{self.device_name}', status='{self.run_status}')>"