import { useEffect, useMemo, useRef, useState } from 'react'
import { AgGridReact } from 'ag-grid-react'
import { FIELDING, HITTING, PITCHING } from '../data/columns.js'
import { gridTheme, heightText, statColumns } from '../lib/grid.jsx'
import MarkerButton from './MarkerButton.jsx'
import StatusBadge, { statusDetail } from './StatusBadge.jsx'

const VIEWS = [
  { key: 'batting', label: 'Batting', stats: HITTING },
  { key: 'pitching', label: 'Pitching', stats: PITCHING },
  { key: 'fielding', label: 'Fielding', stats: FIELDING },
]

const RULES = {
  independent: 'Independent league player',
  grad_2026_no_team: '2026 college graduate',
  released_affiliated: 'Released by an affiliated club',
}

export default function PlayerModal({ api, playerId, listRow, onClose, setMarker, startView }) {
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState('')
  const [view, setView] = useState(startView)
  const [quick, setQuick] = useState('')
  const closeRef = useRef(null)

  useEffect(() => {
    let alive = true
    setDetail(null); setError('')
    api.loadPlayer(playerId).then((d) => alive && setDetail(d)).catch((e) => alive && setError(e.message))
    return () => { alive = false }
  }, [api, playerId])

  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  // The list row carries the latest marker, so the pop up and the grid never disagree.
  const p = { ...(detail?.player ?? {}), ...(listRow ?? {}) }
  const rows = detail?.[view] ?? []
  const v = VIEWS.find((x) => x.key === view)
  const cols = useMemo(() => {
    const base = statColumns(v.stats, { showSeason: true, showTeam: true })
    return base.map((c) => ({ ...c, pinned: c.field === 'season' ? 'left' : undefined }))
  }, [v])

  const facts = [
    ['Position', p.primary_position],
    ['Bats / throws', p.bats || p.throws ? `${p.bats ?? '?'} / ${p.throws ?? '?'}` : null],
    ['Height, weight', p.height_in ? `${heightText(p.height_in)}, ${p.weight_lb ?? '?'} lb` : null],
    ['Hometown', p.hometown],
    ['College', p.college],
    ['Graduated', p.grad_year],
    ['Role', p.pitcher_role === 'SP' ? 'Starter' : p.pitcher_role === 'RP' ? 'Reliever' : null],
    ['Qualifies as', (p.rules ?? []).map((r) => RULES[r] ?? r).join(', ') || null],
  ].filter(([, val]) => val)

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <div className="modal-head">
          <div className="modal-title">
            <h2 id="modal-title">{p.full_name ?? 'Loading player'}</h2>
            {p.id && <StatusBadge player={p} />}
            {p.is_two_way && <span className="tag">Two way</span>}
          </div>
          <div className="modal-head-actions">
            {p.id && <MarkerButton player={p} onChange={setMarker} showLabel />}
            <button ref={closeRef} type="button" className="btn btn-quiet" onClick={onClose} aria-label="Close player profile">Close</button>
          </div>
        </div>

        {p.id && <p className="status-line">{statusDetail(p)}</p>}
        {facts.length > 0 && (
          <dl className="facts">
            {facts.map(([k, val]) => <div key={k}><dt>{k}</dt><dd>{val}</dd></div>)}
          </dl>
        )}

        <div className="modal-bar">
          <div className="segmented" role="tablist" aria-label="Stat view">
            {VIEWS.map((x) => {
              const n = detail?.[x.key]?.length ?? 0
              return (
                <button key={x.key} type="button" role="tab" aria-selected={view === x.key}
                  className={view === x.key ? 'is-on' : ''} onClick={() => setView(x.key)} disabled={detail && n === 0}
                  title={detail && n === 0 ? `No ${x.label.toLowerCase()} stats on file` : undefined}>
                  {x.label}
                </button>
              )
            })}
          </div>
          <input type="search" className="quick" placeholder="Filter by season or team" value={quick}
            onChange={(e) => setQuick(e.target.value)} aria-label="Filter seasons" />
        </div>

        <div className="modal-grid">
          {error && <p className="form-error" role="alert">This profile did not load: {error}</p>}
          {!error && !detail && <p className="empty">Loading seasons</p>}
          {detail && rows.length === 0 && <p className="empty">No {v.label.toLowerCase()} stats on file for this player.</p>}
          {detail && rows.length > 0 && (
            <AgGridReact theme={gridTheme} rowData={rows} columnDefs={cols} quickFilterText={quick}
              defaultColDef={{ sortable: true, resizable: true, suppressMovable: true }}
              domLayout="autoHeight" tooltipShowDelay={300} />
          )}
        </div>
        {detail && rows.some((r) => r.small_sample) && (
          <p className="hint">Grey numbers are small samples: under 100 PA, or under 30 IP.</p>
        )}
      </div>
    </div>
  )
}
