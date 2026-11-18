import { useRef, useState } from 'react'
import Popover from '../lib/Popover.jsx'
import { MARKERS, markerLabel } from '../data/columns.js'
import { fmtDate } from './StatusBadge.jsx'

const Star = ({ filled }) => (
  <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
    <path d="M10 1.8l2.5 5.2 5.7.8-4.1 4 1 5.6L10 14.7l-5.1 2.7 1-5.6-4.1-4 5.7-.8z"
      fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
  </svg>
)

// The star on the left of every row. Shared with the whole staff.
export default function MarkerButton({ player, onChange, showLabel = false }) {
  const ref = useRef(null)
  const [open, setOpen] = useState(false)
  const current = player.marker
  const choose = (status) => {
    setOpen(false)
    if (status !== current) onChange(player.id, status)
  }
  return (
    <>
      <button ref={ref} type="button" className={`marker marker-${current ?? 'none'} ${showLabel ? 'marker-wide' : ''}`}
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o) }}
        aria-haspopup="menu" aria-expanded={open}
        aria-label={current ? `Marked ${markerLabel(current)}. Change marker for ${player.full_name}` : `Mark ${player.full_name}`}
        title={current ? markerLabel(current) : 'Mark this player'}>
        <Star filled={!!current} />
        {showLabel && <span>{current ? markerLabel(current) : 'Mark player'}</span>}
      </button>
      <Popover anchor={ref.current} open={open} onClose={() => setOpen(false)}>
        <div className="menu" role="menu">
          {MARKERS.map((m) => (
            <button key={m.key} type="button" role="menuitemradio" aria-checked={current === m.key}
              className={`menu-item marker-opt-${m.key}`} onClick={() => choose(m.key)}>
              <span className="menu-check">{current === m.key ? '✓' : ''}</span>{m.label}
            </button>
          ))}
          {current && (
            <>
              <div className="menu-sep" />
              <button type="button" role="menuitem" className="menu-item" onClick={() => choose(null)}>
                <span className="menu-check" />Clear marker
              </button>
              {player.marker_set_by && (
                <div className="menu-note">Set by {player.marker_set_by}{player.marker_set_at ? ` on ${fmtDate(player.marker_set_at)}` : ''}</div>
              )}
            </>
          )}
        </div>
      </Popover>
    </>
  )
}
