import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

// A small floating panel anchored to an element. Rendered in a portal so grid cells never clip it.
// Closes on outside click and Escape. `hover` panels are for read only details like a badge's team.
export default function Popover({ anchor, open, onClose, children, placement = 'bottom-start', hover = false, className = '' }) {
  const ref = useRef(null)
  const [pos, setPos] = useState({ top: -9999, left: -9999 })

  useLayoutEffect(() => {
    if (!open || !anchor) return
    const place = () => {
      const r = anchor.getBoundingClientRect()
      const el = ref.current
      const w = el?.offsetWidth ?? 0
      const h = el?.offsetHeight ?? 0
      let left = placement.endsWith('end') ? r.right - w : r.left
      let top = r.bottom + 6
      if (top + h > window.innerHeight - 8) top = r.top - h - 6          // flip above when there is no room
      left = Math.max(8, Math.min(left, window.innerWidth - w - 8))
      setPos({ top, left })
    }
    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    return () => {
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
    }
  }, [open, anchor, placement])

  useEffect(() => {
    if (!open || hover) return
    const onDown = (e) => {
      if (ref.current?.contains(e.target) || anchor?.contains(e.target)) return
      onClose?.()
    }
    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose?.()
        anchor?.focus?.()
      }
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey, true)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey, true)
    }
  }, [open, hover, anchor, onClose])

  if (!open) return null
  return createPortal(
    <div ref={ref} className={`popover ${hover ? 'popover-hover' : ''} ${className}`} style={{ top: pos.top, left: pos.left }}
      role={hover ? 'tooltip' : 'dialog'}>
      {children}
    </div>,
    document.body,
  )
}
