// Every place the site knows data is missing, why, and what would fix it.
// When a gap gets fixed, update or remove its entry here and the site follows.

export const GAPS = {
  gamelog_pro: {
    title: 'Game log not available',
    why: "Game by game stats for the Pioneer League only come from the league's own site, which blocks automated requests. Baseball Reference does not publish independent league game logs.",
    fix: 'Get access from the league office or PrestoSports. The game log reader is already built and will load these as soon as the site allows it.',
  },
  gamelog_college: {
    title: 'College game log not loaded',
    why: 'School stat sites publish game logs, and they are reachable, but the college scraper is not built yet.',
    fix: 'Build the college scraper. It would also bring in 2026 seniors who never played pro ball.',
  },
  fielding_pro: {
    title: 'Fielding not available',
    why: "Baseball Reference does not publish independent league fielding, and the Pioneer League's own site blocks automated requests.",
    fix: 'Same fix as game logs: league or PrestoSports access. College and summer league fielding is already loaded.',
  },
}

// Reasons shown when a single stat cell is blank (hover the grey n/a).
const STAT_REASONS = {
  fip: 'FIP needs the whole league\'s totals, so it is only calculated for leagues loaded in full (the Pioneer League). College conferences are only partly loaded.',
  k_pct: 'Needs batters faced, which the source does not list for this season.',
  bb_pct: 'Needs batters faced, which the source does not list for this season.',
  k_bb_pct: 'Needs batters faced, which the source does not list for this season.',
  pitches: 'The source does not publish pitch counts for this game.',
  strikes: 'The source does not publish strike counts for this game.',
  bf: 'The source does not publish batters faced for this game.',
}

export const statGap = (key) => `Not available. ${STAT_REASONS[key] ?? 'The source does not publish this number for this season.'}`
