import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AgGridReact } from 'ag-grid-react'
import { api, IS_DEMO } from './data/api.js'
import { FORMATS, MARKERS, PAGE_STATS, POSITION_GROUPS, markerLabel } from './data/columns.js'
import { exportColumns, gridTheme, leadColumns, nullsLast, statColumns } from './lib/grid.jsx'
import { exportCsv, exportPdf } from './lib/export.js'
import Popover from './lib/Popover.jsx'
import Header from './components/Header.jsx'
import FilterMenu, { filterText } from './components/FilterMenu.jsx'
import PlayerModal from './components/PlayerModal.jsx'
import Login from './components/Login.jsx'
import { fmtDate } from './components/StatusBadge.jsx'

const PAGES = ['hitters', 'pitchers', 'twoWay', 'scouted']
// Shown inside an embedded preview, where the browser blocks downloads. The real site is never embedded.
const EMBEDDED = (() => { try { return window.self !== window.top } catch { return true } })()
const EMBED_NOTE = 'Downloads are blocked in this preview. Export works on the published site.'
const TITLES = { hitters: 'Position Players', pitchers: 'Pitchers', twoWay: 'Two Way Players', scouted: 'Scouted Players' }
const pageFromHash = () => {
  const h = window.location.hash.replace('#', '')
  return PAGES.includes(h) ? h : 'hitters'
}

// One line summary for the Scouted Players list, where hitters and pitchers sit together.
function lineFor(p, lists) {
  const h = lists.hitters.find((r) => r.id === p.id)
  const pi = lists.pitchers.find((r) => r.id === p.id)
  const parts = []
  if (h) parts.push(`${FORMATS.rate3(h.avg)} / ${FORMATS.rate3(h.obp)} / ${FORMATS.rate3(h.slg)}, ${h.hr ?? 0} HR in ${h.pa ?? 0} PA`)
  if (pi) parts.push(`${FORMATS.dec2(pi.era)} ERA, ${FORMATS.dec2(pi.fip)} FIP in ${FORMATS.ip(pi.ip)} IP`)
  return parts.join('; ')
}

function ExportMenu({ onCsv, onPdf, disabled }) {
  const ref = useRef(null)
  const [open, setOpen] = useState(false)
  return (
    <>
      <button ref={ref} type="button" className="btn" onClick={() => setOpen((o) => !o)} disabled={disabled} aria-expanded={open}>
        Export
      </button>
      <Popover anchor={ref.current} open={open} onClose={() => setOpen(false)} placement="bottom-end">
        <div className="menu" role="menu">
          <button type="button" role="menuitem" className="menu-item" onClick={() => { setOpen(false); onCsv() }}>Spreadsheet (CSV)</button>
          <button type="button" role="menuitem" className="menu-item" onClick={() => { setOpen(false); onPdf() }}>PDF</button>
          <div className="menu-note">Exports the players shown, in the order shown.</div>
        </div>
      </Popover>
    </>
  )
}

