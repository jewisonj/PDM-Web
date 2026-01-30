// Type definitions for PDM-Web

export interface User {
  id: string
  auth_id?: string
  username: string
  email?: string
  role: 'admin' | 'engineer' | 'viewer'
  created_at: string
  updated_at: string
}

export interface Project {
  id: string
  name: string
  description?: string
  status: 'active' | 'archived' | 'completed'
  created_at: string
  updated_at: string
}

export interface Item {
  id: string
  item_number: string
  name?: string
  revision: string
  iteration: number
  lifecycle_state: 'Design' | 'Review' | 'Released' | 'Obsolete'
  description?: string
  project_id?: string
  project_name?: string
  material?: string
  mass?: number
  thickness?: number
  cut_length?: number
  is_supplier_part: boolean
  supplier_name?: string
  supplier_pn?: string
  unit_price?: number
  created_at: string
  updated_at: string
  files?: FileInfo[]
}

export interface FileInfo {
  id: string
  item_id: string
  file_type: 'CAD' | 'STEP' | 'DXF' | 'SVG' | 'PDF' | 'IMAGE' | 'OTHER'
  file_name: string
  file_path?: string
  file_size?: number
  revision?: string
  iteration: number
  uploaded_by?: string
  created_at: string
}

export interface BOMEntry {
  id: string
  parent_item_id: string
  child_item_id: string
  quantity: number
  source_file?: string
  created_at: string
}

export interface BOMTreeNode {
  item: Item
  quantity: number
  children: BOMTreeNode[]
}

export interface Task {
  id: string
  item_id?: string
  file_id?: string
  task_type: 'GENERATE_DXF' | 'GENERATE_SVG'
  status: 'pending' | 'processing' | 'completed' | 'failed'
  payload?: Record<string, unknown>
  error_message?: string
  created_at: string
  started_at?: string
  completed_at?: string
}

export interface LifecycleEntry {
  id: string
  item_id: string
  old_state?: string
  new_state?: string
  old_revision?: string
  new_revision?: string
  old_iteration?: number
  new_iteration?: number
  changed_by?: string
  change_notes?: string
  changed_at: string
}
