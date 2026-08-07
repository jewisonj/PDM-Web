/**
 * Shared links API client - permanent public links for project documents.
 */

export interface SharedLink {
  id: string
  kind: 'build_book' | 'tracker' | 'print_packet' | 'design_book' | 'other'
  project_code: string | null
  title: string
  file_name: string
  storage_path: string
  public_url: string
  size_bytes: number | null
  created_at: string
  updated_at: string
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }
  return response.json()
}

/** Upload a PDF (e.g. browser-printed tracker or build book) and get a permanent link. */
export async function uploadSharedPdf(
  file: File,
  kind: SharedLink['kind'],
  projectCode?: string | null,
  title?: string | null
): Promise<SharedLink> {
  const form = new FormData()
  form.append('file', file)
  form.append('kind', kind)
  if (projectCode) form.append('project_code', projectCode)
  if (title) form.append('title', title)

  const response = await fetch('/api/share', { method: 'POST', body: form })
  return handleResponse<SharedLink>(response)
}

/** Share a project's existing print packet. */
export async function sharePrintPacket(projectId: string): Promise<SharedLink> {
  const response = await fetch(`/api/share/print-packet/${projectId}`, { method: 'POST' })
  return handleResponse<SharedLink>(response)
}

/** Share a file already in Supabase Storage (e.g. a stored build book or design book). */
export async function shareFromStorage(
  bucket: string,
  path: string,
  kind: SharedLink['kind'],
  projectCode?: string | null,
  title?: string | null
): Promise<SharedLink> {
  const response = await fetch('/api/share/from-storage', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bucket, path, kind, project_code: projectCode, title }),
  })
  return handleResponse<SharedLink>(response)
}

export async function listSharedLinks(projectCode?: string | null): Promise<SharedLink[]> {
  const params = projectCode ? `?project_code=${encodeURIComponent(projectCode)}` : ''
  const response = await fetch(`/api/share${params}`)
  const data = await handleResponse<{ links: SharedLink[] }>(response)
  return data.links
}

export async function revokeSharedLink(linkId: string): Promise<void> {
  const response = await fetch(`/api/share/${linkId}`, { method: 'DELETE' })
  await handleResponse(response)
}
