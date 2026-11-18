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
      <StatusBadge player={data} />
    </span>
  )
}

function MarkerCell({ data, context }) {
  return <MarkerButton player={data} onChange={context.setMarker} />
}

// Columns every list starts with, in the order the instructions set:
// marker, name with badge, graduation year, college, then the rest.
// On phones the name column scrolls with the stats instead of staying pinned, so the numbers get the room.
export function leadColumns(narrow = false) {
  const pin = narrow ? undefined : 'left'
  return [
    { headerName: '', field: 'marker', width: 52, pinned: pin, sortable: true, resizable: false,
      cellRenderer: MarkerCell, cellClass: 'cell-marker', comparator: nullsLast, headerTooltip: 'Marker',
      exportValue: (r) => markerLabel(r.marker) },
    { headerName: 'Player', field: 'full_name', width: 250, pinned: pin, cellRenderer: NameCell,
      comparator: (a, b, na, nb) => (na.data.last_name ?? '').localeCompare(nb.data.last_name ?? ''),
      exportValue: (r) => r.full_name, exportExtra: [{ label: 'Status', value: (r) => r.status_label }] },
    { headerName: 'Grad', field: 'grad_year', width: 70, comparator: nullsLast, headerTooltip: 'Graduation year' },
    { headerName: 'College', field: 'college', width: 160, comparator: nullsLast },
    { headerName: 'Pos', field: 'primary_position', width: 66, comparator: nullsLast },
  ]
}

export function statColumns(stats, { seasonField = 'season', teamsField = 'teams', showSeason = true } = {}) {
  const cols = []
  if (showSeason) {
    cols.push({ headerName: 'Yr', field: seasonField, width: 64, comparator: nullsLast, headerTooltip: 'Season these stats are from' })
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
