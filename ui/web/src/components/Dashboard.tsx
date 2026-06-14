import { useEffect, useState } from 'react'
import { useRoomStream } from '../useRoomStream'
import { MessageCard } from './MessageCard'
import { Logo } from './Logo'
import type { Side } from '../types'

// Clinic = pine, Payer = ink. (Matches the landing's two-node mesh.)
const ACCENTS = [
  { dot: 'bg-pine', av: 'bg-pine/10 text-pine ring-1 ring-pine/30' },
  { dot: 'bg-ink', av: 'bg-ink/8 text-ink ring-1 ring-ink/20' },
]

function Column({ side, accent }: { side: Side; accent: (typeof ACCENTS)[number] }) {
  const count = side.items?.length ?? 0
  return (
    <div className="flex min-h-0 flex-col bg-bone">
      <h2 className="sticky top-0 z-10 flex items-center gap-2.5 border-b border-line bg-bone/95 px-4 py-3 backdrop-blur">
        <span className={`flex h-7 w-7 items-center justify-center rounded-lg font-mono text-xs font-bold ${accent.av}`}>
          {side.label[0]}
        </span>
        <span className="text-sm font-semibold text-ink">{side.label}</span>
        <span className={`h-1.5 w-1.5 rounded-full ${accent.dot}`} />
        <span className="ml-auto font-mono text-[11px] uppercase tracking-wider text-ink-faint">sees {count}</span>
      </h2>
      <div className="flex flex-col gap-2.5 overflow-y-auto px-4 py-3.5">
        {side.error ? (
          <p className="py-2 text-[13px] italic text-red-500">{side.error}</p>
        ) : count === 0 ? (
          <p className="py-6 text-center text-[13px] italic text-ink-faint">no messages visible to this account</p>
        ) : (
          side.items!.map((m) => <MessageCard key={m.id} msg={m} />)
        )}
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [room, setRoom] = useState('')
  const [input, setInput] = useState('')

  useEffect(() => {
    fetch('/api/state')
      .then((r) => r.json())
      .then((d) => { if (d.room) { setRoom(d.room); setInput(d.room) } })
      .catch(() => {})
  }, [])

  const { state, connected } = useRoomStream(room)
  const sides = state?.sides ?? []

  return (
    <div className="flex h-full flex-col bg-bone">
      <header className="flex items-center gap-3 border-b border-line bg-bone px-5 py-3">
        <a href="#/" className="flex items-center gap-2 transition-opacity hover:opacity-70">
          <Logo size={22} className="text-ink" />
          <span className="font-display text-base font-semibold tracking-tight text-ink">Syntony</span>
        </a>
        <span className="hidden font-mono text-[11px] text-ink-faint sm:inline">· each column = what that account actually sees</span>
        <span className="ml-auto flex items-center gap-1.5 rounded-full border border-line bg-paper px-2.5 py-1 font-mono text-[11px] text-ink-soft">
          <span className="relative flex h-2 w-2">
            {connected && <span className="absolute inline-flex h-full w-full rounded-full bg-pine animate-ping-slow" />}
            <span className={`relative inline-flex h-2 w-2 rounded-full ${connected ? 'bg-pine' : 'bg-ink-faint'}`} />
          </span>
          {connected ? 'live' : 'connecting…'}
        </span>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') setRoom(input.trim()) }}
          onBlur={() => setRoom(input.trim())}
          placeholder="Band room id"
          spellCheck={false}
          className="w-[320px] rounded-lg border border-line bg-paper px-2.5 py-1.5 font-mono text-xs text-ink outline-none transition-colors focus:border-pine"
        />
      </header>

      <div className="flex items-center justify-center gap-2 border-b border-line bg-sunk px-4 py-1.5 font-mono text-[11px] text-ink-faint">
        shared Band room · routed by <span className="text-pine">@mention</span> ·
        <span className="text-coral">thought</span> events stay private to the sender (the audit channel)
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-2 gap-px bg-line">
        {sides.length ? (
          sides.map((s, i) => <Column key={s.prefix} side={s} accent={ACCENTS[i % ACCENTS.length]} />)
        ) : (
          <div className="col-span-2 flex items-center justify-center text-sm italic text-ink-faint">
            {room ? 'loading room…' : 'enter a room id above'}
          </div>
        )}
      </div>
    </div>
  )
}
