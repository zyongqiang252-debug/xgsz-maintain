from app.models.device import Device
from app.models.work_order import WorkOrder, WorkOrderStatus
from app.models.knowledge import KnowledgeItem, KnowledgeStatus
from app.models.user import User, UserRole
from app.models.spare_part import SparePart
from app.models.category import Category
from app.models.fault_code import FaultCodeMapping
from app.models.fault_phenomenon_category import FaultPhenomenonCategory
from app.models.root_cause_category import RootCauseCategory
from app.models.progress_log import WorkOrderProgressLog
from app.models.duty_schedule import DutySchedule, ShiftType
from app.models.leave_request import (
    LeaveRequest, LeaveRequestDetail,
    LeaveType, LeaveRequestStatus, LeaveShift,
)
from app.models.sys_config import SysConfig
from app.models.notification import Notification
from app.models.manual_code import ManualCodeEntry
from app.models.work_order_import import WorkOrderImportBatch, WorkOrderImportItem
from app.models.import_mapping_template import ImportMappingTemplate
from app.models.work_order_edit_log import WorkOrderEditLog
from app.models.work_order_collaborator import WorkOrderCollaborator
from app.models.customer import Customer
from app.models.customer_device import CustomerDevice
from app.models.customer_contact import CustomerContact
from app.models.customer_site import CustomerSite
from app.models.stock_movement import StockMovement
from app.models.spare_part_requisition import (
    SparePartRequisition, SparePartRequisitionStatus,
)
from app.models.warehouse import Warehouse, WarehouseLocation
from app.models.part_instance import PartInstance, PartInstanceStatus
from app.models.stocktake import Stocktake, StocktakeItem, StocktakeStatus
from app.models.login_log import LoginLog
from app.models.maintenance import (
    MaintenancePlan, MaintenanceRecord, InspectionTemplate, InspectionRecord,
)

__all__ = [
    "Device", "WorkOrder", "WorkOrderStatus",
    "KnowledgeItem", "KnowledgeStatus",
    "User", "UserRole",
    "SparePart",
    "Category",
    "FaultCodeMapping",
    "FaultPhenomenonCategory",
    "RootCauseCategory",
    "WorkOrderProgressLog",
    "DutySchedule", "ShiftType",
    "LeaveRequest", "LeaveRequestDetail",
    "LeaveType", "LeaveRequestStatus", "LeaveShift",
    "SysConfig",
    "Notification",
    "ManualCodeEntry",
    "WorkOrderImportBatch", "WorkOrderImportItem",
    "WorkOrderEditLog",
    "WorkOrderCollaborator",
    "Customer", "CustomerDevice", "CustomerContact", "CustomerSite",
    "StockMovement",
    "SparePartRequisition", "SparePartRequisitionStatus",
    "Warehouse", "WarehouseLocation",
    "PartInstance", "PartInstanceStatus",
    "Stocktake", "StocktakeItem", "StocktakeStatus",
    "LoginLog",
    "MaintenancePlan", "MaintenanceRecord",
    "InspectionTemplate", "InspectionRecord",
]