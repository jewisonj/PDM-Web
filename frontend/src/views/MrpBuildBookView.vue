<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { supabase } from '../services/supabase'
import { calculateSchedule, type PartData, type BomData, type RoutingData } from '../utils/scheduling'
import { buildBook, type BuildBook } from '../utils/buildBook'

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const errorMsg = ref('')
const book = ref<BuildBook | null>(null)
const generatingPdf = ref(false)
const pdfMsg = ref('')

const projectCode = String(route.params.projectCode || '')
const prevTitle = document.title

async function loadAll() {
  loading.value = true
  errorMsg.value = ''
  try {
    const { data: project, error: projErr } = await supabase
      .from('mrp_projects')
      .select('*')
      .eq('project_code', projectCode)
      .single()
    if (projErr || !project) throw new Error(`Project "${projectCode}" not found`)

    const { data: partsData, error: partsErr } = await supabase
      .from('mrp_project_parts')
      .select('item_id, quantity, items (id, item_number, name, description, thickness, material, supplier_pn, supplier_name, revision)')
      .eq('project_id', project.id)
    if (partsErr) throw partsErr

    const itemIds = (partsData || []).map(p => p.item_id)

    const [
      { data: completionData },
      { data: bomData },
      { data: routingData },
      { data: stationsData },
      { data: materialsData },
      { data: printFiles },
    ] = await Promise.all([
      supabase
        .from('part_completion')
        .select('item_id, station_id, qty_complete, completed_at')
        .eq('project_id', project.id),
      supabase
        .from('bom')
        .select('parent_item_id, child_item_id, quantity')
        .or(`parent_item_id.in.(${itemIds.join(',')}),child_item_id.in.(${itemIds.join(',')})`),
      supabase
        .from('routing')
        .select('id, item_id, station_id, sequence, est_time_min, notes, workstations (station_code, station_name)')
        .in('item_id', itemIds)
        .order('sequence'),
      supabase.from('workstations').select('id, station_code, station_name, station_group, sort_order'),
      supabase
        .from('routing_materials')
        .select('item_id, qty_required, raw_materials (description, material_code)')
        .in('item_id', itemIds),
      supabase
        .from('files')
        .select('item_id')
        .eq('file_type', 'PDF')
        .not('file_path', 'is', null)
        .in('item_id', itemIds),
    ])

    const schedule = calculateSchedule(
      (partsData || []).map(p => ({
        item_id: p.item_id,
        quantity: p.quantity,
        items: (p as any).items,
      })) as PartData[],
      (bomData || []) as BomData[],
      (routingData || []).map(r => ({ ...r, workstations: (r as any).workstations })) as RoutingData[],
      (completionData || []).map(c => ({ item_id: c.item_id, station_id: c.station_id }))
    )

    book.value = buildBook({
      project: project as any,
      parts: (partsData || []).map(p => ({
        item_id: p.item_id,
        quantity: p.quantity,
        items: (p as any).items,
      })),
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

    document.title = `BOOK_${projectCode}_${fmtIso(book.value.generatedAt)}`
  } catch (e: any) {
    console.error('Build book load failed:', e)
    errorMsg.value = e?.message || 'Failed to load project data'
  } finally {
    loading.value = false
  }
}

function fmtIso(d: Date): string {
  return d.toISOString().split('T')[0] ?? ''
}
function fmtStamp(d: Date): string {
  const t = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  return `${fmtIso(d)} ${t}`
}
function hrs(min: number): string {
  return (min / 60).toFixed(1)
}
function printBook() {
  window.print()
}

interface PrintSection {
  key: string
  group: string
  label: string
  items: { item_number: string; qty: number | null }[]
}

const sections = computed<PrintSection[]>(() => {
  if (!book.value) return []
  const out: PrintSection[] = []
  if (book.value.referenceDocs.length) {
    out.push({
      key: 'ref',
      group: 'Reference',
      label: 'Design Reference Prints',
      items: book.value.referenceDocs.map(d => ({ item_number: d.item_number, qty: null })),
    })
  }
  // secondary ops (deburr/inspection) never become packages — see SECONDARY_STATIONS
  for (const p of book.value.packages) {
    out.push({
      key: p.id,
      group: 'Work packages',
      label: `${p.id} — ${p.stationName}`,
      items: p.lines.map(l => ({ item_number: l.item_number, qty: l.qty })),
    })
  }
  for (const k of book.value.kits) {
    out.push({
      key: k.rid,
      group: 'Kits',
      label: `${k.rid} — ${k.name}`,
      items: [
        { item_number: k.item_number, qty: k.qty },
        ...k.parts.map(pt => ({ item_number: pt.item_number, qty: pt.qty })),
      ],
    })
  }
  return out
})
const sectionGroups = computed(() => [...new Set(sections.value.map(s => s.group))])
const selectedSection = ref('')

async function downloadSectionPrints() {
  const section = sections.value.find(s => s.key === selectedSection.value)
  if (!book.value || !section || generatingPdf.value) return
  generatingPdf.value = true
  pdfMsg.value = ''
  try {
    const resp = await fetch(`/api/mrp/projects/${book.value.project.id}/section-prints`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ label: section.label, items: section.items }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
      throw new Error(err.detail || `HTTP ${resp.status}`)
    }
    const blob = await resp.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${book.value.project.project_code}_${section.label.replace(/[^\w-]+/g, '_')}.pdf`
    a.click()
    URL.revokeObjectURL(a.href)
    const prints = resp.headers.get('X-Prints-Bound')
    const missing = Number(resp.headers.get('X-Missing') || 0)
    pdfMsg.value = `${prints ?? '?'} prints` + (missing ? ` · ${missing} missing` : '')
  } catch (e: any) {
    console.error('Section prints failed:', e)
    pdfMsg.value = e?.message || 'Download failed'
  } finally {
    generatingPdf.value = false
  }
}
function goTracking() {
  router.push('/mrp/tracking')
}
function goTracker() {
  router.push(`/mrp/tracker/${projectCode}`)
}

onMounted(loadAll)
onUnmounted(() => {
  document.title = prevTitle
})
</script>

<template>
  <div class="book-page">
    <!-- screen toolbar -->
    <div class="toolbar">
      <div class="tb-left">
        <button class="btn btn-secondary" @click="goTracking">&larr; Tracking</button>
        <h1>{{ projectCode }} — Build Book</h1>
      </div>
      <div class="tb-right">
        <span v-if="pdfMsg" class="pdf-msg">{{ pdfMsg }}</span>
        <button class="btn btn-secondary" @click="goTracker">Tracker Sheet</button>
        <select v-model="selectedSection" class="section-select" :disabled="!book">
          <option value="">— Print set —</option>
          <optgroup v-for="g in sectionGroups" :key="g" :label="g">
            <option v-for="s in sections.filter(s => s.group === g)" :key="s.key" :value="s.key">
              {{ s.label }}
            </option>
          </optgroup>
        </select>
        <button
          class="btn btn-secondary"
          :disabled="generatingPdf || !selectedSection"
          @click="downloadSectionPrints"
        >
          {{ generatingPdf ? 'Gathering…' : '⬇ Download prints' }}
        </button>
        <button class="btn btn-primary" @click="printBook">Print (8.5×11 portrait)</button>
      </div>
    </div>

    <div v-if="loading" class="msg">Building the book from the live schedule…</div>
    <div v-else-if="errorMsg" class="msg error">{{ errorMsg }}</div>

    <div v-else-if="book" class="paper-col">
      <!-- ============ COVER / PLAN ============ -->
      <section class="sheet cover">
        <div class="eyebrow">MANUFACTURING BUILD BOOK</div>
        <h2 class="title">
          {{ book.project.project_code }}
          <span v-if="book.project.description"> — {{ book.project.description.toUpperCase() }}</span>
        </h2>
        <div class="meta">
          Customer <b>{{ book.project.customer || '—' }}</b> ·
          Start <b>{{ book.startDate ? fmtIso(book.startDate) : '—' }}</b> ·
          Ship <b>{{ book.project.due_date || '—' }}</b> ·
          Generated <b>{{ fmtStamp(book.generatedAt) }}</b>
        </div>
        <div class="note">
          WORK THE PACKAGES IN ORDER — PKG numbers govern, printed days are the plan.
          Boxes shown solid were already recorded complete in the system when this book was generated.
        </div>

        <div class="stats">
          <div class="stat"><div class="v">{{ book.summary.totalHours }}</div><div class="l">EST HOURS</div></div>
          <div class="stat"><div class="v">{{ book.summary.totalDays }}</div><div class="l">WORK DAYS</div></div>
          <div class="stat"><div class="v">{{ book.summary.packageCount }}</div><div class="l">PACKAGES</div></div>
          <div class="stat"><div class="v">{{ book.summary.fabParts }}</div><div class="l">FAB PARTS</div></div>
          <div class="stat"><div class="v">{{ book.summary.assemblies }}</div><div class="l">WELDMENTS/ASSYS</div></div>
          <div class="stat"><div class="v">{{ book.summary.purchased }}</div><div class="l">PURCHASED</div></div>
        </div>

        <div class="cover-grid">
          <div>
            <div class="sec-t">MILESTONES</div>
            <table class="ms">
              <tbody>
                <tr><th>OP</th><th>MILESTONE</th><th class="c">PLAN</th><th class="c">ACTUAL</th></tr>
                <tr v-for="m in book.milestones" :key="m.rid" :class="{ gate: m.gate }">
                  <td class="c b">{{ m.op }}</td>
                  <td>{{ m.title }}</td>
                  <td class="c">{{ m.plan || '—' }}</td>
                  <td class="c done-ink">{{ m.actual }}</td>
                </tr>
              </tbody>
            </table>

            <div class="sec-t" style="margin-top:14px">HOURS BY AREA</div>
            <table>
              <tbody>
                <tr><th>AREA</th><th class="c">EST HOURS</th></tr>
                <tr v-for="g in book.summary.byGroup" :key="g.group">
                  <td>{{ g.group }}</td><td class="c">{{ g.hours }}</td>
                </tr>
              </tbody>
            </table>

            <template v-if="book.referenceDocs.length">
              <div class="sec-t" style="margin-top:14px">REFERENCE PRINTS — READ FIRST</div>
              <table>
                <tbody>
                  <tr><th>DOC #</th><th>TITLE</th><th class="c">REV</th><th class="c">PDF</th></tr>
                  <tr v-for="d in book.referenceDocs" :key="d.item_number">
                    <td class="b">{{ d.item_number }}</td>
                    <td>{{ d.name }}</td>
                    <td class="c">{{ d.revision || '—' }}</td>
                    <td class="c">{{ d.hasPrint ? '✓' : '—' }}</td>
                  </tr>
                </tbody>
              </table>
              <div class="dim" style="margin-top:2px">Bound in front of the PDF edition · latest revision pulled at generation</div>
            </template>
          </div>
          <div>
            <div class="sec-t">STOCK PULL SUMMARY</div>
            <table>
              <tbody>
                <tr><th>RAW MATERIAL</th><th class="c">TOTAL QTY</th><th class="c">PARTS</th></tr>
                <tr v-for="s in book.stock" :key="s.description">
                  <td>{{ s.description }}</td>
                  <td class="c">{{ s.qty }}</td>
                  <td class="c">{{ s.parts }}</td>
                </tr>
                <tr v-if="!book.stock.length"><td colspan="3" class="dim">No routing materials assigned</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <!-- ============ CALENDAR ============ -->
      <section class="sheet">
        <div class="sec-t big">DAY-BY-DAY STATION LOADING <small>HOURS PER STATION · PKG REFS</small></div>
        <div class="cal-wrap">
          <table class="cal">
            <tbody>
              <tr>
                <th class="dt">DAY</th>
                <th v-for="s in book.calendar.stations" :key="s.code" class="c">{{ s.abbrev }}</th>
              </tr>
              <tr v-for="d in book.calendar.days" :key="d.day">
                <td class="dt b">D{{ d.day + 1 }} · {{ d.date }}</td>
                <td v-for="(c, ci) in d.cells" :key="ci" class="c cell" :class="{ empty: !c }">
                  <template v-if="c">
                    <div class="h">{{ c.hours }}h</div>
                    <div v-if="c.pkgs.length" class="p">{{ c.pkgs.map(p => p.replace('PKG ', '#')).join(' ') }}</div>
                  </template>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- ============ WORK PACKAGES ============ -->
      <section class="sheet">
        <div class="sec-t big">PART I — WORK PACKAGES <small>WORK IN ORDER · CHECK OFF LINES · SIGN EACH PACKAGE</small></div>

        <div v-for="p in book.packages" :key="p.id" class="card" :class="{ 'is-done': p.done }">
          <div class="card-hd">
            <span class="pkg-id">{{ p.id }}</span>
            <span class="pkg-station">{{ p.stationName.toUpperCase() }}</span>
            <span class="pkg-meta">DAY {{ p.day + 1 }}<template v-if="p.date"> · {{ p.date }}</template> · EST {{ hrs(p.estMin) }} H</span>
            <span v-if="p.done" class="badge-done">✔ RECORDED COMPLETE</span>
          </div>

          <div v-if="p.stockPull.length" class="stock">
            <b>PULL STOCK:</b>
            <span v-for="(s, si) in p.stockPull" :key="si">
              {{ s.qty }} — {{ s.description }} ({{ s.parts }} part{{ s.parts > 1 ? 's' : '' }})<span v-if="si < p.stockPull.length - 1"> · </span>
            </span>
          </div>

          <table>
            <tbody>
              <tr>
                <th class="bx"></th><th>PART #</th><th>DESCRIPTION</th><th class="c">QTY</th>
                <th class="c">MIN</th><th class="c">NEXT →</th><th>FOR KIT</th>
              </tr>
              <tr v-for="l in p.lines" :key="l.item_number">
                <td class="bx"><span class="cb" :class="{ pfd: l.done }"></span></td>
                <td class="b">{{ l.displayNumber }}</td>
                <td class="pd">{{ l.name }}</td>
                <td class="c b">{{ l.qty }}</td>
                <td class="c">{{ l.estMin }}</td>
                <td class="c">{{ l.next || '— last op' }}</td>
                <td>{{ l.feeds.join(', ') }}</td>
              </tr>
            </tbody>
          </table>

          <div class="card-ft">
            <span v-if="p.stageFor.length"><b>STAGE KITS:</b> {{ p.stageFor.join(', ') }}</span>
            <span v-else></span>
            <span class="sign">COMPLETED BY ______________ DATE ____ / ____</span>
          </div>
        </div>
      </section>

      <!-- ============ KIT CHAPTERS ============ -->
      <section class="sheet">
        <div class="sec-t big">PART II — KIT &amp; WELD SHEETS <small>ONE PER WELDMENT/ASSEMBLY · BUILD ORDER</small></div>

        <div v-for="k in book.kits" :key="k.rid" class="card kit">
          <div class="card-hd">
            <span class="pkg-id kit-id">{{ k.rid }}</span>
            <span class="pkg-station">{{ k.name }} — {{ k.item_number }}<template v-if="k.qty > 1"> (×{{ k.qty }})</template></span>
            <span class="pkg-meta">
              <template v-if="k.startDay !== null">PLAN D{{ k.startDay + 1 }}–D{{ (k.endDay ?? k.startDay) + 1 }}<template v-if="k.startDate"> · {{ k.startDate }} → {{ k.endDate }}</template> · </template>
              EST {{ hrs(k.estMin) }} H
            </span>
          </div>

          <div v-if="k.childAsms.length" class="stock">
            <b>REQUIRES SUB-ASSEMBLIES:</b>
            {{ k.childAsms.map(c => `${c.rid} ${c.name}`).join(' · ') }}
          </div>

          <div class="kit-grid">
            <div>
              <div class="mini-t">KIT — PARTS REQUIRED</div>
              <table>
                <tbody>
                  <tr><th class="bx"></th><th>ID</th><th>PART #</th><th>DESCRIPTION</th><th class="c">QTY</th><th class="c">READY BY</th></tr>
                  <tr v-for="pt in k.parts" :key="pt.rid">
                    <td class="bx"><span class="cb" :class="{ pfd: pt.done }"></span></td>
                    <td class="c dim">{{ pt.rid }}</td>
                    <td class="b">{{ pt.item_number }}</td>
                    <td class="pd">{{ pt.name }}</td>
                    <td class="c b">{{ pt.qty }}</td>
                    <td class="c">{{ pt.readyBy ? `${pt.readyBy} · D${(pt.readyDay ?? 0) + 1}` : '—' }}</td>
                  </tr>
                  <tr v-if="!k.parts.length"><td colspan="6" class="dim">No loose parts — assembles from sub-assemblies + purchased</td></tr>
                </tbody>
              </table>
            </div>
            <div>
              <div class="mini-t">SEQUENCE</div>
              <table>
                <tbody>
                  <tr><th class="bx"></th><th>STEP</th><th class="c">EST MIN</th></tr>
                  <tr v-for="(w, wi) in k.weldSeq" :key="wi">
                    <td class="bx"><span class="cb" :class="{ pfd: w.done }"></span></td>
                    <td>
                      {{ wi + 1 }}0 — {{ w.station }}
                      <div v-if="w.notes" class="step-note">{{ w.notes }}</div>
                    </td>
                    <td class="c">{{ w.estMin }}</td>
                  </tr>
                </tbody>
              </table>
              <div class="prints" v-if="k.printRefs.length">
                PULL PRINTS:
                <span class="refs">{{ k.printRefs.map(r => r.item_number + (r.revision ? ' R' + r.revision : '')).join(' · ') }}</span>
              </div>
              <div class="prints" v-else>PRINTS: none on file for this kit</div>
            </div>
          </div>

          <div class="card-ft">
            <span><b>INSPECT:</b> welds complete · cleanup · dimensions per print</span>
            <span class="sign">INSPECTED BY ______________ DATE ____ / ____</span>
          </div>
        </div>

        <div class="book-end">
          END OF BOOK — {{ book.project.project_code }} · GENERATED {{ fmtStamp(book.generatedAt) }} ·
          REGENERATE AFTER SCHEDULE OR BOM CHANGES
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
/* ---------- screen chrome (MRP dark theme) ---------- */
.book-page { min-height: 100vh; background: #020617; color: #e5e7eb; }
.toolbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 24px; background: #0f172a; border-bottom: 1px solid #1e293b;
  flex-wrap: wrap; gap: 12px;
}
.tb-left, .tb-right { display: flex; align-items: center; gap: 12px; }
.toolbar h1 { margin: 0; font-size: 20px; }
.btn { padding: 8px 16px; border-radius: 6px; border: none; cursor: pointer; font-size: 13px; font-weight: 500; }
.btn-secondary { background: #374151; color: white; }
.btn-secondary:hover { background: #4b5563; }
.btn-primary { background: #2563eb; color: white; }
.btn-primary:hover { background: #1d4ed8; }
.msg { text-align: center; padding: 60px; color: #6b7280; }
.msg.error { color: #f87171; }
.pdf-msg { font-size: 12px; color: #9ca3af; }
.btn:disabled { opacity: 0.55; cursor: default; }
.section-select {
  padding: 8px 10px; border-radius: 6px; border: 1px solid #334155;
  background: #1e293b; color: #e5e7eb; font-size: 13px; max-width: 240px;
}

/* ---------- paper ---------- */
.paper-col { max-width: 856px; margin: 0 auto; padding: 20px 16px 60px; }
.sheet {
  background: #fff; color: #16181a;
  font-family: Arial, Helvetica, sans-serif; font-variant-numeric: tabular-nums;
  padding: 34px 38px; margin-bottom: 18px;
  box-shadow: 0 3px 22px rgba(0, 0, 0, 0.5);
}

.eyebrow { font-size: 10px; font-weight: bold; letter-spacing: 2.6px; }
.title { font-size: 26px; font-weight: bold; margin: 4px 0 6px; line-height: 1.1; }
.meta { font-size: 11px; }
.note {
  border: 1.5px solid #16181a; padding: 7px 10px; font-size: 9.5px; font-weight: bold;
  letter-spacing: 0.3px; margin: 12px 0;
}
.stats { display: flex; gap: 8px; margin: 14px 0 18px; }
.stat { flex: 1; border: 1.5px solid #16181a; text-align: center; padding: 7px 4px; }
.stat .v { font-size: 19px; font-weight: bold; }
.stat .l { font-size: 6.8px; font-weight: bold; letter-spacing: 0.9px; margin-top: 2px; }
.cover-grid { display: grid; grid-template-columns: 1.15fr 1fr; gap: 0 22px; }

.sec-t {
  font-size: 10.5px; font-weight: bold; letter-spacing: 1.6px;
  border-bottom: 2px solid #16181a; padding-bottom: 2px; margin-bottom: 6px;
  display: flex; justify-content: space-between; align-items: baseline;
}
.sec-t.big { font-size: 13px; margin-bottom: 12px; }
.sec-t small { font-weight: normal; font-size: 8px; letter-spacing: 0.4px; }
.mini-t { font-size: 8.5px; font-weight: bold; letter-spacing: 1px; margin-bottom: 3px; }

.sheet table { border-collapse: collapse; width: 100%; }
.sheet td, .sheet th { border: 0.75px solid #c9cdd1; padding: 2px 5px; font-size: 9.5px; }
.sheet th {
  background: #f1f2f3; font-size: 8px; letter-spacing: 0.5px; text-align: left;
  border-bottom: 1.25px solid #9aa0a5;
}
.sheet th.c, .sheet td.c { text-align: center; }
.b { font-weight: bold; }
.dim { color: #6b7075; font-size: 8.5px; }
.pd { max-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.ms tr.gate td { background: #e4e6e8; font-weight: bold; border-top: 1.5px solid #16181a; border-bottom: 1.5px solid #16181a; }
.done-ink { font-weight: bold; }

/* calendar */
.cal-wrap { overflow-x: auto; }
.cal .dt { white-space: nowrap; }
.cal .cell { min-width: 46px; }
.cal .cell.empty { background: #f7f8f8; }
.cal .h { font-weight: bold; }
.cal .p { font-size: 7px; letter-spacing: 0.2px; }

/* cards */
.card { border: 1.5px solid #16181a; margin-bottom: 12px; break-inside: avoid; page-break-inside: avoid; }
.card-hd {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  background: #16181a; color: #fff; padding: 4px 8px;
}
.pkg-id { font-size: 12px; font-weight: bold; letter-spacing: 0.6px; }
.kit-id { background: #fff; color: #16181a; padding: 0 6px; }
.pkg-station { font-size: 11px; font-weight: bold; letter-spacing: 0.4px; flex: 1; }
.pkg-meta { font-size: 8.5px; letter-spacing: 0.4px; }
.badge-done { font-size: 8.5px; font-weight: bold; border: 1px solid #fff; padding: 1px 6px; }
.card.is-done { border-color: #9aa0a5; }
.card.is-done .card-hd { background: #6b7075; }

.stock { font-size: 9px; padding: 4px 8px; background: #f1f2f3; border-bottom: 0.75px solid #c9cdd1; }
.card table { border-style: none; }
.card td, .card th { border-left: none; border-right: none; }
.bx { width: 26px; text-align: center; }
.cb { display: inline-block; width: 12px; height: 12px; border: 1.5px solid #16181a; background: #fff; vertical-align: -2px; }
.cb.pfd { background: #16181a; }

.card-ft {
  display: flex; justify-content: space-between; align-items: center; gap: 10px;
  padding: 4px 8px; font-size: 8.5px; border-top: 1.25px solid #9aa0a5;
}
.sign { letter-spacing: 0.4px; }

.kit-grid { display: grid; grid-template-columns: 1.5fr 1fr; gap: 8px; padding: 6px 8px; }
.kit-grid table { border: 0.75px solid #c9cdd1; }
.step-note {
  font-size: 8.5px; line-height: 1.45; white-space: normal;
  border-left: 2.5px solid #16181a; padding: 2px 0 2px 6px; margin: 2px 0 3px;
}
.prints { font-size: 8.5px; margin-top: 6px; font-weight: bold; }
.prints .refs { font-weight: normal; }
.prints .dim { font-weight: normal; }

.book-end {
  text-align: center; font-size: 8.5px; font-weight: bold; letter-spacing: 1px;
  border-top: 2px solid #16181a; padding-top: 8px; margin-top: 18px;
}
</style>

<style>
@media print {
  body { background: #fff !important; }
  .book-page .toolbar { display: none !important; }
  .book-page { background: #fff !important; }
  .book-page .paper-col { max-width: none; padding: 0; }
  .book-page .sheet { box-shadow: none; margin: 0; padding: 0.15in 0; page-break-after: always; }
  .book-page .sheet:last-child { page-break-after: auto; }
  .book-page .card { break-inside: avoid; page-break-inside: avoid; }
  @page { size: 8.5in 11in; margin: 0.5in; }
}
</style>
