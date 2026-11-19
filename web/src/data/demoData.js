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

// ---------------------------------------------------------------------------
// Game by game simulation for professional seasons. The season line is the sum of the
// games, so the game log totals always match the season row, as they do with real data.
// ---------------------------------------------------------------------------

function seasonDates(rand, n, year, everyFew = 1) {
  const start = Date.UTC(year, 4, 20), end = Date.UTC(year, 8, 6)
  const days = Math.round((end - start) / 864e5)
  const picked = new Set()
  if (everyFew > 1) {
    for (let d = Math.floor(rand() * 4); d <= days && picked.size < n; d += everyFew + Math.floor(rand() * 2)) picked.add(d)
  }
  while (picked.size < Math.min(n, days)) picked.add(Math.floor(rand() * days))
  return [...picked].sort((a, b) => a - b).map((d) => new Date(start + d * 864e5).toISOString().slice(0, 10))
}

function gameShell(rand, date, team, opponents) {
  const us = Math.floor(rand() * 9), them = Math.floor(rand() * 9)
  const tie = us === them
  const won = tie ? rand() < 0.5 : us > them
  const hi = Math.max(us, them) + (tie ? 1 : 0), lo = Math.min(us, them)
  return {
    game_date: date, game_no: 1, team, opponent: opponents[Math.floor(rand() * opponents.length)],
    home_away: rand() < 0.5 ? 'H' : 'A', result: `${won ? 'W' : 'L'} ${won ? hi : lo}-${won ? lo : hi}`, won,
  }
}

function simHitGames(rand, year, team, opponents, talent) {
  const n = 45 + Math.floor(rand() * 45)
  return seasonDates(rand, n, year).map((date) => {
    const g = { ...gameShell(rand, date, team, opponents), pa: 0, ab: 0, r: 0, h: 0, b2: 0, b3: 0, hr: 0, rbi: 0, bb: 0, so: 0, hbp: 0, sf: 0, sb: 0, cs: 0 }
    const pas = 3 + Math.floor(rand() * 3)
    for (let i = 0; i < pas; i++) {
      g.pa++
      const x = rand()
      const bb = 0.085 + 0.02 * talent, hbp = 0.012, so = 0.22 - 0.03 * talent, hr = 0.025 + 0.015 * talent
      if (x < bb) g.bb++
      else if (x < bb + hbp) g.hbp++
      else if (x < bb + hbp + 0.008) { g.sf++; g.rbi++ }
      else {
        g.ab++
        const y = rand()
        if (y < so) g.so++
        else if (y < so + hr) { g.h++; g.hr++; g.r++; g.rbi += 1 + Math.floor(rand() * 2) }
        else if (y < so + hr + 0.005) { g.h++; g.b3++ }
        else if (y < so + hr + 0.05) { g.h++; g.b2++ }
        else if (y < so + hr + 0.21 + 0.03 * talent) g.h++
      }
    }
    g.r += rand() < 0.3 ? 1 : 0
    g.rbi += g.h > 0 && rand() < 0.3 ? 1 : 0
    if (rand() < 0.12) g.sb++
    if (rand() < 0.03) g.cs++
    delete g.won
    return g
  })
}

function simPitchGames(rand, year, team, opponents, starter, talent, minGames = 0) {
  const n = Math.max(minGames, starter ? 12 + Math.floor(rand() * 7) : 18 + Math.floor(rand() * 18))
  return seasonDates(rand, n, year, starter ? 5 : 1).map((date) => {
    const shell = gameShell(rand, date, team, opponents)
    const g = { ...shell, started: starter, decision: null, outs: 0, bf: 0, h: 0, r: 0, er: 0, hr: 0, bb: 0, so: 0, hbp: 0, wp: 0 }
    const target = starter ? 12 + Math.floor(rand() * 10) : 2 + Math.floor(rand() * 5)
    let traffic = 0
    while (g.outs < target && g.bf < 40) {
      g.bf++
      const x = rand()
      const so = 0.23 + 0.03 * talent, bb = 0.085 - 0.01 * talent, hr = 0.024
      if (x < so) { g.so++; g.outs++ }
      else if (x < so + bb) { g.bb++; traffic++ }
      else if (x < so + bb + 0.01) { g.hbp++; traffic++ }
      else if (x < so + bb + 0.01 + hr) { g.h++; g.hr++; g.er += 1 + Math.min(traffic, 2); traffic = 0 }
      else if (x < so + bb + 0.01 + hr + 0.2) { g.h++; traffic++; if (traffic >= 3) { g.er++; traffic-- } }
      else g.outs++
    }
    g.r = g.er + (rand() < 0.12 ? 1 : 0)
    if (rand() < 0.08) g.wp++
    g.pitches = Math.round(g.bf * (3.6 + rand() * 0.6))
    g.strikes = Math.round(g.pitches * (0.6 + rand() * 0.06))
    g.decision = starter
      ? (g.outs >= 15 && shell.won && rand() < 0.7 ? 'W' : !shell.won && rand() < 0.5 ? 'L' : null)
      : (shell.won && rand() < 0.15 ? 'S' : shell.won && rand() < 0.15 ? 'H' : !shell.won && rand() < 0.08 ? 'L' : null)
    delete g.won
    return { ...g, ip: Math.floor(g.outs / 3) + (g.outs % 3) / 10 }
  })
}