export default function App() {
  const [session, setSession] = useState(undefined)            // undefined while checking
  const [lists, setLists] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [page, setPageState] = useState(pageFromHash)
  const [group, setGroup] = useState({ hitters: 'all', pitchers: 'all' })
  const [status, setStatus] = useState('all')
  const [markerFilter, setMarkerFilter] = useState('all')
  const [filters, setFilters] = useState({ hitters: [], pitchers: [], twoWay: [] })
  const [openId, setOpenId] = useState(null)
  const [toast, setToast] = useState(null)
  const gridApi = useRef(null)
  const [narrow, setNarrow] = useState(() => window.matchMedia('(max-width: 700px)').matches)
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 700px)')
    const on = (e) => setNarrow(e.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])

  // ---- auth and data -------------------------------------------------------
  useEffect(() => {
    api.auth.session().then(setSession)
    return api.auth.onChange(setSession)
  }, [])

  useEffect(() => {
    if (!session) return
    setLoadError('')
    api.loadLists().then(setLists).catch((e) => setLoadError(e.message))
  }, [session])

  useEffect(() => {
    const onHash = () => setPageState(pageFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  const setPage = (p) => { window.location.hash = p; setPageState(p) }

  const say = (text, kind = 'ok') => {
    setToast({ text, kind })
    clearTimeout(say.t)
    say.t = setTimeout(() => setToast(null), 3500)
  }

  // ---- markers (optimistic, rolled back if the save fails) ----------------
  const patchPlayer = (id, fields) => setLists((l) => l && Object.fromEntries(
    Object.entries(l).map(([k, rows]) => [k, rows.map((r) => (r.id === id ? { ...r, ...fields } : r))])))

  const setMarker = useCallback(async (id, next) => {
    const before = [...(lists?.hitters ?? []), ...(lists?.pitchers ?? []), ...(lists?.twoWay ?? [])].find((r) => r.id === id)
    const prev = { marker: before?.marker ?? null, marker_set_at: before?.marker_set_at ?? null, marker_set_by: before?.marker_set_by ?? null }
    patchPlayer(id, { marker: next })
    try {
      const saved = await api.setMarker(id, next)
      patchPlayer(id, saved)
      say(next ? `Marked ${before?.full_name ?? 'player'} ${markerLabel(next)}` : `Cleared marker on ${before?.full_name ?? 'player'}`)
    } catch (e) {
      patchPlayer(id, prev)
      say(`Marker not saved: ${e.message}`, 'error')
    }
  }, [lists])

  // ---- rows for the current page --------------------------------------------
  const allPlayers = useMemo(() => {
    if (!lists) return []
    const m = new Map()
    for (const r of [...lists.hitters, ...lists.pitchers, ...lists.twoWay]) if (!m.has(r.id)) m.set(r.id, r)
    return [...m.values()]
  }, [lists])

  const scoutedRows = useMemo(() => allPlayers.filter((p) => p.marker).map((p) => ({ ...p, line: lineFor(p, lists) })), [allPlayers, lists])
  const stats = PAGE_STATS[page] ?? []
  const pageFilters = filters[page] ?? []

  const rows = useMemo(() => {
    if (!lists) return []
    let r = page === 'scouted' ? scoutedRows : lists[page]
    const g = group[page]
    if (page === 'hitters' && g !== 'all') r = r.filter((x) => x.position_group === g)
    if (page === 'pitchers' && g !== 'all') r = r.filter((x) => x.pitcher_role === g)
    if (status !== 'all') r = r.filter((x) => x.status_label === status)
    if (page === 'scouted' && markerFilter !== 'all') r = r.filter((x) => x.marker === markerFilter)
    for (const f of pageFilters) {
      r = r.filter((x) => {
        const v = x[f.key]
        if (v == null) return false
        return (f.min == null || Number(v) >= f.min) && (f.max == null || Number(v) <= f.max)
      })
    }
    return r
  }, [lists, page, group, status, markerFilter, pageFilters, scoutedRows])

  const columnDefs = useMemo(() => {
    const lead = leadColumns(narrow)
    if (page === 'hitters') return [...lead, { headerName: 'B', field: 'bats', width: 50 }, ...statColumns(stats)]
    if (page === 'pitchers') {
      return [...lead,
        { headerName: 'Role', field: 'pitcher_role', width: 66, comparator: nullsLast, headerTooltip: 'Starter when 50% or more of his last three seasons\' appearances were starts, weighted toward the most recent' },
        { headerName: 'T', field: 'throws', width: 46 }, ...statColumns(stats)]
    }
    if (page === 'twoWay') {
      return [...lead, { headerName: 'Team', field: 'teams', width: 160 },
        ...statColumns(stats, { showSeason: false }).map((c) => (['ip', 'era', 'whip', 'fip', 'p_so', 'k9'].includes(c.field) ? { ...c, headerClass: `${c.headerClass} pit-h` } : c))]
    }
    return [...lead,
      { headerName: 'Line', field: 'line', width: 330, sortable: false, tooltipField: 'line' },
      { headerName: 'Marked as', field: 'marker', width: 150, valueFormatter: (p) => markerLabel(p.value), exportValue: (r) => markerLabel(r.marker) },
      { headerName: 'By', field: 'marker_set_by', width: 120, comparator: nullsLast },
      { headerName: 'When', field: 'marker_set_at', width: 130, valueFormatter: (p) => fmtDate(p.value), exportValue: (r) => fmtDate(r.marker_set_at), comparator: nullsLast },
    ]
  }, [page, stats, narrow])

  // ---- export -------------------------------------------------------------
  const shownRows = () => {
    const out = []
    gridApi.current?.forEachNodeAfterFilterAndSort((n) => out.push(n.data))
    return out.length ? out : rows
  }
  const exportTitle = () => {
    const bits = [TITLES[page]]
    const g = POSITION_GROUPS[page]?.find((x) => x.key === group[page])
    if (g && g.key !== 'all') bits.push(g.label)
    if (page === 'scouted' && markerFilter !== 'all') bits.push(markerLabel(markerFilter))
    return bits.join(', ')
  }
  const exportSubtitle = () => [
    status !== 'all' ? status : null,
    ...pageFilters.map((f) => filterText(f, stats.find((s) => s.key === f.key))),
  ].filter(Boolean).join(', ') || 'No filters'

  // ---- render ---------------------------------------------------------------
  if (session === undefined) return <div className="boot">Checking sign in</div>
  if (!session) return <Login api={api} />

  const openRow = allPlayers.find((p) => p.id === openId)
  const counts = lists ? { hitters: lists.hitters.length, pitchers: lists.pitchers.length, twoWay: lists.twoWay.length } : {}

  return (
    <div className="app">
      <Header page={page} setPage={setPage} scoutedCount={scoutedRows.length} players={allPlayers}
        onPick={setOpenId} demo={IS_DEMO} email={session.user?.email} onSignOut={() => api.auth.signOut()} />

      <section className="toolbar" aria-label="Filters">
        {POSITION_GROUPS[page] && (
          <div className="segmented" role="group" aria-label={page === 'hitters' ? 'Position' : 'Role'}>
            {POSITION_GROUPS[page].map((g) => (
              <button key={g.key} type="button" className={group[page] === g.key ? 'is-on' : ''} aria-pressed={group[page] === g.key}
                onClick={() => setGroup((s) => ({ ...s, [page]: g.key }))}>{g.label}</button>
            ))}
          </div>
        )}
        <label className="select">
          <span className="sr-only">Signing status</span>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="all">Any status</option>
            <option value="Free Agent">Free agents</option>
            <option value="Signed">Signed</option>
            <option value="Unconfirmed">Unconfirmed</option>
          </select>
        </label>
        {page === 'scouted' && (
          <label className="select">
            <span className="sr-only">Marker</span>
            <select value={markerFilter} onChange={(e) => setMarkerFilter(e.target.value)}>
              <option value="all">Any marker</option>
              {MARKERS.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
            </select>
          </label>
        )}
        {stats.length > 0 && <FilterMenu key={page} stats={stats} onAdd={(f) => setFilters((s) => ({ ...s, [page]: [...s[page].filter((x) => x.key !== f.key), f] }))} />}
        <div className="chips">
          {pageFilters.map((f) => (
            <span key={f.key} className="chip">
              {filterText(f, stats.find((s) => s.key === f.key))}
              <button type="button" aria-label={`Remove filter ${filterText(f, stats.find((s) => s.key === f.key))}`}
                onClick={() => setFilters((s) => ({ ...s, [page]: s[page].filter((x) => x.key !== f.key) }))}>×</button>
            </span>
          ))}
          {pageFilters.length > 1 && (
            <button type="button" className="btn btn-quiet btn-small" onClick={() => setFilters((s) => ({ ...s, [page]: [] }))}>Clear all</button>
          )}
        </div>
        <div className="toolbar-end">
          <span className="result-count" aria-live="polite">
            {lists ? `${rows.length} of ${page === 'scouted' ? scoutedRows.length : counts[page]} players` : ''}
          </span>
          <ExportMenu disabled={!rows.length}
            onCsv={() => (EMBEDDED ? say(EMBED_NOTE) : exportCsv(shownRows(), exportColumns(columnDefs), exportTitle()))}
            onPdf={() => (EMBEDDED ? say(EMBED_NOTE) : exportPdf(shownRows(), exportColumns(columnDefs).filter((c) => c.label !== 'Marker' || page === 'scouted'), exportTitle(), exportSubtitle())
              .catch((e) => say(`PDF not created: ${e.message}`, 'error')))} />
        </div>
      </section>

      <main className="gridwrap">
        {loadError && (
          <div className="empty empty-error" role="alert">
            <p>Player lists did not load: {loadError}</p>
            <button type="button" className="btn" onClick={() => { setLoadError(''); api.loadLists().then(setLists).catch((e) => setLoadError(e.message)) }}>Try again</button>
          </div>
        )}
        {!loadError && !lists && <div className="empty">Loading players</div>}
        {lists && rows.length === 0 && (
          <div className="empty">
            {page === 'scouted' && scoutedRows.length === 0
              ? <p>No one is marked yet. Use the star beside any player to mark him Looking to Sign, Potential, or Already Reviewed.</p>
              : <p>No players match these filters. Remove a filter or widen a range.</p>}
          </div>
        )}
        {lists && rows.length > 0 && (
          <AgGridReact
            key={page}
            theme={gridTheme}
            rowData={rows}
            columnDefs={columnDefs}
            getRowId={(p) => String(p.data.id)}
            context={{ openPlayer: setOpenId, setMarker }}
            defaultColDef={{ sortable: true, resizable: true, suppressMovable: false }}
            onGridReady={(e) => { gridApi.current = e.api }}
            onRowDoubleClicked={(e) => setOpenId(e.data.id)}
            tooltipShowDelay={400}
            animateRows={false}
          />
        )}
      </main>

      <footer className="statusbar">
        <span>{IS_DEMO ? 'Demo data: every player here is made up.' : 'Stats are each player\'s most recent season.'}</span>
        <span>Signing status is for the 2027 season. Grey numbers are small samples.</span>
      </footer>

      {openId != null && (
        <PlayerModal api={api} playerId={openId} listRow={openRow} onClose={() => setOpenId(null)} setMarker={setMarker}
          startView={openRow?.position_group === 'P' && !openRow?.is_two_way ? 'pitching' : 'batting'} />
      )}
      {toast && <div className={`toast toast-${toast.kind}`} role="status">{toast.text}</div>}
    </div>
  )
}
