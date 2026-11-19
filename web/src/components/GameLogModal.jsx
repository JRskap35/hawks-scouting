import { useEffect, useMemo, useRef, useState } from 'react'
import { AgGridReact } from 'ag-grid-react'
import { FORMATS } from '../data/columns.js'
import { gridTheme, nullsLast } from '../lib/grid.jsx'
import { statGap } from '../data/gaps.js'

const shortDate = (d) => new Date(`${d}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
const opp = (r) => (r.opponent ? `${r.home_away === 'A' ? 'at ' : r.home_away === 'H' ? 'vs ' : ''}${r.opponent}` : '')
const ipFromOuts = (outs) => Math.floor(outs / 3) + (outs % 3) / 10

const n = (key, label, opts = {}) => ({
  headerName: label, field: key, width: opts.width ?? 58, comparator: nullsLast,
  cellClass: (p) => `num ${p.value == null ? 'is-na' : ''}`, headerClass: 'num-h', headerTooltip: opts.title,
  valueFormatter: (p) => (p.value == null ? (p.node?.rowPinned ? '' : 'n/a') : opts.format ? FORMATS[opts.format](p.value) : p.value),
  tooltipValueGetter: (p) => (p.value == null && !p.node?.rowPinned ? statGap(key) : undefined),
})

const LEAD = [
  { headerName: 'Date', field: 'game_date', width: 92, pinned: 'left', sort: 'asc',
    valueFormatter: (p) => (p.node.rowPinned ? 'Totals' : `${shortDate(p.value)}${p.data.game_no > 1 ? ` (${p.data.game_no})` : ''}`),
    comparator: (a, b, na, nb) => (a === b ? (na.data.game_no ?? 1) - (nb.data.game_no ?? 1) : a < b ? -1 : 1),
    headerTooltip: 'Game 2 of a doubleheader shows (2)' },
  { headerName: 'Opponent', colId: 'opp', width: 210, valueGetter: (p) => opp(p.data), tooltipValueGetter: (p) => opp(p.data) },
  { headerName: 'Result', field: 'result', width: 82 },
  { headerName: 'Team', field: 'team', width: 160, comparator: nullsLast, tooltipField: 'team' },
]

const BATTING = [
  n('pa', 'PA'), n('ab', 'AB'), n('r', 'R'), n('h', 'H'), n('b2', '2B'), n('b3', '3B'), n('hr', 'HR'),
  n('rbi', 'RBI'), n('bb', 'BB'), n('so', 'SO'), n('hbp', 'HBP'), n('sb', 'SB'), n('cs', 'CS'),
]

const PITCHING = [
  // cellDataType 'text' stops the grid from drawing a checkbox for this true/false field
  { headerName: 'Role', colId: 'role', width: 76, cellDataType: 'text',
    valueGetter: (p) => (p.node.rowPinned ? p.data.started : p.data.started == null ? '' : p.data.started ? 'Start' : 'Relief') },
  { headerName: 'Dec', field: 'decision', width: 78, cellDataType: 'text',
    headerTooltip: 'Decision: W, L, S (save), H (hold). The totals row shows W-L-S.' },
  n('ip', 'IP', { format: 'ip', title: '45.2 means 45 and two thirds' }), n('h', 'H'), n('r', 'R'), n('er', 'ER'),
  n('bb', 'BB'), n('so', 'SO'), n('hr', 'HR'), n('hbp', 'HBP'), n('wp', 'WP'),
  n('bf', 'BF', { title: 'Batters faced' }), n('pitches', 'Pitches', { width: 74 }), n('strikes', 'Strikes', { width: 72 }),
]

function totals(rows, kind) {
  const add = (k) => (rows.some((r) => r[k] != null) ? rows.reduce((t, r) => t + (r[k] ?? 0), 0) : null)
  const keys = kind === 'pitching'
    ? ['outs', 'h', 'r', 'er', 'bb', 'so', 'hr', 'hbp', 'wp', 'bf', 'pitches', 'strikes']
    : ['pa', 'ab', 'r', 'h', 'b2', 'b3', 'hr', 'rbi', 'bb', 'so', 'hbp', 'sb', 'cs']
  const t = Object.fromEntries(keys.map((k) => [k, add(k)]))
  t.game_date = ''
  if (kind === 'pitching') {
    t.ip = t.outs != null ? ipFromOuts(t.outs) : null
    const gs = rows.filter((r) => r.started).length
    t.started = `${gs} GS`
    t.decision = ['W', 'L', 'S'].map((d) => `${rows.filter((r) => r.decision === d).length}`).join('-')
  }
  return t
}

function summary(rows, kind) {
  if (!rows.length) return ''
  const t = totals(rows, kind)
  if (kind === 'pitching') {
    const ip = (t.outs ?? 0) / 3
    const era = ip ? FORMATS.dec2((9 * (t.er ?? 0)) / ip) : ''
    const whip = ip ? FORMATS.dec2(((t.bb ?? 0) + (t.h ?? 0)) / ip) : ''
    return `${rows.length} games, ${rows.filter((r) => r.started).length} starts. ${FORMATS.ip(t.ip)} IP, ${era} ERA, ${whip} WHIP, ${t.so ?? 0} SO.`
  }
  const avg = t.ab ? FORMATS.rate3(t.h / t.ab) : ''
  const obpDen = (t.ab ?? 0) + (t.bb ?? 0) + (t.hbp ?? 0)
  const obp = obpDen ? FORMATS.rate3(((t.h ?? 0) + (t.bb ?? 0) + (t.hbp ?? 0)) / obpDen) : ''
  const slg = t.ab ? FORMATS.rate3(((t.h ?? 0) + (t.b2 ?? 0) + 2 * (t.b3 ?? 0) + 3 * (t.hr ?? 0)) / t.ab) : ''
  return `${rows.length} games. ${avg} / ${obp} / ${slg}, ${t.hr ?? 0} HR, ${t.rbi ?? 0} RBI.`
}

// Second level pop up: every game of one season, opened from a season row in the player pop up.
export default function GameLogModal({ api, player, season, kind, onClose }) {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState('')
  const [quick, setQuick] = useState('')
  const [shownTotals, setShownTotals] = useState(null)
  const closeRef = useRef(null)

  useEffect(() => {
    let alive = true
    api.loadGameLog(player.id, season, kind).then((r) => alive && setRows(r)).catch((e) => alive && setError(e.message))
    return () => { alive = false }
  }, [api, player.id, season, kind])

  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e) => { if (e.key === 'Escape') { e.stopPropagation(); onClose() } }
    document.addEventListener('keydown', onKey, true)
    return () => document.removeEventListener('keydown', onKey, true)
  }, [onClose])

  const cols = useMemo(() => [...LEAD, ...(kind === 'pitching' ? PITCHING : BATTING)], [kind])
  // Totals follow the opponent filter, so "every game against Ogden" adds up correctly.
  const recomputeTotals = (e) => {
    const shown = []
    e.api.forEachNodeAfterFilter((node) => shown.push(node.data))
    setShownTotals(totals(shown, kind))
  }

  return (
    <div className="modal-backdrop modal-stack" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal modal-gamelog" role="dialog" aria-modal="true" aria-labelledby="gamelog-title">
        <div className="modal-head">
          <div>
            <h2 id="gamelog-title">{player.full_name}</h2>
            <p className="status-line">{season} {kind} game log{rows ? `. ${summary(rows, kind)}` : ''}</p>
          </div>
          <div className="modal-head-actions">
            <input type="search" className="quick" placeholder="Filter by opponent or result" value={quick}
              onChange={(e) => setQuick(e.target.value)} aria-label="Filter games" />
            <button ref={closeRef} type="button" className="btn btn-quiet" onClick={onClose}>Back to profile</button>
          </div>
        </div>
        <div className="modal-grid gamelog-grid">
          {error && <p className="form-error" role="alert">This game log did not load: {error}</p>}
          {!error && !rows && <p className="empty">Loading games</p>}
          {rows && rows.length === 0 && <p className="empty">No game log on file for {season}.</p>}
          {rows && rows.length > 0 && (
            <AgGridReact theme={gridTheme} rowData={rows} columnDefs={cols} quickFilterText={quick}
              defaultColDef={{ sortable: true, resizable: true, suppressMovable: true }}
              pinnedBottomRowData={shownTotals ? [shownTotals] : [totals(rows, kind)]}
              getRowClass={(p) => (p.node.rowPinned ? 'row-totals' : '')}
              onFilterChanged={recomputeTotals} onFirstDataRendered={recomputeTotals}
              tooltipShowDelay={300} />
          )}
        </div>
      </div>
    </div>
  )
}
