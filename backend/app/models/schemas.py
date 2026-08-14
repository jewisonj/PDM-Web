"""Pydantic schemas for API request/response models."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID


# === User Schemas ===
class UserBase(BaseModel):
    username: str
    email: Optional[str] = None
    role: str = "viewer"


class UserCreate(UserBase):
    pass


class User(UserBase):
    id: UUID
    auth_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# === Project Schemas ===
class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None
    status: str = "active"


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class Project(ProjectBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# === Item Schemas ===
class ItemBase(BaseModel):
    """Base fields for items - no pattern validation (used for responses)."""
    item_number: str
    name: Optional[str] = None
    revision: str = "A"
    iteration: int = 1
    lifecycle_state: str = "Design"
    description: Optional[str] = None
    project_id: Optional[UUID] = None
    material: Optional[str] = None
    mass: Optional[float] = None
    thickness: Optional[float] = None
    cut_length: Optional[float] = None
    cut_time: Optional[float] = None
    price_est: Optional[float] = None
    is_supplier_part: bool = False
    supplier_name: Optional[str] = None
    supplier_pn: Optional[str] = None
    unit_price: Optional[float] = None


class ItemCreate(BaseModel):
    """Item creation with pattern validation.

    Standard format: 3 letters + 4-6 digits (e.g., csp0030, wma20000)
    Also accepts: mmc/spn/zzz prefixes with alphanumeric suffixes for supplier parts
    """
    item_number: str = Field(..., pattern=r"^[a-zA-Z]{3}[a-zA-Z0-9_-]+$")
    name: Optional[str] = None
    revision: str = "A"
    iteration: int = 1
    lifecycle_state: str = "Design"
    description: Optional[str] = None
    project_id: Optional[UUID] = None
    material: Optional[str] = None
    mass: Optional[float] = None
    thickness: Optional[float] = None
    cut_length: Optional[float] = None
    cut_time: Optional[float] = None
    price_est: Optional[float] = None
    is_supplier_part: bool = False
    supplier_name: Optional[str] = None
    supplier_pn: Optional[str] = None
    unit_price: Optional[float] = None


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    revision: Optional[str] = None
    iteration: Optional[int] = None
    lifecycle_state: Optional[str] = None
    description: Optional[str] = None
    project_id: Optional[UUID] = None
    material: Optional[str] = None
    mass: Optional[float] = None
    thickness: Optional[float] = None
    cut_length: Optional[float] = None
    cut_time: Optional[float] = None
    price_est: Optional[float] = None
    is_supplier_part: Optional[bool] = None
    supplier_name: Optional[str] = None
    supplier_pn: Optional[str] = None
    unit_price: Optional[float] = None


class Item(ItemBase):
    id: UUID
    project_name: Optional[str] = None  # Joined from projects table
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ItemWithFiles(Item):
    files: list["FileInfo"] = []


# === File Schemas ===
class FileBase(BaseModel):
    file_type: str
    file_name: str
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    revision: Optional[str] = None
    iteration: int = 1


class FileCreate(FileBase):
    item_id: UUID


class FileInfo(FileBase):
    id: UUID
    item_id: UUID
    uploaded_by: Optional[UUID] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# === BOM Schemas ===
class BOMEntry(BaseModel):
    id: UUID
    parent_item_id: UUID
    child_item_id: UUID
    quantity: int = 1
    source_file: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class BOMCreate(BaseModel):
    parent_item_id: UUID
    child_item_id: UUID
    quantity: int = 1
    source_file: Optional[str] = None


class BOMChildItem(BaseModel):
    """Child item in bulk BOM upload."""
    item_number: str
    quantity: int = 1
    name: Optional[str] = None
    material: Optional[str] = None
    mass: Optional[float] = None
    thickness: Optional[float] = None
    cut_length: Optional[float] = None
    cut_time: Optional[float] = None
    price_est: Optional[float] = None


class BOMBulkCreate(BaseModel):
    """Bulk BOM upload - replaces entire BOM for an assembly."""
    parent_item_number: str
    parent_name: Optional[str] = None
    parent_material: Optional[str] = None
    parent_mass: Optional[float] = None
    parent_thickness: Optional[float] = None
    parent_cut_length: Optional[float] = None
    parent_cut_time: Optional[float] = None
    parent_price_est: Optional[float] = None
    children: list[BOMChildItem]
    source_file: Optional[str] = None


class BOMBulkResponse(BaseModel):
    """Response from bulk BOM upload."""
    parent_item_number: str
    parent_item_id: UUID
    items_created: int
    items_updated: int
    bom_entries_created: int
    children: list[str]


class BOMTreeNode(BaseModel):
    """Recursive BOM tree structure."""
    item: Item
    quantity: int
    children: list["BOMTreeNode"] = []


# === Work Queue Schemas ===
class TaskBase(BaseModel):
    item_id: Optional[UUID] = None
    file_id: Optional[UUID] = None
    task_type: str
    payload: Optional[dict] = None


class TaskCreate(TaskBase):
    pass


class Task(TaskBase):
    id: UUID
    status: str = "pending"
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# === Lifecycle History ===
class LifecycleEntry(BaseModel):
    id: UUID
    item_id: UUID
    old_state: Optional[str] = None
    new_state: Optional[str] = None
    old_revision: Optional[str] = None
    new_revision: Optional[str] = None
    old_iteration: Optional[int] = None
    new_iteration: Optional[int] = None
    changed_by: Optional[UUID] = None
    change_notes: Optional[str] = None
    changed_at: datetime

    class Config:
        from_attributes = True


# === Checkout ===
class Checkout(BaseModel):
    item_id: UUID
    user_id: UUID
    checked_out_at: datetime

    class Config:
        from_attributes = True


# === Search/Filter ===
class ItemSearchParams(BaseModel):
    q: Optional[str] = None  # Search term
    lifecycle_state: Optional[str] = None
    project_id: Optional[UUID] = None
    is_supplier_part: Optional[bool] = None
    limit: int = 50
    offset: int = 0


# === Cutting Parameters ===
class CuttingParameterBase(BaseModel):
    material_code: str = Field(..., description="Material code: 'CS', 'AL', 'SS'")
    ref_speed_ipm: float = Field(..., description="Reference cutting speed at 0.25\" thickness (IPM)")
    machinability: float = Field(default=1.0, description="Machinability index relative to mild steel")
    exponent: float = Field(default=0.85, description="Power law exponent for speed calculation")
    notes: Optional[str] = None


class CuttingParameterCreate(CuttingParameterBase):
    pass


class CuttingParameterUpdate(BaseModel):
    ref_speed_ipm: Optional[float] = None
    machinability: Optional[float] = None
    exponent: Optional[float] = None
    notes: Optional[str] = None


class CuttingParameter(CuttingParameterBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# === Model Annotation Schemas ===
class AnnotationBase(BaseModel):
    position_x: float
    position_y: float
    position_z: float
    normal_x: Optional[float] = None
    normal_y: Optional[float] = None
    normal_z: Optional[float] = None
    content: str


class AnnotationCreate(AnnotationBase):
    pass


class Annotation(AnnotationBase):
    id: UUID
    item_id: UUID
    file_id: UUID
    author_type: str  # 'user' or 'supplier'
    author_id: UUID
    author_name: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Forward reference resolution
BOMTreeNode.model_rebuild()
ItemWithFiles.model_rebuild()
