<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import QRCode from 'qrcode'
import { supabase } from '../services/supabase'
import { calculateSchedule, type PartData, type BomData, type RoutingData } from '../utils/scheduling'
import {
  buildTrackerSheet,
  applyKitSourcing,
  PART_COLUMNS,
  ASM_COLUMNS,
  type TrackerSheet,
  type TrackerInputs,
  type TrackerFormat,
  type TrackerPage,
} from '../utils/buildTracker'
import { fetchProjectKitSources } from '../services/designBook'

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const errorMsg = ref('')
const sheet = ref<TrackerSheet | null>(null)
const qrUrl = ref('')
const showRecorded = ref(true)
const scale = ref(1)
const fitwrap = ref<HTMLElement | null>(null)
const format = ref<TrackerFormat>(route.query.size === 'letter' ? 'letter' : 'tabloid')

const projectCode = String(route.params.projectCode || '')
const prevTitle = document.title
let rawInputs: Omit<TrackerInputs, 'format'> | null = null

const paperW = computed(() => (format.value === 'letter' ? 1056 : 1632))
const paperH = computed(() => (format.value === 'letter' ? 816 : 1056))

function pageLayout(page: TrackerPage, pi: number): string {
  if (format.value === 'letter') return page.showRail ? 'l-status' : 'l-parts'
  return pi === 0 ? 't-main' : 't-cont'
}

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
      .select('item_id, quantity, items (id, item_number, name, description, thickness, material, supplier_pn, supplier_name)')
      .eq('project_id', project.id)
    if (partsErr) throw partsErr

    const itemIds = (partsData || []).map(p => p.item_id)

    const [{ data: completionData }, { data: bomData }, { data: routingData }, { data: stationsData }, kitSources] =
      await Promise.all([
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
          .select('id, item_id, station_id, sequence, est_time_min, workstations (station_code, station_name)')
          .in('item_id', itemIds)
          .order('sequence'),
        supabase.from('workstations').select('id, station_code, station_name, station_group'),
        fetchProjectKitSources(project.id),
      ])

    const bom = (bomData || []) as any
    const workstations = (stationsData || []) as any
    // kit-sourced parts are received/inspected/staged, not made — synthesize that
    // routing before scheduling so the tracker agrees with the master book. (No
    // routing_materials here — the tracker has no stock-pull section.)
    const sourced = applyKitSourcing({
      routing: (routingData || []).map(r => ({ ...r, workstations: (r as any).workstations })) as any,
      kitSources,
      workstations,
      bom,
    })

    const schedule = calculateSchedule(
      (partsData || []).map(p => ({
        item_id: p.item_id,
        quantity: p.quantity,
        items: (p as any).items,
      })) as PartData[],
      bom as BomData[],
      sourced.routing as unknown as RoutingData[],
      (completionData || []).map(c => ({ item_id: c.item_id, station_id: c.station_id }))
    )

    rawInputs = {
      project: project as any,
      parts: (partsData || []).map(p => ({
        item_id: p.item_id,
        quantity: p.quantity,
        items: (p as any).items,
      })),
      bom,
      routing: sourced.routing as any,
      completion: (completionData || []) as any,
      workstations,
      schedule,
      kitSources,
    }
    rebuild()

    qrUrl.value = await QRCode.toDataURL(`${window.location.origin}/mrp/tracker/${projectCode}`, {
      margin: 0,
      width: 168,
      errorCorrectionLevel: 'M',
    })
  } catch (e: any) {
    console.error('Build tracker load failed:', e)
    errorMsg.value = e?.message || 'Failed to load project data'
  } finally {
    loading.value = false
  }
}

function rebuild() {
  if (!rawInputs) return
  sheet.value = buildTrackerSheet({ ...rawInputs, format: format.value })
  document.title = `TRK_${projectCode}_${fmtIso(sheet.value.generatedAt)}${format.value === 'letter' ? '_LTR' : ''}`
}

function setFormat(f: TrackerFormat) {
  if (format.value === f) return
  format.value = f
  rebuild()
  router.replace({ query: { ...route.query, size: f === 'letter' ? 'letter' : undefined } })
  nextTick(fit)
}

