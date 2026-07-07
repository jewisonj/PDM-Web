/**
 * Dev script: compute the Build Book payload for a project, exactly as
 * MrpBuildBookView does, and write it to a JSON file. Useful for exercising
 * the POST /mrp/projects/{id}/build-book endpoint without a browser session.
 *
 * Uses the backend service key from backend/.env (local dev only).
 *
 * Usage:  npx tsx scripts/emit-book.ts [PROJECT_CODE] [OUT_PATH]
 */
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createClient } from '@supabase/supabase-js'
import { calculateSchedule, type PartData, type BomData, type RoutingData } from '../src/utils/scheduling'
import { buildBook } from '../src/utils/buildBook'

const here = dirname(fileURLToPath(import.meta.url))
const projectCode = process.argv[2] || 'TEST-PROG01'
const outPath = process.argv[3] || resolve(here, '../book-payload.json')

const env = Object.fromEntries(
  readFileSync(resolve(here, '../../backend/.env'), 'utf8')
    .split(/\r?\n/)
    .filter(l => l.includes('=') && !l.trim().startsWith('#'))
    .map(l => [l.slice(0, l.indexOf('=')).trim(), l.slice(l.indexOf('=') + 1).trim()])
)
const supabase = createClient(env.SUPABASE_URL!, env.SUPABASE_SERVICE_KEY!)

async function main() {
  const { data: project, error } = await supabase
    .from('mrp_projects')
    .select('*')
    .eq('project_code', projectCode)
    .single()
  if (error || !project) throw new Error(`Project ${projectCode} not found: ${error?.message}`)

  const { data: partsData } = await supabase
    .from('mrp_project_parts')
    .select('item_id, quantity, items (id, item_number, name, description, thickness, material, supplier_pn, supplier_name, revision)')
    .eq('project_id', project.id)
  const itemIds = (partsData || []).map(p => p.item_id)

  const [
    { data: completionData },
    { data: bomData },
    { data: routingData },
    { data: stationsData },
    { data: materialsData },
    { data: printFiles },
  ] = await Promise.all([
    supabase.from('part_completion').select('item_id, station_id, qty_complete, completed_at').eq('project_id', project.id),
    supabase.from('bom').select('parent_item_id, child_item_id, quantity').or(`parent_item_id.in.(${itemIds.join(',')}),child_item_id.in.(${itemIds.join(',')})`),
    supabase.from('routing').select('id, item_id, station_id, sequence, est_time_min, notes, workstations (station_code, station_name)').in('item_id', itemIds).order('sequence'),
    supabase.from('workstations').select('id, station_code, station_name, station_group, sort_order'),
    supabase.from('routing_materials').select('item_id, qty_required, raw_materials (description, material_code)').in('item_id', itemIds),
    supabase.from('files').select('item_id').eq('file_type', 'PDF').not('file_path', 'is', null).in('item_id', itemIds),
  ])

  const schedule = calculateSchedule(
    (partsData || []).map(p => ({ item_id: p.item_id, quantity: p.quantity, items: (p as any).items })) as PartData[],
    (bomData || []) as BomData[],
    (routingData || []).map(r => ({ ...r, workstations: (r as any).workstations })) as RoutingData[],
    (completionData || []).map(c => ({ item_id: c.item_id, station_id: c.station_id }))
  )

  const book = buildBook({
    project: project as any,
    parts: (partsData || []).map(p => ({ item_id: p.item_id, quantity: p.quantity, items: (p as any).items })),
    bom: (bomData || []) as any,
    routing: (routingData || []).map(r => ({ ...r, workstations: (r as any).workstations })) as any,
    completion: (completionData || []) as any,
    workstations: (stationsData || []) as any,
    schedule,
    routingMaterials: (materialsData || []).map(m => ({
      item_id: m.item_id,
      qty_required: m.qty_required,
      raw_materials: (m as any).raw_materials,
    })),
    printItemIds: [...new Set((printFiles || []).map(f => f.item_id))],
  })

  writeFileSync(outPath, JSON.stringify({ book }))
  console.log(
    `WROTE ${outPath}\n` +
      `packages=${book.packages.length} kits=${book.kits.length} refDocs=${book.referenceDocs.length} ` +
      `fabParts=${book.fabTotal ?? book.summary.fabParts} pct=${Math.round(book.pctComplete ?? 0)}`
  )
}

main().catch(e => {
  console.error(e)
  process.exit(1)
})
