// Supplier Portal Types

export interface Supplier {
  id: string
  company_name: string
  contact_name?: string
  contact_email?: string
  phone?: string
  login_email: string
  is_active: boolean
  notes?: string
  created_by?: string
  created_at: string
  updated_at: string
}

export interface SupplierWithUnread extends Supplier {
  unread_count: number
}

export interface SupplierItemView {
  id: string
  item_number: string
  name?: string
  revision: string
  lifecycle_state: string
  material?: string
  allowed_file_types: string[]
  files: SupplierFileView[]
  unread_comments: number
}

export interface SupplierFileView {
  id: string
  file_type: string
  file_name: string
  file_size?: number
  revision?: string
  created_at: string
}

export interface ItemAccess {
  id: string
  supplier_id: string
  item_id: string
  file_types: string[]
  notes?: string
  granted_by?: string
  granted_at: string
  item_number?: string
  item_name?: string
}

export interface SupplierComment {
  id: string
  supplier_id: string
  item_id: string
  author_type: 'supplier' | 'admin'
  author_name: string
  author_user_id?: string
  content: string
  is_read: boolean
  created_at: string
}

export interface SupplierCreate {
  company_name: string
  contact_name?: string
  contact_email?: string
  phone?: string
  login_email: string
  password: string
  is_active?: boolean
  notes?: string
}

export interface SupplierUpdate {
  company_name?: string
  contact_name?: string
  contact_email?: string
  phone?: string
  login_email?: string
  is_active?: boolean
  notes?: string
}

export interface ItemAccessCreate {
  item_id: string
  file_types?: string[]
  notes?: string
}
