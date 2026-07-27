"""Pydantic schemas for Supplier Portal."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID


# === Supplier Schemas ===
class SupplierBase(BaseModel):
    company_name: str
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    phone: Optional[str] = None
    login_email: str
    is_active: bool = True
    notes: Optional[str] = None


class SupplierCreate(SupplierBase):
    password: str = Field(..., min_length=8)


class SupplierUpdate(BaseModel):
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    phone: Optional[str] = None
    login_email: Optional[str] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class Supplier(SupplierBase):
    id: UUID
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SupplierWithUnread(Supplier):
    unread_count: int = 0


# === Supplier Login ===
class SupplierLogin(BaseModel):
    email: str
    password: str


class SupplierTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    supplier: Supplier


# === Item Access Schemas ===
class ItemAccessBase(BaseModel):
    item_id: UUID
    file_types: list[str] = ["PDF", "STEP"]
    notes: Optional[str] = None


class ItemAccessCreate(ItemAccessBase):
    pass


class ItemAccessUpdate(BaseModel):
    file_types: Optional[list[str]] = None
    notes: Optional[str] = None


class ItemAccess(ItemAccessBase):
    id: UUID
    supplier_id: UUID
    granted_by: Optional[UUID] = None
    granted_at: datetime
    # Joined item info
    item_number: Optional[str] = None
    item_name: Optional[str] = None

    class Config:
        from_attributes = True


# === Supplier Item View (for portal) ===
class SupplierFileView(BaseModel):
    id: UUID
    file_type: str
    file_name: str
    file_size: Optional[int] = None
    revision: Optional[str] = None
    created_at: datetime


class SupplierItemView(BaseModel):
    id: UUID
    item_number: str
    name: Optional[str] = None
    revision: str
    lifecycle_state: str
    material: Optional[str] = None
    thickness: Optional[float] = None
    mass: Optional[float] = None
    allowed_file_types: list[str]
    files: list[SupplierFileView] = []
    unread_comments: int = 0


# === Comment Schemas ===
class CommentBase(BaseModel):
    content: str


class CommentCreate(CommentBase):
    pass


class Comment(CommentBase):
    id: UUID
    supplier_id: UUID
    item_id: UUID
    author_type: str  # 'supplier' or 'admin'
    author_name: str
    author_user_id: Optional[UUID] = None
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UnreadCount(BaseModel):
    count: int


# === Password Reset ===
class PasswordReset(BaseModel):
    new_password: str = Field(..., min_length=8)
