import type { Msg } from '../types'

const STYLE: Record<string, { badge: string; bar: string; label: string }> = {
  text: { badge: 'text-pine border-pine/30 bg-pine/8', bar: 'bg-pine', label: 'message' },
  thought: { badge: 'text-coral border-coral/30 bg-coral/10', bar: 'bg-coral', label: 'private · audit' },
  tool_call: { badge: 'text-ink-soft border-line bg-sunk', bar: 'bg-ink-soft', label: 'tool call' },
  tool_result: { badge: 'text-ink-soft border-line bg-sunk', bar: 'bg-ink-soft', label: 'tool result' },
  error: { badge: 'text-red-600 border-red-300 bg-red-50', bar: 'bg-red-500', label: 'error' },
}

function time(ts: string | null): string {
  if (!ts) return ''
  try { return new Date(ts).toLocaleTimeString() } catch { return '' }
}

export function MessageCard({ msg }: { msg: Msg }) {
  const s = STYLE[msg.type] ?? { badge: 'text-ink-soft border-line bg-sunk', bar: 'bg-ink-faint', label: msg.type }
  return (
    <div className="animate-rise relative overflow-hidden rounded-xl border border-line bg-paper px-3.5 py-3 transition-colors hover:border-ink/25">
      <span className={`absolute inset-y-0 left-0 w-[3px] ${s.bar}`} />
      <div className="mb-1.5 flex items-center gap-2 text-[11px] text-ink-faint">
        <span className="font-semibold text-ink">{msg.sender}</span>
        <span className={`rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide ${s.badge}`}>{s.label}</span>
        <span className="ml-auto font-mono tabular-nums">{time(msg.ts)}</span>
      </div>
      <div className="whitespace-pre-wrap text-[13px] leading-relaxed text-ink">{msg.content}</div>
      {msg.mentions.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {msg.mentions.map((m, i) => (
            <span key={i} className="rounded-md border border-pine/30 bg-pine/8 px-1.5 py-0.5 font-mono text-[10px] text-pine">@{m}</span>
          ))}
        </div>
      )}
    </div>
  )
}
