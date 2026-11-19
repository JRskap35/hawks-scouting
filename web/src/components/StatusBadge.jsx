import { useEffect, useRef, useState } from 'react'
import Popover from '../lib/Popover.jsx'

export const fmtDate = (d) =>
  d ? new Date(`${String(d).slice(0, 10)}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : ''

export function statusDetail(p) {
  const base = p.status_label === 'Signed'
    ? `Signed with ${p.status_team ?? 'an independent club'}${p.status_date ? ` on ${fmtDate(p.status_date)}` : ''}`
    : p.status_label === 'Free Agent'
      ? (p.status_date ? `Free agent since ${fmtDate(p.status_date)}` : 'Free agent')
      : p.status_by_staff ? 'Marked unconfirmed' : 'No 2027 move reported yet'
  const who = p.status_by_staff ? ` Set by ${p.status_set_by ?? 'staff'}${p.status_date ? ` on ${fmtDate(p.status_date)}` : ''}.` : ''
  return `${base}.${who}${p.status_note ? ` Note: ${p.status_note}` : ''}`
}

const OPTIONS = [
  { key: 'free_agent', label: 'Free Agent', help: 'Available to sign now' },
  { key: 'signed_independent', label: 'Signed', help: 'Under contract for 2027' },
  { key: 'unknown', label: 'Unconfirmed', help: 'No reliable word yet' },
]
const currentKey = (p) => (p.status_label === 'Free Agent' ? 'free_agent' : p.status_label === 'Signed' ? 'signed_independent' : 'unknown')

function StatusEditor({ player, edit, onDone }) {
  const [choice, setChoice] = useState(currentKey(player))
  const [team, setTeam] = useState(player.status_team ?? player.team ?? '')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [history, setHistory] = useState(null)

  useEffect(() => {
    let alive = true
    edit.loadHistory(player.id).then((h) => alive && setHistory(h)).catch(() => alive && setHistory([]))
    return () => { alive = false }
  }, [edit, player.id])

  const save = async (e) => {
    e.preventDefault()
    if (choice === 'signed_independent' && !team.trim()) return setError('Enter the team he signed with.')
    setBusy(true); setError('')
    const ok = await edit.save(player.id, choice, choice === 'signed_independent' ? team.trim() : null, note.trim() || null)
    setBusy(false)
    if (ok) onDone()
  }

  return (
    <form className="status-editor" onSubmit={save} onClick={(e) => e.stopPropagation()}>
      <div className="status-editor-head">
        <strong>{player.full_name}</strong>
        <span>2027 status</span>
      </div>
      <fieldset>
        <legend className="sr-only">Status</legend>
        {OPTIONS.map((o) => (
          <label key={o.key} className={`status-opt ${choice === o.key ? 'is-on' : ''}`}>
            <input type="radio" name="status" value={o.key} checked={choice === o.key} onChange={() => setChoice(o.key)} />
            <span className={`badge badge-${o.key === 'free_agent' ? 'fa' : o.key === 'signed_independent' ? 'signed' : 'unconfirmed'}`}>{o.label}</span>
            <span className="status-help">{o.help}</span>
          </label>
        ))}
      </fieldset>
      {choice === 'signed_independent' && (
        <label className="field">
          <span>Signed with</span>
          <input list="team-names" value={team} onChange={(e) => setTeam(e.target.value)} placeholder="Team name" autoFocus />
          <datalist id="team-names">{edit.teamNames.map((t) => <option key={t} value={t} />)}</datalist>
        </label>
      )}
      <label className="field">
        <span>Note (optional)</span>
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Where you heard it, contract details" maxLength={300} />
      </label>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="filterform-actions">
        <button type="button" className="btn btn-quiet" onClick={onDone}>Cancel</button>
        <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? 'Saving' : 'Save status'}</button>
      </div>
      <div className="status-history">
        <div className="status-history-title">History</div>
        {history === null && <p className="hint">Loading</p>}
        {history && history.length === 0 && <p className="hint">No moves on file. Saving here starts his history.</p>}
        {history && history.length > 0 && (
          <ol>
            {history.slice(0, 8).map((h) => (
              <li key={h.id}>
                <span className="h-date">{fmtDate(h.txn_date)}</span>
                <span className="h-text">
                  {h.raw_text}
                  <span className="h-src">{h.by_staff ? ` (staff${h.entered_by_name ? `: ${h.entered_by_name}` : ''})` : ' (league)'}</span>
                  {h.note && <span className="h-note">{h.note}</span>}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </form>
  )
}

// Free Agent, Signed, or Unconfirmed. Hover or focus shows the team, date, and who set it.
// When `edit` is given, clicking opens the editor.
export default function StatusBadge({ player, edit }) {
  const ref = useRef(null)
  const [hover, setHover] = useState(false)
  const [open, setOpen] = useState(false)
  const label = player.status_label ?? 'Unconfirmed'
  const kind = label === 'Free Agent' ? 'fa' : label === 'Signed' ? 'signed' : 'unconfirmed'
  const cls = `badge badge-${kind} ${player.status_by_staff ? 'badge-edited' : ''} ${edit ? 'badge-button' : ''}`
  const props = {
    ref, className: cls,
    onMouseEnter: () => setHover(true), onMouseLeave: () => setHover(false),
    onFocus: () => setHover(true), onBlur: () => setHover(false),
    'aria-label': `${label}. ${statusDetail(player)}${edit ? ' Click to change.' : ''}`,
  }
  return (
    <>
      {edit
        ? <button type="button" {...props} onClick={(e) => { e.stopPropagation(); setHover(false); setOpen((o) => !o) }} aria-haspopup="dialog" aria-expanded={open}>{label}</button>
        : <span tabIndex={0} {...props}>{label}</span>}
      <Popover anchor={ref.current} open={hover && !open} hover>
        <div className="hovercard">{statusDetail(player)}{edit && <div className="hovercard-hint">Click to change</div>}</div>
      </Popover>
      {edit && (
        <Popover anchor={ref.current} open={open} onClose={() => setOpen(false)}>
          <StatusEditor player={player} edit={edit} onDone={() => setOpen(false)} />
        </Popover>
      )}
    </>
  )
}
