import { useRef, useState } from 'react'
import Popover from '../lib/Popover.jsx'

export const fmtDate = (d) =>
  d ? new Date(`${String(d).slice(0, 10)}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : ''

export function statusDetail(p) {
  if (p.status_label === 'Signed') return `Signed with ${p.status_team ?? 'an independent club'}${p.status_date ? ` on ${fmtDate(p.status_date)}` : ''}`
  if (p.status_label === 'Free Agent') return p.status_date ? `Free agent since ${fmtDate(p.status_date)}` : 'Free agent'
  return 'No 2027 move reported yet'
}

// Free Agent, Signed, or Unconfirmed. Hover or focus shows the team and date.
export default function StatusBadge({ player }) {
  const ref = useRef(null)
  const [open, setOpen] = useState(false)
  const label = player.status_label ?? 'Unconfirmed'
  const kind = label === 'Free Agent' ? 'fa' : label === 'Signed' ? 'signed' : 'unconfirmed'
  return (
    <>
      <span ref={ref} className={`badge badge-${kind}`} tabIndex={0}
        onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}
        aria-label={`${label}. ${statusDetail(player)}`}>
        {label}
      </span>
      <Popover anchor={ref.current} open={open} hover>
        <div className="hovercard">{statusDetail(player)}</div>
      </Popover>
    </>
  )
}
