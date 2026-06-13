import { useEffect, useState } from 'react'
import type { RoomState } from './types'

/**
 * Subscribe to a Band room's live state.
 *
 * Transport with graceful degradation: HTTP polling of `/api/state` is the reliable
 * baseline (works through any plain reverse proxy / port-forward), and a WebSocket
 * (`/ws`) is an optional upgrade for true push. If the socket connects and delivers a
 * frame we drive off it and pause polling; if it's blocked (some port-forwards reject
 * the upgrade) we just keep polling. Either way the UI stays live.
 */
export function useRoomStream(room: string) {
  const [state, setState] = useState<RoomState | null>(null)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    if (!room) return
    let closed = false
    let usingWs = false
    let ws: WebSocket | null = null

    const poll = async () => {
      if (closed || usingWs) return
      try {
        const r = await fetch(`/api/state?room=${encodeURIComponent(room)}`)
        const d = (await r.json()) as RoomState
        if (!closed && !usingWs) { setState(d); setConnected(true) }
      } catch {
        if (!closed && !usingWs) setConnected(false)
      }
    }

    poll()
    const timer = setInterval(poll, 2500)

    try {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/ws?room=${encodeURIComponent(room)}`)
      ws.onmessage = (e) => {
        try {
          const d = JSON.parse(e.data) as RoomState
          usingWs = true
          setState(d)
          setConnected(true)
        } catch { /* ignore malformed frame */ }
      }
      ws.onclose = () => { usingWs = false }
      ws.onerror = () => { /* non-fatal: polling carries the UI */ }
    } catch { /* WebSocket unavailable: polling carries the UI */ }

    return () => {
      closed = true
      clearInterval(timer)
      ws?.close()
    }
  }, [room])

  return { state, connected }
}
