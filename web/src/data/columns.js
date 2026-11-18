// Every stat the site shows: label, how to format it, and whether higher is better.
// The filter menu and the export both read from this list, so a new stat only needs adding here.

export const FORMATS = {
  int: (v) => (v == null ? '' : String(Math.round(v))),
  rate3: (v) => {
    if (v == null) return ''
    const s = Number(v).toFixed(3)
    return s.startsWith('0.') ? s.slice(1) : s          // .353, but 1.012 stays
  },
  dec1: (v) => (v == null ? '' : Number(v).toFixed(1)),
  dec2: (v) => (v == null ? '' : Number(v).toFixed(2)),
  pct1: (v) => (v == null ? '' : `${Number(v).toFixed(1)}%`),
  ip: (v) => (v == null ? '' : Number(v).toFixed(1)),  // already in baseball notation (45.2)
  text: (v) => (v == null ? '' : String(v)),
}

const S = (key, label, format, opts = {}) => ({ key, label, format, higherIsBetter: true, ...opts })

export const HITTING = [
  S('g', 'G', 'int'),
  S('pa', 'PA', 'int', { title: 'Plate appearances' }),
  S('ab', 'AB', 'int'),
  S('h', 'H', 'int'),
  S('b2', '2B', 'int'),
  S('b3', '3B', 'int'),
  S('hr', 'HR', 'int'),
  S('rbi', 'RBI', 'int'),
  S('bb', 'BB', 'int'),
  S('so', 'SO', 'int', { higherIsBetter: false }),
  S('sb', 'SB', 'int'),
  S('avg', 'AVG', 'rate3', { title: 'H / AB' }),
  S('obp', 'OBP', 'rate3', { title: '(H + BB + HBP) / (AB + BB + HBP + SF)' }),
  S('slg', 'SLG', 'rate3', { title: 'Total bases / AB' }),
  S('ops', 'OPS', 'rate3', { title: 'OBP + SLG' }),
  S('iso', 'ISO', 'rate3', { title: 'SLG minus AVG' }),
  S('babip', 'BABIP', 'rate3', { title: '(H minus HR) / (AB minus SO minus HR + SF)' }),
  S('k_pct', 'K%', 'pct1', { title: 'SO / PA', higherIsBetter: false }),
  S('bb_pct', 'BB%', 'pct1', { title: 'BB / PA' }),
]

export const PITCHING = [
  S('g', 'G', 'int'),
  S('gs', 'GS', 'int'),
  S('w', 'W', 'int'),
  S('l', 'L', 'int', { higherIsBetter: false }),
  S('sv', 'SV', 'int'),
  S('ip', 'IP', 'ip', { title: 'Innings pitched. 45.2 means 45 and two thirds' }),
  S('h', 'H', 'int', { higherIsBetter: false }),
  S('er', 'ER', 'int', { higherIsBetter: false }),
  S('hr', 'HR', 'int', { higherIsBetter: false }),
  S('bb', 'BB', 'int', { higherIsBetter: false }),
  S('so', 'SO', 'int'),
  S('era', 'ERA', 'dec2', { title: '9 x ER / IP', higherIsBetter: false }),
  S('whip', 'WHIP', 'dec2', { title: '(BB + H) / IP', higherIsBetter: false }),
  S('fip', 'FIP', 'dec2', { title: '(13 x HR + 3 x (BB + HBP) minus 2 x SO) / IP + league constant', higherIsBetter: false }),
  S('k9', 'K/9', 'dec1', { title: '9 x SO / IP' }),
  S('bb9', 'BB/9', 'dec1', { title: '9 x BB / IP', higherIsBetter: false }),
  S('hr9', 'HR/9', 'dec1', { title: '9 x HR / IP', higherIsBetter: false }),
  S('k_pct', 'K%', 'pct1', { title: 'SO / batters faced. Blank when the league does not publish batters faced' }),
  S('bb_pct', 'BB%', 'pct1', { title: 'BB / batters faced', higherIsBetter: false }),
  S('k_bb_pct', 'K-BB%', 'pct1', { title: 'K% minus BB%' }),
]

export const TWO_WAY = [
  S('pa', 'PA', 'int'),
  S('avg', 'AVG', 'rate3'),
  S('obp', 'OBP', 'rate3'),
  S('slg', 'SLG', 'rate3'),
  S('ops', 'OPS', 'rate3'),
  S('hr', 'HR', 'int'),
  S('sb', 'SB', 'int'),
  S('ip', 'IP', 'ip'),
  S('era', 'ERA', 'dec2', { higherIsBetter: false }),
  S('whip', 'WHIP', 'dec2', { higherIsBetter: false }),
  S('fip', 'FIP', 'dec2', { higherIsBetter: false }),
  S('p_so', 'SO', 'int', { title: 'Strikeouts as a pitcher' }),
  S('k9', 'K/9', 'dec1'),
]

export const FIELDING = [
  S('position', 'Pos', 'text'),
  S('g', 'G', 'int'),
  S('po', 'PO', 'int'),
  S('a', 'A', 'int'),
  S('e', 'E', 'int', { higherIsBetter: false }),
  S('dp', 'DP', 'int'),
  S('fpct', 'FPCT', 'rate3', { title: '(PO + A) / (PO + A + E)' }),
  S('pb', 'PB', 'int', { higherIsBetter: false }),
  S('sb_against', 'SB', 'int', { title: 'Stolen bases allowed (catchers)', higherIsBetter: false }),
  S('cs_by', 'CS', 'int', { title: 'Runners caught stealing (catchers)' }),
  S('cs_pct', 'CS%', 'pct1'),
]

export const PAGE_STATS = { hitters: HITTING, pitchers: PITCHING, twoWay: TWO_WAY }

export const MARKERS = [
  { key: 'looking_to_sign', label: 'Looking to Sign' },
  { key: 'potential', label: 'Potential' },
  { key: 'already_reviewed', label: 'Already Reviewed' },
]
export const markerLabel = (k) => MARKERS.find((m) => m.key === k)?.label ?? ''

export const POSITION_GROUPS = {
  hitters: [
    { key: 'all', label: 'All' },
    { key: 'IF', label: 'Infield' },
    { key: 'OF', label: 'Outfield' },
    { key: 'C', label: 'Catcher' },
  ],
  pitchers: [
    { key: 'all', label: 'All' },
    { key: 'SP', label: 'Starters' },
    { key: 'RP', label: 'Relievers' },
  ],
}
