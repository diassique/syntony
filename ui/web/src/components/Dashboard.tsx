import { useEffect, useState } from 'react'
import { useRoomStream } from '../useRoomStream'
import { MessageCard } from './MessageCard'
import { Logo } from './Logo'
import type { Side } from '../types'

const ACCENTS = [
  { dot: 'bg-emerald-400', text: 'text-emerald-300', ring: 'ring-emerald-500/30', av: 'bg-emerald-500/15 text-emerald-300' },
  { dot: 'bg-violet-400', text: 'text-violet-300', ring: 'ring-violet-500/30', av: 'bg-violet-500/15 text-violet-300' },
]

function Column({ side, accent }: { side: Side; accent: (typeof ACCENTS)[number] }) {
  const count = side.items?.length ?? 0
  return (
    <div className="flex min-h-0 flex-col bg-[#0a0e18]">
      <h2 className={`sticky top-0 z-10 flex items-center gap-2.5 border-b border-[#161d2e] bg-[#0a0e18]/95 px-4 py-3 backdrop-blur`}>
        <span className={`flex h-7 w-7 items-center justify-center rounded-lg text-xs font-bold ring-1 ${accent.av} ${accent.ring}`}>
          {side.label[0]}
        </span>
        <span className="text-sm font-semibold text-[#dbe3f4]">{side.label}</span>
        <span className={`h-1.5 w-1.5 rounded-full ${accent.dot}`} />
        <span className="ml-auto text-[11px] uppercase tracking-wider text-[#5c6a85]">sees {count}</span>
      </h2>
      <div className="flex flex-col gap-2.5 overflow-y-auto px-4 py-3.5">
        {side.error ? (
          <p className="py-2 text-[13px] italic text-red-400">{side.error}</p>
        ) : count === 0 ? (
          <p className="py-6 text-center text-[13px] italic text-[#5c6a85]">no messages visible to this account</p>
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
    <div className="flex h-full flex-col bg-[#07090f]">
      <header className="flex items-center gap-3 border-b border-[#161d2e] px-5 py-3">
        <a href="#/" className="flex items-center gap-2 transition-opacity hover:opacity-80">
          <Logo size={24} />
          <span className="text-base font-semibold text-[#e6e6e6]">Syntony</span>
        </a>
        <span className="hidden text-xs text-[#6b7790] sm:inline">· each column shows what that account actually sees</span>
        <span className="ml-auto flex items-center gap-1.5 rounded-full border border-[#1c2740] bg-[#0c1322] px-2.5 py-1 text-[11px] text-[#9fb0cc]">
          <span className="relative flex h-2 w-2">
            {connected && <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 animate-ping-slow" />}
            <span className={`relative inline-flex h-2 w-2 rounded-full ${connected ? 'bg-emerald-400' : 'bg-zinc-600'}`} />
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
          className="w-[320px] rounded-lg border border-[#222d45] bg-[#0c1322] px-2.5 py-1.5 font-mono text-xs text-[#cdd8ee] outline-none transition-colors focus:border-violet-500/60"
        />
      </header>

      <div className="flex items-center justify-center gap-2 border-b border-[#11182680] bg-[#080b12] px-4 py-1.5 text-[11px] text-[#5c6a85]">
        shared Band room · routed by <span className="text-[#8ad8a0]">@mention</span> ·
        <span className="text-amber-300/90">thought</span> events stay private to the sender (the audit channel)
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-2 gap-px bg-[#161d2e]">
        {sides.length ? (
          sides.map((s, i) => <Column key={s.prefix} side={s} accent={ACCENTS[i % ACCENTS.length]} />)
        ) : (
          <div className="col-span-2 flex items-center justify-center text-sm italic text-[#5c6a85]">
            {room ? 'loading room…' : 'enter a room id above'}
          </div>
        )}
      </div>
    </div>
  )
}
