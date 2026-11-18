// One interface, two backends: the live Supabase database, or made up demo data.
// Demo mode turns on when no Supabase settings are present, or with VITE_DEMO=true.

import { createClient } from '@supabase/supabase-js'
import { buildDemo } from './demoData.js'

const URL = import.meta.env.VITE_SUPABASE_URL
const KEY = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY
export const IS_DEMO = import.meta.env.VITE_DEMO === 'true' || !URL || !KEY

// ---------------------------------------------------------------------------
// Live
// ---------------------------------------------------------------------------

function liveApi() {
  const sb = createClient(URL, KEY)

  // Supabase returns at most 1,000 rows per request, so page through big views.
  async function all(view, order = 'last_name') {
    const out = []
    const size = 1000
    for (let from = 0; ; from += size) {
      const { data, error } = await sb.from(view).select('*').order(order).range(from, from + size - 1)
      if (error) throw new Error(`${view}: ${error.message}`)
      out.push(...data)
      if (data.length < size) return out
    }
  }

  return {
    mode: 'live',
    auth: {
      async session() {
        const { data } = await sb.auth.getSession()
        return data.session
      },
      onChange(fn) {
        const { data } = sb.auth.onAuthStateChange((_e, session) => fn(session))
        return () => data.subscription.unsubscribe()
      },
      async signIn(email, password) {
        const { error } = await sb.auth.signInWithPassword({ email, password })
        if (error) throw new Error(error.message)
      },
      async sendLink(email) {
        const { error } = await sb.auth.signInWithOtp({
          email, options: { shouldCreateUser: false, emailRedirectTo: window.location.href.split('#')[0] },
        })
        if (error) throw new Error(error.message)
      },
      async signOut() { await sb.auth.signOut() },
    },

    async loadLists() {
      const [hitters, pitchers, twoWay] = await Promise.all([all('ui_hitters'), all('ui_pitchers'), all('ui_two_way')])
      return { hitters, pitchers, twoWay }
    },

    async loadPlayer(id) {
      const q = (view, order) => sb.from(view).select('*').eq(order ? 'player_id' : 'id', id)
      const [p, b, pi, f] = await Promise.all([
        q('ui_players').maybeSingle(),
        q('ui_batting_seasons', true).order('season', { ascending: false }),
        q('ui_pitching_seasons', true).order('season', { ascending: false }),
        q('ui_fielding_seasons', true).order('season', { ascending: false }),
      ])
      for (const r of [p, b, pi, f]) if (r.error) throw new Error(r.error.message)
      return { player: p.data, batting: b.data, pitching: pi.data, fielding: f.data }
    },

    // Returns the saved marker fields so every list can update without a reload.
    async setMarker(playerId, status) {
      if (!status) {
        const { error } = await sb.from('player_markers').delete().eq('player_id', playerId)
        if (error) throw new Error(error.message)
        return { marker: null, marker_set_at: null, marker_set_by: null }
      }
      const { error } = await sb.from('player_markers').upsert({ player_id: playerId, status }, { onConflict: 'player_id' })
      if (error) throw new Error(error.message)
      const { data } = await sb.from('ui_players').select('marker, marker_set_at, marker_set_by').eq('id', playerId).maybeSingle()
      return data ?? { marker: status, marker_set_at: new Date().toISOString(), marker_set_by: null }
    },
  }
}

// ---------------------------------------------------------------------------
// Demo
// ---------------------------------------------------------------------------

function demoApi() {
  const d = buildDemo()
  const byId = new Map(d.players.map((p) => [p.id, p]))

  const lists = () => {
    const hitters = [], pitchers = [], twoWay = []
    for (const p of d.players) {
      const b = d.batting[p.id]?.[0]
      const pi = d.pitching[p.id]?.[0]
      if (b && (p.position_group !== 'P' || p.is_two_way)) hitters.push({ ...p, ...b })
      if (pi && (p.position_group === 'P' || p.is_two_way)) pitchers.push({ ...p, ...pi })
      if (p.is_two_way) {
        twoWay.push({
          ...p, teams: b?.teams ?? pi?.teams, bat_season: b?.season, pa: b?.pa, avg: b?.avg, obp: b?.obp, slg: b?.slg, ops: b?.ops, hr: b?.hr, sb: b?.sb,
          pit_season: pi?.season, ip: pi?.ip, era: pi?.era, whip: pi?.whip, fip: pi?.fip, p_so: pi?.so, k9: pi?.k9,
        })
      }
    }
    return { hitters, pitchers, twoWay }
  }

  return {
    mode: 'demo',
    auth: {
      session: async () => ({ user: { email: 'demo@hawks' } }),
      onChange: () => () => {},
      signIn: async () => {}, sendLink: async () => {}, signOut: async () => {},
    },
    loadLists: async () => lists(),
    loadPlayer: async (id) => ({
      player: byId.get(id), batting: d.batting[id] ?? [], pitching: d.pitching[id] ?? [], fielding: d.fielding[id] ?? [],
    }),
    setMarker: async (id, status) => {
      const p = byId.get(id)
      Object.assign(p, status
        ? { marker: status, marker_set_at: new Date().toISOString(), marker_set_by: 'You' }
        : { marker: null, marker_set_at: null, marker_set_by: null })
      return { marker: p.marker, marker_set_at: p.marker_set_at, marker_set_by: p.marker_set_by }
    },
  }
}

export const api = IS_DEMO ? demoApi() : liveApi()
