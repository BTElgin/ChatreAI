import { useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

interface Message {
  role: 'user' | 'assistant' | 'error'
  text: string
}

const REQUEST_TIMEOUT_MS = 30000
const FAILURE_MESSAGE =
  "Something went wrong reaching Cadre AI. Please try again in a moment, or book a call with a strategist directly."

function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)

  async function sendMessage(event: FormEvent) {
    event.preventDefault()
    const text = input.trim()
    if (!text || loading) return

    setMessages((prev) => [...prev, { role: 'user', text }])
    setInput('')
    setLoading(true)

    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
        signal: controller.signal,
      })
      if (!response.ok) throw new Error(`Request failed (${response.status})`)
      const data = await response.json()
      setMessages((prev) => [...prev, { role: 'assistant', text: data.message }])
    } catch {
      setMessages((prev) => [...prev, { role: 'error', text: FAILURE_MESSAGE }])
    } finally {
      clearTimeout(timeout)
      setLoading(false)
    }
  }

  return (
    <div className="chat">
      <h1>Cadre AI Chat</h1>
      <div className="messages">
        {messages.map((message, index) => (
          <div key={index} className={`message ${message.role}`}>
            {message.text}
          </div>
        ))}
      </div>
      <form onSubmit={sendMessage}>
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Type a message..."
        />
        <button type="submit" disabled={loading}>
          Send
        </button>
      </form>
    </div>
  )
}

export default App
