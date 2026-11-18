// Made up players for demo mode. Every name is invented. The stat math mirrors db/web.sql
// so the demo behaves like the real site.

function rng(seed) {
  let a = seed
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const FIRST = ['Cody', 'Mason', 'Tyler', 'Grant', 'Luis', 'Evan', 'Brody', 'Dalton', 'Jace', 'Marco', 'Nate', 'Owen',
  'Riley', 'Sam', 'Trey', 'Wyatt', 'Andres', 'Bennett', 'Colt', 'Diego', 'Garrett', 'Hayden', 'Isaac', 'Jonah',
  'Kyle', 'Logan', 'Miles', 'Noah', 'Parker', 'Quinn', 'Reid', 'Tanner', 'Victor', 'Zane', 'Austin', 'Cal']
const LAST = ['Ashby', 'Barlow', 'Castellan', 'Dorsey', 'Ellery', 'Fairbank', 'Galvez', 'Hollis', 'Iverson',
  'Jessup', 'Kettering', 'Lowell', 'Marchetti', 'Northcutt', 'Okafor', 'Pruitt', 'Quintero', 'Rasmussen',
  'Sutter', 'Tolliver', 'Underhill', 'Vance', 'Whitlock', 'Yarbrough', 'Zeller', 'Abernathy', 'Brandt',
  'Corwin', 'Delacruz', 'Embry', 'Fontaine', 'Gentry', 'Haskins', 'Ibarra', 'Joffe', 'Kowalski', 'Lindqvist']
const INDY = ['Boise Hawks', 'Idaho Falls Chukars', 'Missoula PaddleHeads', 'Ogden Raptors', 'Billings Mustangs',
  'Glacier Range Riders', 'Great Falls Voyagers', 'Oakland Ballers', 'Yuba-Sutter Freebirds', 'Long Beach Coast']
const COLLEGES = ['Boise State', 'Gonzaga', 'Nevada', 'BYU', 'Utah', 'Oregon State', 'Washington State',
  'Fresno State', 'Sacramento State', 'Portland', 'Montana State Billings', 'Lewis-Clark State', 'UC Davis', 'Seattle U']
const STATES = [['Boise', 'Idaho'], ['Meridian', 'Idaho'], ['Spokane', 'Wash.'], ['Reno', 'Nev.'], ['Provo', 'Utah'],
  ['Fresno', 'Calif.'], ['Eugene', 'Ore.'], ['Billings', 'Mont.'], ['Tulsa', 'Okla.'], ['Mesa', 'Ariz.']]

const r3 = (x) => (Number.isFinite(x) ? Math.round(x * 1000) / 1000 : null)
const r2 = (x) => (Number.isFinite(x) ? Math.round(x * 100) / 100 : null)
const r1 = (x) => (Number.isFinite(x) ? Math.round(x * 10) / 10 : null)
const ipOf = (outs) => Math.floor(outs / 3) + (outs % 3) / 10

export function battingRates(s) {
  const obpDen = s.ab + s.bb + s.hbp + s.sf
  const tb = s.h + s.b2 + 2 * s.b3 + 3 * s.hr
  return {
    ...s,
    avg: r3(s.h / s.ab), obp: r3((s.h + s.bb + s.hbp) / obpDen), slg: r3(tb / s.ab),
    ops: r3((s.h + s.bb + s.hbp) / obpDen + tb / s.ab), iso: r3((tb - s.h) / s.ab),
    babip: r3((s.h - s.hr) / (s.ab - s.so - s.hr + s.sf)),
    k_pct: r1((100 * s.so) / s.pa), bb_pct: r1((100 * s.bb) / s.pa), small_sample: s.pa < 100,
  }
}

const FIP_C = 3.55
export function pitchingRates(s) {
  const ip = s.outs / 3
  return {
    ...s, ip: ipOf(s.outs),
    era: r2((9 * s.er) / ip), whip: r2((s.bb + s.h) / ip), k9: r1((9 * s.so) / ip), bb9: r1((9 * s.bb) / ip),
    hr9: r1((9 * s.hr) / ip), k_pct: r1((100 * s.so) / s.bf), bb_pct: r1((100 * s.bb) / s.bf),
    k_bb_pct: r1((100 * (s.so - s.bb)) / s.bf),
    fip: r2((13 * s.hr + 3 * (s.bb + s.hbp) - 2 * s.so) / ip + FIP_C), small_sample: s.outs < 90,
  }
}

function hitSeason(rand, season, team, league, talent) {
  const g = 20 + Math.floor(rand() * 75)
  const pa = Math.floor(g * (3.2 + rand() * 1.2))
  const bb = Math.floor(pa * (0.06 + rand() * 0.08 + talent * 0.02))
  const hbp = Math.floor(pa * (0.01 + rand() * 0.02))
  const sf = Math.floor(rand() * 5)
  const ab = pa - bb - hbp - sf
  const so = Math.floor(pa * (0.14 + rand() * 0.14 - talent * 0.03))
  const h = Math.floor((ab - so) * (0.3 + rand() * 0.1 + talent * 0.04))
  const hr = Math.floor(h * (0.03 + rand() * 0.12 + talent * 0.03))
  const b3 = Math.floor(rand() * 4)
  const b2 = Math.floor(h * (0.15 + rand() * 0.1))
  return battingRates({
    season, teams: team, leagues: league, g, pa, ab, r: Math.floor(h * 0.6), h, b2, b3, hr,
    rbi: Math.floor(hr * 3 + h * 0.3), bb, so, hbp, sf, sb: Math.floor(rand() * 25), cs: Math.floor(rand() * 6),
  })
}

function pitSeason(rand, season, team, league, starter, talent) {
  const g = starter ? 10 + Math.floor(rand() * 9) : 15 + Math.floor(rand() * 30)
  const gs = starter ? g - Math.floor(rand() * 2) : Math.floor(rand() * 2)
  const outs = starter ? gs * (13 + Math.floor(rand() * 6)) : g * (3 + Math.floor(rand() * 2))
  const bf = Math.floor(outs * (1.3 + rand() * 0.15))
  const so = Math.floor(bf * (0.17 + rand() * 0.12 + talent * 0.03))
  const bb = Math.floor(bf * (0.06 + rand() * 0.06 - talent * 0.01))
  const hr = Math.floor(bf * (0.015 + rand() * 0.02))
  const h = Math.floor(bf * (0.2 + rand() * 0.06))
  const er = Math.floor(outs / 27 * (2.5 + rand() * 3 - talent))
  return pitchingRates({
    season, teams: team, leagues: league, w: Math.floor(rand() * 9), l: Math.floor(rand() * 7), g, gs,
    sv: starter ? 0 : Math.floor(rand() * 10), outs, bf, h, r: er + Math.floor(rand() * 4), er, hr, bb, so,
    hbp: Math.floor(rand() * 6),
  })
}

export function buildDemo(seed = 2027) {
  const rand = rng(seed)
  const pick = (a) => a[Math.floor(rand() * a.length)]
  const usedNames = new Set()
  const name = () => {
    let n
    do { n = [pick(FIRST), pick(LAST)] } while (usedNames.has(n.join(' ')))
    usedNames.add(n.join(' '))
    return n
  }

  const players = []
  const batting = {}, pitching = {}, fielding = {}
  let id = 1

  const make = (kind) => {
    const [first, last] = name()
    const [city, state] = pick(STATES)
    const isGrad = rand() < 0.35
    const college = pick(COLLEGES)
    const talent = rand() - 0.3
    const pos = kind === 'P' ? (rand() < 0.75 ? 'RHP' : 'LHP')
      : kind === 'TW' ? pick(['OF', '1B', 'INF'])
        : pick(['C', 'C', '1B', '2B', '3B', 'SS', 'INF', 'LF', 'CF', 'RF', 'OF', 'OF'])
    const statusRoll = rand()
    const status = isGrad ? 'free_agent'
      : statusRoll < 0.22 ? 'free_agent' : statusRoll < 0.42 ? 'signed_independent' : 'unknown'
    const team = pick(INDY)
    const p = {
      id: id++, first_name: first, last_name: last, full_name: `${first} ${last}`,
      primary_position: pos,
      position_group: pos === 'C' ? 'C' : ['LF', 'CF', 'RF', 'OF'].includes(pos) ? 'OF' : ['RHP', 'LHP'].includes(pos) ? 'P' : 'IF',
      bats: pick(['R', 'R', 'L', 'S']), throws: pos === 'LHP' ? 'L' : rand() < 0.85 ? 'R' : 'L',
      height_in: 68 + Math.floor(rand() * 10), weight_lb: 170 + Math.floor(rand() * 60),
      hometown: `${city}, ${state}`, grad_year: isGrad ? 2026 : 2022 + Math.floor(rand() * 4), college,
      status, status_label: status === 'free_agent' ? 'Free Agent' : status === 'signed_independent' ? 'Signed' : 'Unconfirmed',
      status_team: status === 'signed_independent' ? team : null,
      status_date: status === 'unknown' ? null : `2026-${pick(['10', '11'])}-${String(1 + Math.floor(rand() * 17)).padStart(2, '0')}`,
      unconfirmed: status === 'unknown', can_sign_now: status === 'free_agent',
      pitcher_role: null, is_two_way: kind === 'TW', marker: null, marker_set_at: null, marker_set_by: null,
    }

    // Season history: college years, then independent years unless he is a 2026 grad.
    const seasons = []
    const firstYear = isGrad ? 2023 : p.grad_year - 3
    for (let y = firstYear; y <= 2026; y++) {
      const inCollege = y <= p.grad_year
      seasons.push({ y, team: inCollege ? college : team, league: inCollege ? 'NCAA D1' : 'Pioneer League' })
    }
    const recent = seasons.slice(-3 - Math.floor(rand() * 2))

    if (kind !== 'P') {
      batting[p.id] = recent.map((s) => hitSeason(rand, s.y, s.team, s.league, talent)).reverse()
      fielding[p.id] = recent.map((s) => {
        const g = batting[p.id].find((b) => b.season === s.y).g
        const po = Math.floor(g * (pos === 'C' ? 7 : pos === '1B' ? 8 : 2) * (0.8 + rand() * 0.4))
        const a = Math.floor(g * (['SS', '2B', '3B', 'INF'].includes(pos) ? 2.5 : 0.3) * (0.8 + rand() * 0.4))
        const e = Math.floor(rand() * 12)
        const row = { season: s.y, position: pos === 'INF' ? 'SS' : pos, teams: s.team, g, po, a, e,
          dp: Math.floor(a * 0.15), fpct: r3((po + a) / (po + a + e)) }
        if (pos === 'C') Object.assign(row, { pb: Math.floor(rand() * 8), sb_against: 20 + Math.floor(rand() * 30), cs_by: 5 + Math.floor(rand() * 15) })
        if (pos === 'C') row.cs_pct = r1((100 * row.cs_by) / (row.sb_against + row.cs_by))
        return row
      }).reverse()
    }
    if (kind !== 'H') {
      const starter = kind === 'P' ? rand() < 0.45 : rand() < 0.3
      pitching[p.id] = recent.map((s) => pitSeason(rand, s.y, s.team, s.league, starter, talent)).reverse()
      const ps = pitching[p.id].slice(0, 3)
      const w = [3, 2, 1]
      const share = ps.reduce((t, s, i) => t + w[i] * s.gs, 0) / ps.reduce((t, s, i) => t + w[i] * s.g, 0)
      p.pitcher_role = share >= 0.5 ? 'SP' : 'RP'
      if (kind === 'TW') {
        // keep two way pitching samples real: at least 20 IP in the latest season
        pitching[p.id][0] = pitchingRates({ ...pitching[p.id][0], outs: Math.max(pitching[p.id][0].outs, 75) })
      }
    }
    // Team column: 2027 club if signed, otherwise the last professional team, otherwise none.
    const lastPro = [...(batting[p.id] ?? []), ...(pitching[p.id] ?? [])]
      .filter((x) => x.leagues === 'Pioneer League').sort((a, b) => b.season - a.season)[0]
    p.team = p.status_team ?? lastPro?.teams ?? null
    players.push(p)
  }

  for (let i = 0; i < 110; i++) make('H')
  for (let i = 0; i < 100; i++) make('P')
  for (let i = 0; i < 7; i++) make('TW')

  // A few markers so the Scouted Players page has something on it.
  players.filter((_, i) => i % 13 === 0).forEach((p, i) => {
    p.marker = ['looking_to_sign', 'potential', 'already_reviewed'][i % 3]
    p.marker_set_at = '2026-11-14T15:00:00Z'
    p.marker_set_by = ['Joe', 'Area scout', 'Pitching coach'][i % 3]
  })

  return { players, batting, pitching, fielding }
}
