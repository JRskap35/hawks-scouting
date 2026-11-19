import { useEffect, useMemo, useRef, useState } from 'react'
import { AgGridReact } from 'ag-grid-react'
import { FIELDING, HITTING, PITCHING } from '../data/columns.js'
import { gridTheme, heightText, statColumns } from '../lib/grid.jsx'
import MarkerButton from './MarkerButton.jsx'
import StatusBadge, { statusDetail } from './StatusBadge.jsx'
import GameLogModal from './GameLogModal.jsx'

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

export default function PlayerModal({ api, playerId, listRow, onClose, setMarker, startView, statusEdit }) {
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState('')
  const [view, setView] = useState(startView)
  const [quick, setQuick] = useState('')
  const [gameLog, setGameLog] = useState(null)          // { season, kind } while the game log is open
  const closeRef = useRef(null)
  const gameLogOpen = useRef(false)
  gameLogOpen.current = !!gameLog

  useEffect(() => {
    let alive = true
    setDetail(null); setError('')
    api.loadPlayer(playerId).then((d) => alive && setDetail(d)).catch((e) => alive && setError(e.message))
    return () => { alive = false }
  }, [api, playerId])

  useEffect(() => {
    closeRef.current?.focus()
    // Escape closes the game log first, then this pop up.
    const onKey = (e) => e.key === 'Escape' && !gameLogOpen.current && onClose()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  // The list row carries the latest marker, so the pop up and the grid never disagree.
  const p = { ...(detail?.player ?? {}), ...(listRow ?? {}) }
  const rows = detail?.[view] ?? []
  const v = VIEWS.find((x) => x.key === view)
  const canOpen = (r) => view !== 'fielding' && (r?.games_logged ?? 0) > 0
  const cols = useMemo(() => {
    const base = statColumns(v.stats, { showSeason: true, showTeam: true })
    return base.map((c) => (c.field === 'season'
      ? { ...c, pinned: 'left', width: 78, cellRenderer: SeasonCell }
      : c))
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
            {p.id && <StatusBadge player={p} edit={statusEdit} />}
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
              context={{ open: (r) => setGameLog({ season: r.season, kind: view }), canOpen }}
              onRowClicked={(e) => canOpen(e.data) && setGameLog({ season: e.data.season, kind: view })}
              getRowClass={(p) => (canOpen(p.data) ? 'row-openable' : '')}
              domLayout="autoHeight" tooltipShowDelay={300} />
          )}
        </div>
        {detail && rows.length > 0 && (
          <p className="hint">
            {view !== 'fielding' && rows.some(canOpen) && 'Click a season to see every game. '}
            {view !== 'fielding' && rows.some((r) => !canOpen(r)) && 'Seasons without a link have no game log on file yet (college game logs are not loaded). '}
            {rows.some((r) => r.small_sample) && 'Grey numbers are small samples: under 100 PA, or under 30 IP.'}
          </p>
        )}
      </div>
      {gameLog && (
        <GameLogModal api={api} player={p} season={gameLog.season} kind={gameLog.kind} onClose={() => setGameLog(null)} />
      )}
    </div>
  )
}

// The season in each row. A link when that season has a game log.
function SeasonCell({ data, context }) {
  if (!context.canOpen(data)) return <span>{data.season}</span>
  return (
    <button type="button" className="seasonlink" title={`Show all ${data.games_logged} games`}
      onClick={(e) => { e.stopPropagation(); context.open(data) }}>
      {data.season}
    </button>
  )
}
