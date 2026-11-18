import { useRef, useState } from 'react'
import Popover from '../lib/Popover.jsx'
import { FORMATS } from '../data/columns.js'

// Rate stats are typed the way scouts say them: ".850" for OPS, "3.50" for ERA, "25" for K%.
export function filterText(f, stat) {
  const fmt = FORMATS[stat.format]
  if (f.min != null && f.max != null) return `${stat.label} ${fmt(f.min)} to ${fmt(f.max)}`
  if (f.min != null) return `${stat.label} at least ${fmt(f.min)}`
  return `${stat.label} at most ${fmt(f.max)}`
}

const parse = (v) => {
  if (v === '' || v == null) return null
  const n = Number(String(v).replace('%', '').trim())
  return Number.isFinite(n) ? n : NaN
}

export default function FilterMenu({ stats, onAdd }) {
  const ref = useRef(null)
  const [open, setOpen] = useState(false)
  const [key, setKey] = useState(stats[0]?.key ?? '')
  const [min, setMin] = useState('')
  const [max, setMax] = useState('')
  const [error, setError] = useState('')

  const submit = (e) => {
    e.preventDefault()
    const lo = parse(min), hi = parse(max)
    if (Number.isNaN(lo) || Number.isNaN(hi)) return setError('Enter numbers only, like .850 or 3.50.')
    if (lo == null && hi == null) return setError('Enter a minimum, a maximum, or both.')
    if (lo != null && hi != null && lo > hi) return setError('The minimum is higher than the maximum.')
    onAdd({ key, min: lo, max: hi })
    setOpen(false); setMin(''); setMax(''); setError('')
  }

  const stat = stats.find((s) => s.key === key)
  return (
    <>
      <button ref={ref} type="button" className="btn" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        Add filter
      </button>
      <Popover anchor={ref.current} open={open} onClose={() => setOpen(false)}>
        <form className="filterform" onSubmit={submit}>
          <label>
            <span>Stat</span>
            <select value={key} onChange={(e) => setKey(e.target.value)} autoFocus>
              {stats.filter((s) => s.format !== 'text').map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </label>
          <div className="filterform-range">
            <label><span>Minimum</span><input inputMode="decimal" value={min} onChange={(e) => setMin(e.target.value)} placeholder={stat?.format === 'rate3' ? '.850' : ''} /></label>
            <label><span>Maximum</span><input inputMode="decimal" value={max} onChange={(e) => setMax(e.target.value)} /></label>
          </div>
          {stat?.title && <p className="hint">{stat.label} is {stat.title}.</p>}
          {error && <p className="form-error" role="alert">{error}</p>}
          <div className="filterform-actions">
            <button type="button" className="btn btn-quiet" onClick={() => setOpen(false)}>Cancel</button>
            <button type="submit" className="btn btn-primary">Apply filter</button>
          </div>
        </form>
      </Popover>
    </>
  )
}
