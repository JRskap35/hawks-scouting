import { useState } from 'react'

export default function Login({ api }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState({ kind: '', text: '' })

  const signIn = async (e) => {
    e.preventDefault()
    setBusy(true); setMsg({})
    try { await api.auth.signIn(email.trim(), password) }
    catch (err) { setMsg({ kind: 'error', text: `Sign in failed: ${err.message}. Check the email and password, or email yourself a sign in link.` }) }
    finally { setBusy(false) }
  }
  const sendLink = async () => {
    if (!email.trim()) return setMsg({ kind: 'error', text: 'Enter your email first, then send the link.' })
    setBusy(true); setMsg({})
    try {
      await api.auth.sendLink(email.trim())
      setMsg({ kind: 'ok', text: `Sign in link sent to ${email.trim()}. Open it on this device.` })
    } catch (err) { setMsg({ kind: 'error', text: `The link was not sent: ${err.message}.` }) }
    finally { setBusy(false) }
  }

  return (
    <main className="login">
      <form className="login-card" onSubmit={signIn}>
        <h1>Hawks Scouting</h1>
        <p>Sign in with the account the scouting director set up for you.</p>
        <label><span>Email</span><input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
        <label><span>Password</span><input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        {msg.text && <p className={msg.kind === 'error' ? 'form-error' : 'form-ok'} role="status">{msg.text}</p>}
        <button type="submit" className="btn btn-primary btn-block" disabled={busy || !password}>Sign in</button>
        <button type="button" className="btn btn-quiet btn-block" onClick={sendLink} disabled={busy}>Email me a sign in link</button>
      </form>
    </main>
  )
}
