import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
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
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

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
      inputRef.current?.focus()
    }
  }

  return (
    <div className="chat">
      <h1>Cadre AI Chat</h1>
      <div className="messages">
        {messages.map((message, index) => (
          <div key={index} className={`message ${message.role}`}>
            {message.role === 'user' ? (
              message.text
            ) : (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.text}</ReactMarkdown>
            )}
          </div>
        ))}
        {loading && (
          <div className="message assistant loading" aria-live="polite">
            Thinking…
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <form onSubmit={sendMessage}>
        <input
          ref={inputRef}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Type a message..."
          disabled={loading}
        />
        <button type="submit" disabled={loading}>
          Send
        </button>
      </form>
    </div>
  )
}

export default App
