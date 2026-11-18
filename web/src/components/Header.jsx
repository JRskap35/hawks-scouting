import { useMemo, useRef, useState } from 'react'
import Popover from '../lib/Popover.jsx'

const TABS = [
  { key: 'hitters', label: 'Position Players' },
  { key: 'pitchers', label: 'Pitchers' },
  { key: 'twoWay', label: 'Two Way Players' },
]

function SearchBox({ players, onPick }) {
  const ref = useRef(null)
  const [q, setQ] = useState('')
  const [active, setActive] = useState(0)
  const results = useMemo(() => {
    const t = q.trim().toLowerCase()
    if (t.length < 2) return []
    return players.filter((p) => p.full_name.toLowerCase().includes(t)).slice(0, 8)
  }, [q, players])

  const pick = (p) => { onPick(p.id); setQ(''); ref.current?.blur() }
  const onKey = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)) }
    // preventDefault stops the same key press from landing on the pop up's Close button
    if (e.key === 'Enter' && results[active]) { e.preventDefault(); pick(results[active]) }
    if (e.key === 'Escape') setQ('')
  }
  return (
    <div className="search">
      <input ref={ref} type="search" value={q} placeholder="Find a player"
        onChange={(e) => { setQ(e.target.value); setActive(0) }} onKeyDown={onKey}
        aria-label="Find a player by name" role="combobox" aria-expanded={results.length > 0} aria-controls="search-results" />
      <Popover anchor={ref.current} open={results.length > 0 || q.trim().length >= 2} onClose={() => setQ('')}>
        <ul className="menu search-results" id="search-results" role="listbox">
          {results.length === 0 && <li className="menu-note">No player in the pool matches "{q.trim()}".</li>}
          {results.map((p, i) => (
            <li key={p.id} role="option" aria-selected={i === active}>
              <button type="button" className={`menu-item ${i === active ? 'is-active' : ''}`}
                onMouseEnter={() => setActive(i)} onClick={() => pick(p)}>
                <span className="search-name">{p.full_name}</span>
                <span className="search-meta">{[p.primary_position, p.status_label].filter(Boolean).join(', ')}</span>
              </button>
            </li>
          ))}
        </ul>
      </Popover>
    </div>
  )
}

export default function Header({ page, setPage, scoutedCount, players, onPick, demo, onSignOut, email }) {
  return (
    <header className="topbar">
      <div className="brand">
        <svg viewBox="0 0 32 32" width="26" height="26" aria-hidden="true">
          <circle cx="16" cy="16" r="14" fill="#1C2B24" />
          <path d="M9 7c4 5 4 13 0 18M23 7c-4 5-4 13 0 18" stroke="#E9B10E" strokeWidth="2" fill="none" />
        </svg>
        <span>Hawks Scouting</span>
      </div>
      <nav className="tabs" aria-label="Player lists">
        {TABS.map((t) => (
          <button key={t.key} type="button" className={`tab ${page === t.key ? 'is-current' : ''}`}
            aria-current={page === t.key ? 'page' : undefined} onClick={() => setPage(t.key)}>
            {t.label}
          </button>
        ))}
      </nav>
      <SearchBox players={players} onPick={onPick} />
      <button type="button" className={`tab tab-scouted ${page === 'scouted' ? 'is-current' : ''}`}
        aria-current={page === 'scouted' ? 'page' : undefined} onClick={() => setPage('scouted')}>
        Scouted Players <span className="count">{scoutedCount}</span>
      </button>
      <div className="account">
        {demo ? <span className="demo-pill" title="Made up players. Connect Supabase to see real data.">Demo data</span>
          : <button type="button" className="btn btn-quiet btn-small" onClick={onSignOut} title={email}>Sign out</button>}
      </div>
    </header>
  )
}
