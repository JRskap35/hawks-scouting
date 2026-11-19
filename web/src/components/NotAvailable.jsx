import { useEffect, useRef } from 'react'
import { GAPS } from '../data/gaps.js'

// A "Not available" notice for data the site can't get yet. Marks it as a known gap
// and says what would fix it, so it doubles as a to do list.

export function NotAvailablePanel({ gap, detail }) {
  const g = GAPS[gap]
  return (
    <div className="na-panel" role="note">
      <span className="na-tag">Not available</span>
      <div>
        <p className="na-title">{g.title}{detail ? `: ${detail}` : ''}</p>
        <p><strong>Why:</strong> {g.why}</p>
        <p><strong>What would fix it:</strong> {g.fix}</p>
      </div>
    </div>
  )
}

export default function NotAvailableDialog({ gap, detail, onClose }) {
  const okRef = useRef(null)
  useEffect(() => {
    okRef.current?.focus()
    const onKey = (e) => { if (e.key === 'Escape') { e.stopPropagation(); onClose() } }
    document.addEventListener('keydown', onKey, true)
    return () => document.removeEventListener('keydown', onKey, true)
  }, [onClose])
  return (
    <div className="modal-backdrop modal-stack" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal na-dialog" role="alertdialog" aria-modal="true" aria-labelledby="na-title">
        <NotAvailablePanel gap={gap} detail={detail} />
        <div className="na-actions">
          <button ref={okRef} type="button" className="btn btn-primary" onClick={onClose}>OK</button>
        </div>
      </div>
    </div>
  )
}
