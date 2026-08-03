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
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [starterPrompts, setStarterPrompts] = useState<string[]>([])
  const [suggestions, setSuggestions] = useState<string[]>([])
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  useEffect(() => {
    fetch('/api/config')
      .then((response) => response.json())
      .then((data) => {
        setStarterPrompts(data.starterPrompts ?? [])
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  async function sendMessage(event: FormEvent | null, overrideText?: string) {
    event?.preventDefault()
    const text = (overrideText ?? input).trim()
    if (!text || loading) return

    const outgoing = [...messages, { role: 'user' as const, text }]
    setMessages(outgoing)
    setInput('')
    setSuggestions([])
    setLoading(true)

    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: outgoing.filter((m) => m.role !== 'error') }),
        signal: controller.signal,
      })
      if (!response.ok) throw new Error(`Request failed (${response.status})`)
      const data = await response.json()
      setMessages((prev) => [...prev, { role: 'assistant', text: data.message }])
      setSuggestions(data.suggestions ?? [])
    } catch {
      setMessages((prev) => [...prev, { role: 'error', text: FAILURE_MESSAGE }])
    } finally {
      clearTimeout(timeout)
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  const chips = messages.length === 0 ? starterPrompts : suggestions
  const showChips = chips.length > 0 && !loading

  return (
    <>
      {!open && (
        <div className="backdrop-hint">
          <p>Chat widget preview — click the bubble to start a conversation with Cadre AI.</p>
        </div>
      )}

      {open && (
        <div className="chat" role="dialog" aria-label="Cadre AI Chat">
          <header className="chat-header">
            <h1>
              Cadre AI <span className="accent">Chat</span>
            </h1>
            <button type="button" className="close-btn" onClick={() => setOpen(false)} aria-label="Close chat">
              ×
            </button>
          </header>
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
                Typing…
              </div>
            )}
            <div ref={bottomRef} />
          </div>
          {showChips && (
            <div className="chip-row" aria-label="Suggested questions">
              {chips.map((chip) => (
                <button key={chip} type="button" className="chip" onClick={() => sendMessage(null, chip)}>
                  {chip}
                </button>
              ))}
            </div>
          )}
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
      )}

      {!open && (
        <button type="button" className="launcher" onClick={() => setOpen(true)} aria-label="Open chat with Cadre AI">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <rect x="3" y="4" width="18" height="13" rx="4" fill="currentColor" />
            <path d="M8 17v4l5-4H8Z" fill="currentColor" />
          </svg>
        </button>
      )}
    </>
  )
}

export default App
