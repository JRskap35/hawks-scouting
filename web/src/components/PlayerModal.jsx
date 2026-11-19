import { useEffect, useMemo, useRef, useState } from 'react'
import { AgGridReact } from 'ag-grid-react'
import { FIELDING, HITTING, PITCHING } from '../data/columns.js'
import { gridTheme, heightText, statColumns } from '../lib/grid.jsx'
import MarkerButton from './MarkerButton.jsx'
import StatusBadge, { statusDetail } from './StatusBadge.jsx'
import GameLogModal from './GameLogModal.jsx'
import NotAvailableDialog, { NotAvailablePanel } from './NotAvailable.jsx'

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
  const [gap, setGap] = useState(null)                  // { gap, detail } while a Not available notice is open
  const closeRef = useRef(null)
  const childOpen = useRef(false)
  childOpen.current = !!gameLog || !!gap

  useEffect(() => {
    let alive = true
    setDetail(null); setError('')
    api.loadPlayer(playerId).then((d) => alive && setDetail(d)).catch((e) => alive && setError(e.message))
    return () => { alive = false }
  }, [api, playerId])

  useEffect(() => {
    closeRef.current?.focus()
    // Escape closes the game log or notice first, then this pop up.
    const onKey = (e) => e.key === 'Escape' && !childOpen.current && onClose()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  // The list row carries the latest marker, so the pop up and the grid never disagree.
  const p = { ...(detail?.player ?? {}), ...(listRow ?? {}) }
  const rows = detail?.[view] ?? []
  const v = VIEWS.find((x) => x.key === view)
  const hasLog = (r) => (r?.games_logged ?? 0) > 0
  // Every batting and pitching season opens: its game log, or a Not available notice saying why not.
  const openSeason = (r) => {
    if (view === 'fielding' || !r) return
    if (hasLog(r)) setGameLog({ season: r.season, kind: view })
    else setGap({ gap: r.is_pro === false ? 'gamelog_college' : 'gamelog_pro', detail: `${r.season}${r.leagues ? ` ${r.leagues}` : ''}` })
  }
  // Pro seasons with no fielding line: shown as known gaps under the fielding table.
  const missingFielding = useMemo(() => {
    if (!detail) return []
    const have = new Set((detail.fielding ?? []).map((f) => `${f.season}|${f.league_key ?? ''}`))
    const seen = new Set()
    return [...(detail.batting ?? []), ...(detail.pitching ?? [])]
      .filter((r) => r.is_pro !== false && !have.has(`${r.season}|${r.league_key ?? ''}`))
      .filter((r) => { const k = `${r.season}|${r.leagues}`; if (seen.has(k)) return false; seen.add(k); return true })
      .sort((a, b) => b.season - a.season)
  }, [detail])
  // Catcher only columns appear only when he caught, so n/a always means a real gap, never "does not apply".
  const caught = view === 'fielding' && rows.some((r) => r.position === 'C')
  const cols = useMemo(() => {
    const stats = v.key === 'fielding' && !caught ? v.stats.filter((x) => !['pb', 'sb_against', 'cs_by', 'cs_pct'].includes(x.key)) : v.stats
    const base = statColumns(stats, { showSeason: true, showTeam: true })
    return base.map((c) => (c.field === 'season'
      ? { ...c, pinned: 'left', width: 96, cellRenderer: SeasonCell }
      : c))
  }, [v, caught])

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
                  className={view === x.key ? 'is-on' : ''} onClick={() => setView(x.key)}
                  disabled={detail && n === 0 && x.key !== 'fielding'}
                  title={detail && n === 0 && x.key !== 'fielding' ? `He has no ${x.label.toLowerCase()} stats` : undefined}>
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
          {detail && rows.length === 0 && view !== 'fielding' && <p className="empty">He has no {v.label.toLowerCase()} stats.</p>}
          {detail && rows.length === 0 && view === 'fielding' && (
            <NotAvailablePanel gap="fielding_pro" detail={missingFielding.map((r) => `${r.season} ${r.leagues ?? ''}`.trim()).join(', ') || undefined} />
          )}
          {detail && rows.length > 0 && (
            <AgGridReact theme={gridTheme} rowData={rows} columnDefs={cols} quickFilterText={quick}
              defaultColDef={{ sortable: true, resizable: true, suppressMovable: true }}
              context={{ openSeason, hasLog, view }}
              onRowClicked={(e) => openSeason(e.data)}
              getRowClass={() => (view !== 'fielding' ? 'row-openable' : '')}
              domLayout="autoHeight" tooltipShowDelay={300} />
          )}
        </div>
        {detail && view === 'fielding' && rows.length > 0 && missingFielding.length > 0 && (
          <div className="na-chips">
            {missingFielding.map((r) => (
              <button key={`${r.season}${r.leagues}`} type="button" className="na-chip"
                onClick={() => setGap({ gap: 'fielding_pro', detail: `${r.season} ${r.leagues ?? ''}`.trim() })}>
                {r.season} {r.leagues ?? 'pro'} fielding: Not available
              </button>
            ))}
          </div>
        )}
        {detail && rows.length > 0 && (
          <p className="hint">
            {view !== 'fielding' && 'Click a season to see every game. Seasons marked n/a have no game log yet; click one to see why. '}
            {rows.some((r) => r.small_sample) && 'Grey numbers are small samples: under 100 PA, or under 30 IP. '}
            Hover any n/a for the reason.
          </p>
        )}
      </div>
      {gameLog && (
        <GameLogModal api={api} player={p} season={gameLog.season} kind={gameLog.kind} onClose={() => setGameLog(null)} />
      )}
      {gap && <NotAvailableDialog gap={gap.gap} detail={gap.detail} onClose={() => setGap(null)} />}
    </div>
  )
}

// The season in each row. Opens its game log, or a Not available notice when there isn't one.
function SeasonCell({ data, context }) {
  if (context.view === 'fielding') return <span>{data.season}</span>
  const has = context.hasLog(data)
  return (
    <button type="button" className={`seasonlink ${has ? '' : 'seasonlink-na'}`}
      title={has ? `Show all ${data.games_logged} games` : 'Game log not available. Click to see why.'}
      onClick={(e) => { e.stopPropagation(); context.openSeason(data) }}>
      {data.season}{!has && <span className="na-mini">n/a</span>}
    </button>
  )
}