const sum = (rows, k) => rows.reduce((t, r) => t + (r[k] ?? 0), 0)

function battingFromGames(games, season, team, league) {
  const t = Object.fromEntries(['pa', 'ab', 'r', 'h', 'b2', 'b3', 'hr', 'rbi', 'bb', 'so', 'hbp', 'sf', 'sb', 'cs'].map((k) => [k, sum(games, k)]))
  return battingRates({ season, teams: team, leagues: league, g: games.length, ...t, games_logged: games.length })
}

function pitchingFromGames(games, season, team, league) {
  const t = Object.fromEntries(['outs', 'bf', 'h', 'r', 'er', 'hr', 'bb', 'so', 'hbp'].map((k) => [k, sum(games, k)]))
  return pitchingRates({
    season, teams: team, leagues: league, g: games.length, gs: games.filter((x) => x.started).length,
    w: games.filter((x) => x.decision === 'W').length, l: games.filter((x) => x.decision === 'L').length,
    sv: games.filter((x) => x.decision === 'S').length, ...t, games_logged: games.length,
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
  const battingGames = {}, pitchingGames = {}        // [playerId][season] -> games
  const history = {}                                  // [playerId] -> status moves, oldest first
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

    const opponents = INDY.filter((t) => t !== team)
    const isPro = (s) => s.league === 'Pioneer League'

    if (kind !== 'P') {
      battingGames[p.id] = {}
      batting[p.id] = recent.map((s) => {
        if (!isPro(s)) return hitSeason(rand, s.y, s.team, s.league, talent)
        const games = simHitGames(rand, s.y, s.team, opponents, talent)
        battingGames[p.id][s.y] = games
        return battingFromGames(games, s.y, s.team, s.league)
      }).reverse()
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
      pitchingGames[p.id] = {}
      pitching[p.id] = recent.map((s, i) => {
        if (!isPro(s)) return pitSeason(rand, s.y, s.team, s.league, starter, talent)
        // two way players get enough relief outings to clear 20 IP in their latest season
        const minGames = kind === 'TW' && i === recent.length - 1 ? 24 : 0
        const games = simPitchGames(rand, s.y, s.team, opponents, starter, talent, minGames)
        pitchingGames[p.id][s.y] = games
        return pitchingFromGames(games, s.y, s.team, s.league)
      }).reverse()
      const ps = pitching[p.id].slice(0, 3)
      const w = [3, 2, 1]
      const share = ps.reduce((t, s, i) => t + w[i] * s.gs, 0) / ps.reduce((t, s, i) => t + w[i] * s.g, 0)
      p.pitcher_role = share >= 0.5 ? 'SP' : 'RP'
      if (kind === 'TW' && pitching[p.id][0].outs < 60) {
        // a two way player who is still a college grad: keep his pitching sample over 20 IP
        pitching[p.id][0] = pitchingRates({ ...pitching[p.id][0], outs: 75, bf: 100 })
      }
    }
    // Team column: 2027 club if signed, otherwise the last professional team, otherwise none.
    const lastPro = [...(batting[p.id] ?? []), ...(pitching[p.id] ?? [])]
      .filter((x) => x.leagues === 'Pioneer League').sort((a, b) => b.season - a.season)[0]
    p.last_pro_team = lastPro?.teams ?? null
    p.team = p.status_team ?? p.last_pro_team
    // League moves behind the badge, for the status history
    if (p.status !== 'unknown') {
      history[p.id] = [{
        id: p.id * 10, txn_date: p.status_date, by_staff: false,
        raw_text: p.status === 'signed_independent' ? `Signed ${p.full_name} to their 2027 roster`
          : p.grad_year === 2026 && !lastPro ? 'Graduated, no pro contract on record' : `Placed ${p.full_name} on Irrevocable waivers`,
      }]
    }
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

  return { players, batting, pitching, fielding, battingGames, pitchingGames, history }
}
