/**
 * Supabase Storage Service
 *
 * Handles file uploads, downloads, and URL generation for PDM files
 */

import { supabase } from './supabase'

export type BucketName = 'pdm-cad' | 'pdm-exports' | 'pdm-drawings' | 'pdm-other'

// File extension to bucket mapping
const EXTENSION_BUCKET_MAP: Record<string, BucketName> = {
  '.prt': 'pdm-cad',
  '.asm': 'pdm-cad',
  '.step': 'pdm-exports',
  '.stp': 'pdm-exports',
  '.dxf': 'pdm-exports',
  '.svg': 'pdm-exports',
  '.pdf': 'pdm-drawings',
}

// File extension to file_type mapping
const EXTENSION_TYPE_MAP: Record<string, string> = {
  '.prt': 'CAD',
  '.asm': 'CAD',
  '.step': 'STEP',
  '.stp': 'STEP',
  '.dxf': 'DXF',
  '.svg': 'SVG',
  '.pdf': 'PDF',
}

/**
 * Get the appropriate bucket for a file based on its extension
 */
export function getBucketForFile(filename: string): BucketName {
  const ext = filename.toLowerCase().slice(filename.lastIndexOf('.'))
  return EXTENSION_BUCKET_MAP[ext] || 'pdm-other'
}

/**
 * Get the file type for database storage
 */
export function getFileType(filename: string): string {
  const ext = filename.toLowerCase().slice(filename.lastIndexOf('.'))
  return EXTENSION_TYPE_MAP[ext] || 'OTHER'
}

/**
 * Build the storage path for a file
 * Convention: {item_number}/{revision}/{iteration}/{filename}
 */
export function buildStoragePath(
  itemNumber: string,
  revision: string,
  iteration: number,
  filename: string
): string {
  return `${itemNumber.toLowerCase()}/${revision}/${iteration}/${filename}`
}

/**
 * Parse a full storage path to extract bucket and path
 */
export function parseStoragePath(fullPath: string): { bucket: BucketName; path: string } | null {
  const match = fullPath.match(/^(pdm-\w+)\/(.+)$/)
  if (match) {
    return {
      bucket: match[1] as BucketName,
      path: match[2]
    }
  }
  return null
}

/**
 * Get a signed URL for downloading a file (valid for 1 hour)
 */
export async function getSignedUrl(
  bucket: BucketName,
  path: string,
  expiresIn: number = 3600
): Promise<string | null> {
  const { data, error } = await supabase.storage
    .from(bucket)
    .createSignedUrl(path, expiresIn)

  if (error) {
    console.error('Error creating signed URL:', error)
    return null
  }

  return data.signedUrl
}

/**
 * Get a signed URL from a full storage path (bucket/path format)
 */
export async function getSignedUrlFromPath(
  fullPath: string,
  expiresIn: number = 3600
): Promise<string | null> {
  const parsed = parseStoragePath(fullPath)
  if (!parsed) {
    console.error('Invalid storage path:', fullPath)
    return null
  }
  return getSignedUrl(parsed.bucket, parsed.path, expiresIn)
}

/**
 * Download a file as a blob
 */
export async function downloadFile(
  bucket: BucketName,
  path: string
): Promise<Blob | null> {
  const { data, error } = await supabase.storage
    .from(bucket)
    .download(path)

  if (error) {
    console.error('Error downloading file:', error)
    return null
  }

  return data
}

/**
 * Download a file and trigger browser download
 */
export async function downloadFileToDevice(
  bucket: BucketName,
  path: string,
  filename?: string
): Promise<boolean> {
  const blob = await downloadFile(bucket, path)
  if (!blob) return false

  // Create download link
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename || path.split('/').pop() || 'download'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)

  return true
}

/**
 * Upload a file to Supabase Storage
 */
export async function uploadFile(
  file: File,
  itemNumber: string,
  revision: string,
  iteration: number,
  onProgress?: (progress: number) => void
): Promise<{ path: string; bucket: BucketName } | null> {
  const bucket = getBucketForFile(file.name)
  const path = buildStoragePath(itemNumber, revision, iteration, file.name)

  const { data, error } = await supabase.storage
    .from(bucket)
    .upload(path, file, {
      cacheControl: '3600',
      upsert: true  // Overwrite if exists
    })

  if (error) {
    console.error('Error uploading file:', error)
    return null
  }

  return {
    path: `${bucket}/${path}`,
    bucket
  }
}

/**
 * Create or update a file record in the database after upload
 */
export async function createFileRecord(
  itemId: string,
  filename: string,
  storagePath: string,
  fileSize: number,
  revision?: string,
  iteration?: number
): Promise<{ id: string } | null> {
  const fileType = getFileType(filename)

  // Check if file record exists
  const { data: existing } = await supabase
    .from('files')
    .select('id')
    .eq('item_id', itemId)
    .eq('file_name', filename)
    .single()

  if (existing) {
    // Update existing record
    const { data, error } = await supabase
      .from('files')
      .update({
        file_path: storagePath,
        file_size: fileSize,
        revision,
        iteration
      })
      .eq('id', existing.id)
      .select('id')
      .single()

    if (error) {
      console.error('Error updating file record:', error)
      return null
    }
    return data
  }

  // Create new record
  const { data, error } = await supabase
    .from('files')
    .insert({
      item_id: itemId,
      file_type: fileType,
      file_name: filename,
      file_path: storagePath,
      file_size: fileSize,
      revision,
      iteration
    })
    .select('id')
    .single()

  if (error) {
    console.error('Error creating file record:', error)
    return null
  }

  return data
}

/**
 * Upload a file and create the database record
 */
export async function uploadFileWithRecord(
  file: File,
  itemId: string,
  itemNumber: string,
  revision: string,
  iteration: number,
  onProgress?: (progress: number) => void
): Promise<{ fileId: string; storagePath: string } | null> {
  // Upload to storage
  const uploadResult = await uploadFile(file, itemNumber, revision, iteration, onProgress)
  if (!uploadResult) return null

  // Create database record
  const fileRecord = await createFileRecord(
    itemId,
    file.name,
    uploadResult.path,
    file.size,
    revision,
    iteration
  )

  if (!fileRecord) return null

  return {
    fileId: fileRecord.id,
    storagePath: uploadResult.path
  }
}

/**
 * Delete a file from storage and database
 */
export async function deleteFile(
  fileId: string,
  storagePath: string
): Promise<boolean> {
  const parsed = parseStoragePath(storagePath)
  if (!parsed) {
    console.error('Invalid storage path:', storagePath)
    return false
  }

  // Delete from storage
  const { error: storageError } = await supabase.storage
    .from(parsed.bucket)
    .remove([parsed.path])

  if (storageError) {
    console.error('Error deleting from storage:', storageError)
    // Continue to delete database record anyway
  }

  // Delete database record
  const { error: dbError } = await supabase
    .from('files')
    .delete()
    .eq('id', fileId)

  if (dbError) {
    console.error('Error deleting file record:', dbError)
    return false
  }

  return true
}

/**
 * List files in a directory (for debugging/admin)
 */
export async function listFiles(
  bucket: BucketName,
  path: string
): Promise<{ name: string; size: number }[] | null> {
  const { data, error } = await supabase.storage
    .from(bucket)
    .list(path)

  if (error) {
    console.error('Error listing files:', error)
    return null
  }

  return data.map(f => ({
    name: f.name,
    size: f.metadata?.size || 0
  }))
}
