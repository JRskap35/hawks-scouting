import { themeQuartz } from 'ag-grid-community'
import MarkerButton from '../components/MarkerButton.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import { FORMATS, markerLabel } from '../data/columns.js'

export const gridTheme = themeQuartz.withParams({
  fontFamily: '"Barlow Semi Condensed", "Arial Narrow", system-ui, sans-serif',
  headerFontFamily: '"Barlow Semi Condensed", "Arial Narrow", system-ui, sans-serif',
  fontSize: 14,
  headerFontSize: 13,
  headerFontWeight: 600,
  foregroundColor: '#1C2B24',
  backgroundColor: '#FFFFFF',
  headerBackgroundColor: '#EBF0EB',
  headerTextColor: '#3E5446',
  oddRowBackgroundColor: '#F8FAF8',
  rowHoverColor: '#FBF3D6',
  borderColor: '#D5DDD6',
  accentColor: '#C99500',
  rowHeight: 36,
  headerHeight: 38,
  spacing: 6,
  wrapperBorderRadius: 0,
  borderRadius: 3,
})

// Blank values always sort to the bottom, whichever direction the column is sorted.
export const nullsLast = (a, b, _na, _nb, desc) => {
  const an = a == null || a === '', bn = b == null || b === ''
  if (an && bn) return 0
  if (an) return desc ? -1 : 1
  if (bn) return desc ? 1 : -1
  return typeof a === 'string' ? a.localeCompare(b) : a - b
}

export const heightText = (inches) => (inches ? `${Math.floor(inches / 12)}-${inches % 12}` : '')

function NameCell({ data, context }) {
  return (
    <span className="namecell">
      <button type="button" className="namelink" onClick={() => context.openPlayer(data.id)}>{data.full_name}</button>
      <StatusBadge player={data} edit={context.statusEdit} />
    </span>
  )
}

function MarkerCell({ data, context }) {
  return <MarkerButton player={data} onChange={context.setMarker} />
}

function TeamCell({ value }) {
  return value ? <span>{value}</span> : <span className="none">None</span>
}

export const collegeText = (r) => (r.college ? `${r.college}${r.grad_year ? ` (${r.grad_year})` : ''}` : '')

// Columns every list starts with:
// marker, name with badge, team, college with graduation year, position, bats, throws.
export function leadColumns(narrow = false, { role = false } = {}) {
  const pin = narrow ? undefined : 'left'
  const cols = [
    { headerName: '', field: 'marker', width: 52, pinned: pin, sortable: true, resizable: false,
      cellRenderer: MarkerCell, cellClass: 'cell-marker', comparator: nullsLast, headerTooltip: 'Marker',
      exportValue: (r) => markerLabel(r.marker) },
    // The value includes the status, so the cell redraws when a badge is edited.
    { headerName: 'Name', colId: 'full_name', width: 250, pinned: pin, cellRenderer: NameCell,
      valueGetter: (p) => `${p.data.full_name}|${p.data.status_label}|${p.data.status_team ?? ''}|${p.data.status_by_staff ? 1 : 0}|${p.data.status_note ?? ''}`,
      comparator: (a, b, na, nb) => (na.data.last_name ?? '').localeCompare(nb.data.last_name ?? ''),
      exportValue: (r) => r.full_name, exportExtra: [{ label: 'Status', value: (r) => r.status_label }] },
    { headerName: 'Team', field: 'team', width: 185, cellRenderer: TeamCell, comparator: nullsLast, tooltipField: 'team',
      headerTooltip: 'His 2027 club if signed, otherwise the last professional team he played for',
      exportValue: (r) => r.team ?? '' },
    { headerName: 'College', colId: 'college', width: 230, valueGetter: (p) => collegeText(p.data), comparator: nullsLast,
      tooltipValueGetter: (p) => collegeText(p.data), headerTooltip: 'College and graduation year',
      exportValue: collegeText },
    { headerName: 'Pos', field: 'primary_position', width: 62, comparator: nullsLast },
    { headerName: 'B', field: 'bats', width: 46, headerTooltip: 'Bats' },
    { headerName: 'T', field: 'throws', width: 46, headerTooltip: 'Throws' },
  ]
  if (role) {
    cols.push({ headerName: 'Role', field: 'pitcher_role', width: 62, comparator: nullsLast,
      headerTooltip: "Starter when 50% or more of his last three seasons' appearances were starts, weighted toward the most recent" })
  }
  return cols
}

// showTeam adds the club for each season (used in the pop up, where every row is a different season).
export function statColumns(stats, { seasonField = 'season', teamsField = 'teams', showSeason = true, showTeam = false } = {}) {
  const cols = []
  if (showSeason) {
    cols.push({ headerName: 'Yr', field: seasonField, width: 64, comparator: nullsLast, headerTooltip: 'Season these stats are from' })
  }
  if (showTeam) {
    cols.push({ headerName: 'Team', field: teamsField, width: 170, comparator: nullsLast, tooltipField: teamsField })
  }
  for (const s of stats) {
    const fmt = FORMATS[s.format]
    const numeric = s.format !== 'text'
    cols.push({
      headerName: s.label,
      field: s.key,
      width: s.format === 'pct1' ? 74 : s.format === 'int' ? 60 : 70,
      headerTooltip: s.title ? `${s.label}: ${s.title}` : undefined,
      valueFormatter: (p) => fmt(p.value),
      comparator: nullsLast,
      cellClass: (p) => [numeric ? 'num' : '', p.data?.small_sample && numeric ? 'is-small' : ''].join(' '),
      headerClass: numeric ? 'num-h' : '',
      exportValue: (r) => fmt(r[s.key]),
    })
  }
  return cols
}

// Turn the grid's columns into export columns (label + text value).
export function exportColumns(colDefs) {
  const out = []
  for (const c of colDefs) {
    if (c.hide) continue
    out.push({ label: c.headerName || 'Marker', value: c.exportValue ?? ((r) => (r[c.field] ?? '').toString()) })
    if (c.exportExtra) out.push(...c.exportExtra)
  }
  return out
}
