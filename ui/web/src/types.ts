export type MessageType = 'text' | 'thought' | 'tool_call' | 'tool_result' | 'error' | string

export interface Msg {
  id: string
  type: MessageType
  sender: string
  content: string
  mentions: string[]
  ts: string | null
}

export interface Side {
  label: string
  prefix: string
  items?: Msg[]
  error?: string
}

export interface RoomState {
  room: string
  sides: Side[]
}
