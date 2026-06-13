import type { Msg } from '../types'

const STYLE: Record<string, { badge: string; bar: string; label: string }> = {
  text: { badge: 'text-emerald-300 border-emerald-700/50 bg-emerald-900/30', bar: 'bg-emerald-400/70', label: 'message' },
  thought: { badge: 'text-amber-300 border-amber-700/50 bg-amber-900/30', bar: 'bg-amber-400/70', label: 'private · audit' },
  tool_call: { badge: 'text-sky-300 border-sky-700/50 bg-sky-900/30', bar: 'bg-sky-400/70', label: 'tool call' },
  tool_result: { badge: 'text-sky-300 border-sky-700/50 bg-sky-900/30', bar: 'bg-sky-400/70', label: 'tool result' },
  error: { badge: 'text-red-300 border-red-700/50 bg-red-900/30', bar: 'bg-red-400/70', label: 'error' },
}

function time(ts: string | null): string {
  if (!ts) return ''
  try { return new Date(ts).toLocaleTimeString() } catch { return '' }
}

export function MessageCard({ msg }: { msg: Msg }) {
  const s = STYLE[msg.type] ?? { badge: 'text-zinc-300 border-zinc-600/50 bg-zinc-800/40', bar: 'bg-zinc-500/70', label: msg.type }
  return (
    <div className="animate-rise relative overflow-hidden rounded-xl border border-[#212b40] bg-[#111726] px-3.5 py-3 transition-colors hover:border-[#2c3a57]">
      <span className={`absolute inset-y-0 left-0 w-[3px] ${s.bar}`} />
      <div className="mb-1.5 flex items-center gap-2 text-[11px] text-[#7d8aa3]">
        <span className="font-semibold text-[#d6def0]">{msg.sender}</span>
        <span className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${s.badge}`}>{s.label}</span>
        <span className="ml-auto tabular-nums">{time(msg.ts)}</span>
      </div>
      <div className="whitespace-pre-wrap text-[13px] leading-relaxed text-[#e6e6e6]">{msg.content}</div>
      {msg.mentions.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {msg.mentions.map((m, i) => (
            <span key={i} className="rounded-md border border-sky-800/60 bg-sky-950/40 px-1.5 py-0.5 text-[10px] text-sky-300">@{m}</span>
          ))}
        </div>
      )}
    </div>
  )
}