function fmtIso(d: Date): string {
  return d.toISOString().split('T')[0] ?? ''
}
function fmtStamp(d: Date): string {
  const t = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  return `${fmtIso(d)} ${t}`
}
function segFilled(idx: number): boolean {
  if (!sheet.value) return false
  return idx <= Math.floor(sheet.value.pctComplete / 10)
}
function fit() {
  const w = fitwrap.value?.clientWidth || paperW.value
  scale.value = Math.min(1, (w - 8) / paperW.value)
}
function printSheet() {
  window.print()
}
function goBack() {
  router.push('/mrp/tracking')
}

// keep the printed page size in sync with the selected format
const pageStyleEl = document.createElement('style')
watch(
  format,
  f => {
    pageStyleEl.textContent = `@media print { @page { size: ${f === 'letter' ? '11in 8.5in' : '17in 11in'}; margin: 0; } }`
  },
  { immediate: true }
)

onMounted(async () => {
  document.head.appendChild(pageStyleEl)
  await loadAll()
  fit()
  window.addEventListener('resize', fit)
})
onUnmounted(() => {
  window.removeEventListener('resize', fit)
  pageStyleEl.remove()
  document.title = prevTitle
})
</script>

<template>
  <div class="tracker-page" :class="{ 'hide-recorded': !showRecorded }">
    <!-- screen toolbar -->
    <div class="toolbar">
      <div class="tb-left">
        <button class="btn btn-secondary" @click="goBack">&larr; Tracking</button>
        <h1>{{ projectCode }} — Build Tracker</h1>
      </div>
      <div class="tb-right">
        <button class="btn btn-secondary" @click="router.push(`/mrp/book/${projectCode}`)">
          📖 Build Book
        </button>
        <div class="seggroup" role="group" aria-label="Paper size">
          <button class="btn seg-btn" :class="{ active: format === 'tabloid' }" @click="setFormat('tabloid')">
            11×17 · 1 page
          </button>
          <button class="btn seg-btn" :class="{ active: format === 'letter' }" @click="setFormat('letter')">
            Letter · {{ format === 'letter' && sheet ? sheet.pages.length : 3 }} pages
          </button>
        </div>
        <label class="chk">
          <input type="checkbox" v-model="showRecorded" />
          Pre-fill recorded progress
        </label>
        <button class="btn btn-primary" @click="printSheet">
          Print ({{ format === 'letter' ? '8.5×11' : '11×17' }} landscape)
        </button>
      </div>
    </div>

    <div v-if="loading" class="msg">Generating tracker sheet…</div>
    <div v-else-if="errorMsg" class="msg error">{{ errorMsg }}</div>

    <div v-else-if="sheet" ref="fitwrap" class="fitwrap">
      <div
        v-for="(page, pi) in sheet.pages"
        :key="pi"
        class="page-slot"
        :style="{ height: paperH * scale + 24 + 'px' }"
      >
        <div class="paper" :class="{ letter: sheet.format === 'letter' }" :style="{ transform: `scale(${scale})` }">
          <div class="anch tr"></div>
          <div class="anch bl"></div>
          <div class="anch br"></div>

          <!-- header (full on page 1, slim on later pages) -->
          <div v-if="pi === 0" class="hd">
            <div class="qr">
              <img v-if="qrUrl" :src="qrUrl" :width="sheet.format === 'letter' ? 66 : 84" :height="sheet.format === 'letter' ? 66 : 84" alt="QR link to live tracker" />
              <div class="lbl">SCAN → LIVE TRACKER</div>
            </div>
            <div class="id">
              <div class="eyebrow">BUILD TRACKER</div>
              <div class="proj">
                {{ sheet.project.project_code }}
                <span v-if="sheet.project.description"> — {{ sheet.project.description.toUpperCase() }}</span>
              </div>
              <div class="projsub">
                Customer <b>{{ sheet.project.customer || '—' }}</b> ·
                <b>{{ sheet.fabTotal }}</b> fab parts · <b>{{ sheet.asmTotal }}</b> weldments &amp; assemblies ·
                <b>{{ sheet.purchasedTotal }}</b> purchased ·
                Start <b>{{ sheet.startDate ? fmtIso(sheet.startDate) : '—' }}</b> ·
                Ship <b>{{ sheet.project.due_date || '—' }}</b>
              </div>
            </div>
            <div class="rev">
              <div class="big">PRINTED {{ fmtStamp(sheet.generatedAt) }}</div>
              Pre-filled from system at print time.<br />
              Prints &amp; work instructions: see project packet.
              <div class="warn">▲ LATEST PRINT WINS — DESTROY OLDER SHEETS</div>
            </div>
            <div class="glance">
              <div class="fracs">
                <div class="frac">
                  <div class="t">FAB PARTS DONE</div>
                  <div class="v"><span class="pf big-n">{{ sheet.fabDone }}</span><span class="of">/ {{ sheet.fabTotal }}</span></div>
                </div>
                <div class="frac">
                  <div class="t">WELDMENTS &amp; ASSYS DONE</div>
                  <div class="v"><span class="pf big-n">{{ sheet.asmDone }}</span><span class="of">/ {{ sheet.asmTotal }}</span></div>
                </div>
              </div>
              <div class="pbar">
                <div class="t">
                  <span>OVERALL — FILL ONE SEGMENT PER 10%</span>
                  <span class="pf">{{ Math.round(sheet.pctComplete) }}% AT PRINT</span>
                </div>
                <div class="segs">
                  <div v-for="i in 10" :key="i" class="seg">
                    <span v-if="segFilled(i)" class="segfill pf"></span>
                    <i>{{ i * 10 }}</i>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="hd slim">
            <div class="proj sm">
              {{ sheet.project.project_code }} — BUILD TRACKER
              <span v-if="page.showRail">· ASSEMBLIES &amp; STATUS</span>
              <span v-else>(CONT.)</span>
            </div>
            <div class="rev slim">PRINTED {{ fmtStamp(sheet.generatedAt) }}</div>
          </div>

          <!-- body -->
          <div class="bd" :class="pageLayout(page, pi)">
            <!-- parts column A -->
            <div v-if="page.colA.length" class="gA">
              <div class="sec">
                <div class="sec-t">
                  FAB PARTS <small>GROUPED BY PARENT · ▸STG = STAGED TO FAB/ASSY</small>
                </div>
                <table>
                  <tbody>
                    <tr>
                      <th class="rid">ID</th><th class="pn">PART #</th><th>DESCRIPTION</th><th class="q">QTY</th>
                      <th v-for="c in PART_COLUMNS" :key="c.key" class="bx" :class="{ gate: c.gate }">{{ c.label }}</th>
                    </tr>
                    <template v-for="g in page.colA" :key="g.ref + g.assembly_number + (g.cont ? 'c' : '')">
                      <tr class="grp">
                        <td class="gref">{{ g.ref }}</td>
                        <td colspan="3">{{ g.name }}<span v-if="g.assembly_number"> — {{ g.assembly_number }}</span><span v-if="g.cont"> (CONT.)</span></td>
                        <td colspan="7" class="gfrac">parts staged <span class="pf">{{ g.readyDone }}</span> / {{ g.readyTotal }}</td>
                      </tr>
                      <tr v-for="r in g.rows" :key="r.rid">
                        <td class="rid">{{ r.rid }}</td>
                        <td class="pn">{{ r.item_number }}</td>
                        <td class="pd">{{ r.name }}</td>
                        <td class="q">{{ r.qty }}</td>
                        <td v-for="(b, bi) in r.boxes" :key="bi" class="bx" :class="{ na: !b.applicable, gate: b.gate }">
                          <span class="cb" :class="{ pfd: b.done }"><span v-if="b.partial" class="pf tally">{{ b.partial }}</span></span>
                        </td>
                      </tr>
                    </template>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- parts column B -->
            <div v-if="page.colB.length" class="gB">
              <div class="sec">
                <div class="sec-t">FAB PARTS <small>QTY = TOTAL FOR PROJECT</small></div>
                <table>
                  <tbody>
                    <tr>
                      <th class="rid">ID</th><th class="pn">PART #</th><th>DESCRIPTION</th><th class="q">QTY</th>
                      <th v-for="c in PART_COLUMNS" :key="c.key" class="bx" :class="{ gate: c.gate }">{{ c.label }}</th>
                    </tr>
                    <template v-for="g in page.colB" :key="g.ref + g.assembly_number + (g.cont ? 'c' : '')">
                      <tr class="grp">
                        <td class="gref">{{ g.ref }}</td>
                        <td colspan="3">{{ g.name }}<span v-if="g.assembly_number"> — {{ g.assembly_number }}</span><span v-if="g.cont"> (CONT.)</span></td>
                        <td colspan="7" class="gfrac">parts staged <span class="pf">{{ g.readyDone }}</span> / {{ g.readyTotal }}</td>
                      </tr>
                      <tr v-for="r in g.rows" :key="r.rid">
                        <td class="rid">{{ r.rid }}</td>
                        <td class="pn">{{ r.item_number }}</td>
                        <td class="pd">{{ r.name }}</td>
                        <td class="q">{{ r.qty }}</td>
                        <td v-for="(b, bi) in r.boxes" :key="bi" class="bx" :class="{ na: !b.applicable, gate: b.gate }">
                          <span class="cb" :class="{ pfd: b.done }"><span v-if="b.partial" class="pf tally">{{ b.partial }}</span></span>
                        </td>
                      </tr>
                    </template>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- assembly matrix -->
            <div v-if="page.showRail" class="gM">
              <div class="sec">
                <div class="sec-t">WELDMENTS &amp; ASSEMBLIES <small>JIG→TIG→DS→CLEANUP · ASM = BUILD · INS = FINAL</small></div>
                <table class="asm">
                  <tbody>
                    <tr>
                      <th class="rid">ID</th><th class="pn">ASSY #</th><th>DESCRIPTION</th><th class="q">QTY</th><th class="rdy">PARTS RDY</th>
                      <th v-for="c in ASM_COLUMNS" :key="c.key" class="bx">{{ c.label }}</th>
                    </tr>
                    <tr v-for="a in sheet.asmRows" :key="a.rid">
                      <td class="rid">{{ a.rid }}</td>
                      <td class="pn">{{ a.item_number }}</td>
                      <td class="pd">{{ a.name }}</td>
                      <td class="q">{{ a.qty }}</td>
                      <td class="rdy"><span class="pf">{{ a.readyDone }}</span> / {{ a.readyTotal }}</td>
                      <td v-for="(b, bi) in a.boxes" :key="bi" class="bx" :class="{ na: !b.applicable }">
                        <span class="cb" :class="{ pfd: b.done }"><span v-if="b.partial" class="pf tally">{{ b.partial }}</span></span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- milestones + purchased -->
            <div v-if="page.showRail" class="gR">
              <div class="sec">
                <div class="sec-t">BUILD MILESTONES <small>PLAN FROM SCHEDULE · WRITE ACTUAL</small></div>
                <table class="ms">
                  <tbody>
                    <tr><th class="rid">ID</th><th class="op">OP</th><th>MILESTONE</th><th class="plan">PLAN</th><th class="act">ACTUAL</th><th class="ini">INIT</th></tr>
                    <tr v-for="m in sheet.milestones" :key="m.rid" :class="{ 'gate-row': m.gate }">
                      <td class="rid">{{ m.rid }}</td>
                      <td class="op">{{ m.op }}</td>
                      <td>{{ m.title }}</td>
                      <td class="plan">{{ m.plan || '—' }}</td>
                      <td class="act"><span class="pf">{{ m.actual }}</span></td>
                      <td class="ini"></td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div class="sec">
                <div class="sec-t">PURCHASED — RECEIVE CHECKLIST <small>SUPPLIER PART #s — PDM PREFIXES DROPPED</small></div>
                <table class="pur-ll" v-if="sheet.purchased.some(p => p.longLead)">
                  <tbody>
                    <tr><th class="rid">ID</th><th class="pn">PART #</th><th>DESCRIPTION — LONG LEAD</th><th class="src">SOURCE</th><th class="q">QTY</th><th class="bx sm">ORD</th><th class="bx sm">RCV</th></tr>
                    <tr v-for="p in sheet.purchased.filter(p => p.longLead)" :key="p.rid">
                      <td class="rid">{{ p.rid }}</td>
                      <td class="pn">{{ p.displayNumber }}</td>
                      <td class="pd">{{ p.name }}</td>
                      <td class="src">{{ p.source }}</td>
                      <td class="q">{{ p.qty }}</td>
                      <td class="bx sm"><span class="cb"></span></td>
                      <td class="bx sm"><span class="cb" :class="{ pfd: p.rcvDone }"><span v-if="p.rcvPartial" class="pf tally">{{ p.rcvPartial }}</span></span></td>
                    </tr>
                  </tbody>
                </table>
                <div class="pur2">
                  <table v-for="(half, hi) in [
                      sheet.purchased.filter(p => !p.longLead).slice(0, Math.ceil(sheet.purchased.filter(p => !p.longLead).length / 2)),
                      sheet.purchased.filter(p => !p.longLead).slice(Math.ceil(sheet.purchased.filter(p => !p.longLead).length / 2)),
                    ]" :key="hi">
                    <tbody>
                      <tr v-for="p in half" :key="p.rid">
                        <td class="rid">{{ p.rid }}</td>
                        <td class="pn">{{ p.displayNumber }}</td>
                        <td class="pd">{{ p.name }}</td>
                        <td class="q">{{ p.qty }}</td>
                        <td class="bx sm"><span class="cb" :class="{ pfd: p.rcvDone }"><span v-if="p.rcvPartial" class="pf tally">{{ p.rcvPartial }}</span></span></td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <!-- daily log + shortages -->
            <div v-if="page.showRail" class="gL">
              <div class="sec">
                <div class="sec-t">DAILY LOG <small>END OF SHIFT — EVERY DAY, EVEN IF NO PROGRESS</small></div>
                <table class="log">
                  <tbody>
                    <tr><th class="dt">DATE</th><th class="ini">INIT</th><th class="hr">HRS</th><th>WORKED ON / ISSUES</th></tr>
                    <tr v-for="i in 7" :key="i"><td class="dt"></td><td class="ini"></td><td class="hr"></td><td></td></tr>
                  </tbody>
                </table>
              </div>
              <div class="sec notes">
                <div class="sec-t">SHORTAGES · REWORK · DEVIATIONS</div>
                <div class="ln"></div><div class="ln"></div><div class="ln"></div>
              </div>
            </div>

            <!-- notes column on tabloid continuation pages -->
            <div v-if="!page.showRail && sheet.format === 'tabloid'" class="gN">
              <div class="sec notes">
                <div class="sec-t">NOTES</div>
                <div v-for="i in 12" :key="i" class="ln"></div>
              </div>
            </div>
          </div>

          <!-- footer -->
          <div class="ft">
            <div class="legend">
              <span><span class="cb"></span>REQUIRED OP</span>
              <span><span class="cb naex"></span>NOT IN ROUTING</span>
              <span><span class="cb pfd"></span>RECORDED IN SYSTEM AT PRINT</span>
              <span><b>NEW WORK:</b>&nbsp;HEAVY X IN PEN · PARTIAL: WRITE QTY IN BOX</span>
              <span><b>UPDATE END OF SHIFT · KEEP FLAT · PHOTO FROM DIRECTLY ABOVE</b></span>
            </div>
            <div class="sheetid">TRK · {{ sheet.project.project_code }} · {{ fmtIso(sheet.generatedAt) }} · PAGE {{ pi + 1 }}/{{ sheet.pages.length }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ---------- screen chrome (MRP dark theme) ---------- */
.tracker-page {
  min-height: 100vh;
  background: #020617;
  color: #e5e7eb;
}
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background: #0f172a;
  border-bottom: 1px solid #1e293b;
  flex-wrap: wrap;
  gap: 12px;
}
.tb-left, .tb-right { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.toolbar h1 { margin: 0; font-size: 20px; }
.btn { padding: 8px 16px; border-radius: 6px; border: none; cursor: pointer; font-size: 13px; font-weight: 500; }
.btn-secondary { background: #374151; color: white; }
.btn-secondary:hover { background: #4b5563; }
.btn-primary { background: #2563eb; color: white; }
.btn-primary:hover { background: #1d4ed8; }
.seggroup { display: flex; border-radius: 6px; overflow: hidden; border: 1px solid #334155; }
.seg-btn { border-radius: 0; background: #1e293b; color: #9ca3af; }
.seg-btn.active { background: #2563eb; color: white; }
.chk { display: flex; align-items: center; gap: 6px; font-size: 13px; color: #9ca3af; cursor: pointer; }
.msg { text-align: center; padding: 60px; color: #6b7280; }
.msg.error { color: #f87171; }
.fitwrap { padding: 16px; }
.page-slot { position: relative; }

/* ---------- the sheet (paper) ---------- */
.paper {
  width: 1632px;
  height: 1056px;
  background: #fff;
  color: #16181a;
  font-family: Arial, Helvetica, sans-serif;
  position: relative;
  padding: 24px 26px 20px;
  box-sizing: border-box;
  box-shadow: 0 3px 26px rgba(0, 0, 0, 0.55);
  font-variant-numeric: tabular-nums;
  transform-origin: 0 0;
}
.paper.letter { width: 1056px; height: 816px; padding: 20px 24px 16px; }
.anch { position: absolute; width: 15px; height: 15px; background: #16181a; }
.anch.tr { top: 16px; right: 16px; }
.anch.bl { bottom: 16px; left: 16px; }
.anch.br { bottom: 16px; right: 16px; }
.letter .anch { width: 12px; height: 12px; }

/* header */
.hd { display: flex; gap: 18px; align-items: stretch; height: 98px; }
.hd.slim { height: 34px; align-items: center; justify-content: space-between; }
.letter .hd { height: 84px; gap: 12px; }
.letter .hd.slim { height: 30px; }
.qr { flex: 0 0 auto; text-align: center; }
.qr img { display: block; image-rendering: pixelated; }
.qr .lbl { font-size: 6.5px; letter-spacing: 0.6px; font-weight: bold; margin-top: 2px; }
.id { flex: 1 1 auto; min-width: 0; padding-top: 2px; }
.eyebrow { font-size: 10px; font-weight: bold; letter-spacing: 2.4px; }
.proj { font-size: 30px; font-weight: bold; letter-spacing: 0.4px; line-height: 1.05; margin-top: 2px; }
.proj.sm { font-size: 16px; margin: 0; }
.letter .proj { font-size: 19px; }
.letter .proj.sm { font-size: 14px; }
.projsub { font-size: 11px; margin-top: 5px; letter-spacing: 0.2px; }
.letter .projsub { font-size: 9px; margin-top: 3px; }
.rev { flex: 0 0 218px; border: 1.5px solid #16181a; padding: 7px 10px; font-size: 9.5px; line-height: 1.5; }
.rev.slim { flex: 0 0 auto; border: none; font-weight: bold; }
.letter .rev { flex: 0 0 178px; font-size: 8px; line-height: 1.45; padding: 5px 8px; }
.rev .big { font-size: 11.5px; font-weight: bold; letter-spacing: 0.3px; }
.letter .rev .big { font-size: 9.5px; }
.rev .warn { font-weight: bold; margin-top: 3px; }
.glance { flex: 0 0 430px; display: flex; flex-direction: column; justify-content: space-between; }
.letter .glance { flex: 0 0 300px; }
.fracs { display: flex; gap: 10px; }
.frac { flex: 1; border: 1.5px solid #16181a; padding: 5px 8px 6px; }
.frac .t { font-size: 8px; font-weight: bold; letter-spacing: 1.2px; }
.letter .frac .t { font-size: 6.5px; letter-spacing: 0.8px; }
.frac .v { display: flex; align-items: baseline; gap: 5px; margin-top: 1px; }
.frac .big-n { font-size: 21px; font-weight: bold; border-bottom: 2px solid #16181a; min-width: 44px; display: inline-block; text-align: center; }
.letter .frac .big-n { font-size: 15px; min-width: 32px; }
.frac .of { font-size: 16px; font-weight: bold; }
.letter .frac .of { font-size: 12px; }
.pbar { margin-top: 8px; }
.letter .pbar { margin-top: 4px; }
.pbar .t { font-size: 8px; font-weight: bold; letter-spacing: 1.2px; margin-bottom: 2px; display: flex; justify-content: space-between; }
.letter .pbar .t { font-size: 6.5px; letter-spacing: 0.6px; }
.segs { display: flex; }
.seg { flex: 1; height: 19px; border: 1.5px solid #16181a; border-left-width: 0; position: relative; }
.letter .seg { height: 14px; }
.seg:first-child { border-left-width: 1.5px; }
.seg i { position: absolute; font-style: normal; font-size: 6.5px; bottom: -11px; left: 0; right: 0; text-align: center; letter-spacing: 0.3px; }
.letter .seg i { font-size: 5.5px; bottom: -9px; }
.segfill { position: absolute; inset: 1.5px; background: #16181a; display: block; }

/* body grid — named areas, rearranged per page layout */
.bd { display: grid; gap: 0 14px; margin-top: 14px; }
.gA { grid-area: A; }
.gB { grid-area: B; }
.gM { grid-area: M; }
.gR { grid-area: R; }
.gL { grid-area: L; }
.gN { grid-area: N; }
/* tabloid page 1: parts A | parts B + matrix | rail + log */
.bd.t-main {
  grid-template-columns: 562px 562px 1fr;
  grid-template-areas:
    'A B R'
    'A M R'
    'A M L';
  grid-template-rows: auto auto 1fr;
}
/* tabloid continuation: parts A | parts B | notes */
.bd.t-cont {
  grid-template-columns: 562px 562px 1fr;
  grid-template-areas: 'A B N';
}
/* letter parts pages: two part columns */
.bd.l-parts {
  grid-template-columns: 1fr 1fr;
  grid-template-areas: 'A B';
  margin-top: 10px;
}
/* letter status page: matrix + log | milestones + purchased */
.bd.l-status {
  grid-template-columns: 1.3fr 1fr;
  grid-template-areas:
    'M R'
    'L R';
  grid-template-rows: auto 1fr;
  margin-top: 10px;
}

.sec { margin-bottom: 10px; }
.sec-t {
  font-size: 10.5px; font-weight: bold; letter-spacing: 1.6px;
  border-bottom: 2px solid #16181a; padding-bottom: 2px;
  display: flex; justify-content: space-between; align-items: baseline;
}
.sec-t small { font-weight: normal; font-size: 8px; letter-spacing: 0.4px; }
.letter .sec-t { font-size: 9px; letter-spacing: 1.1px; }
.letter .sec-t small { font-size: 6.5px; }

.paper table { border-collapse: collapse; width: 100%; }
.paper td, .paper th { border: 0.75px solid #c9cdd1; padding: 0 4px; height: 18px; box-sizing: border-box; overflow: hidden; white-space: nowrap; }
.paper th { background: #f1f2f3; font-size: 8px; letter-spacing: 0.5px; height: 20px; border-bottom: 1.25px solid #9aa0a5; text-align: left; }
.paper th.bx, .paper th.q { text-align: center; }
.paper td { font-size: 9.5px; }
.letter .paper td { font-size: 9px; }
.rid { width: 27px; text-align: center !important; font-weight: bold; font-size: 9px; background: #f1f2f3; border-right: 1.25px solid #9aa0a5 !important; }
.pn { width: 64px; font-weight: bold; }
.letter .pn { width: 60px; }
.pd { font-size: 9px; max-width: 0; text-overflow: ellipsis; }
.q { width: 24px; text-align: center; font-weight: bold; }
.bx { width: 30px; text-align: center; padding: 0 !important; }
.letter .bx { width: 26px; }
.cb { display: block; width: 13px; height: 13px; border: 1.5px solid #16181a; margin: 0 auto; position: relative; background: #fff; }
.bx.na .cb { border-color: #d9dcdf; background: repeating-linear-gradient(45deg, #e9ebec 0 2px, #fff 2px 4.5px); }
.bx.gate { background: #f1f2f3; border-left: 2px solid #16181a !important; }
th.gate { border-left: 2px solid #16181a !important; }
.grp td { background: #e4e6e8; font-size: 9.5px; font-weight: bold; height: 20px; border-top: 1.5px solid #9aa0a5; border-bottom: 1.25px solid #9aa0a5; }
.grp .gref { width: 27px; text-align: center; background: #16181a !important; color: #fff; font-size: 9px; }
.grp .gfrac { text-align: right; font-weight: normal; font-size: 8.5px; }

.asm td { height: 20px; }
.asm .rdy { width: 52px; text-align: center; font-size: 8.5px; }

.ms td { height: 22px; font-size: 9.5px; }
.ms .op { width: 24px; text-align: center; font-weight: bold; background: #f1f2f3; }
.ms .plan { width: 52px; text-align: center; font-size: 9px; }
.ms .act { width: 56px; }
.ms .ini { width: 34px; }
.ms tr.gate-row td { background: #e4e6e8; font-weight: bold; border-top: 1.5px solid #16181a; border-bottom: 1.5px solid #16181a; }

.pur-ll td { height: 17px; font-size: 9px; }
.pur-ll .pn { width: 84px; }
.pur-ll .src { width: 68px; font-size: 8px; }
.pur2 { display: grid; grid-template-columns: 1fr 1fr; gap: 0 8px; margin-top: -0.75px; }
.pur2 td { height: 17px; font-size: 8.5px; }
.pur2 .pd { font-size: 8px; }
.bx.sm { width: 24px; }
.bx.sm .cb { width: 12px; height: 12px; }

.log td { height: 19px; }
.log .dt { width: 44px; }
.log .ini { width: 32px; }
.log .hr { width: 32px; }
.notes .ln { border-bottom: 1px solid #9aa0a5; height: 22px; }

/* footer */
.ft {
  position: absolute; left: 52px; right: 52px; bottom: 18px;
  display: flex; justify-content: space-between; align-items: center; gap: 18px;
}
.letter .ft { left: 44px; right: 44px; bottom: 13px; }
.legend { display: flex; gap: 14px; align-items: center; font-size: 8.5px; letter-spacing: 0.2px; }
.letter .legend { font-size: 7px; gap: 9px; }
.legend .cb { display: inline-block; vertical-align: -3px; margin-right: 3px; }
.legend .naex { border-color: #d9dcdf; background: repeating-linear-gradient(45deg, #e9ebec 0 2px, #fff 2px 4.5px); }
.sheetid { font-size: 8px; letter-spacing: 1px; font-weight: bold; white-space: nowrap; }

/* pre-filled (recorded in system) marks */
.cb.pfd { background: #16181a; }
.pf.tally { position: absolute; left: -2px; top: -1px; width: 17px; text-align: center; font-size: 9px; line-height: 14px; font-weight: bold; }
.cb.pfd .pf.tally { color: #fff; }
.hide-recorded .cb.pfd { background: #fff; }
.hide-recorded .pf { visibility: hidden; }
.hide-recorded .frac .big-n { color: transparent; }
</style>

<style>
/* print rules must be unscoped; @page size is injected dynamically per format */
@media print {
  body { background: #fff !important; }
  .tracker-page .toolbar { display: none !important; }
  .tracker-page { background: #fff !important; }
  .tracker-page .fitwrap { padding: 0 !important; }
  .tracker-page .page-slot { height: auto !important; }
  .tracker-page .paper {
    transform: none !important;
    box-shadow: none !important;
    page-break-after: always;
  }
}
</style>
