/**
 * AI Assistant API client - SSE streaming for chat.
 *
 * Uses fetch with ReadableStream since EventSource doesn't support POST bodies.
 */

export interface SSEEvent {
  event: 'start' | 'text' | 'tool' | 'done' | 'error'
  data: {
    conversation_id?: string
    delta?: string
    name?: string
    summary?: string
    message?: string
  }
}

export interface ChatCallbacks {
  onStart?: (conversationId: string) => void
  onText?: (delta: string) => void
  onTool?: (name: string, summary: string) => void
  onDone?: () => void
  onError?: (message: string) => void
}

/**
 * Send a chat message and stream the response.
 *
 * @param message - The user's message
 * @param conversationId - Optional existing conversation ID
 * @param callbacks - Event callbacks for streaming updates
 * @returns Promise that resolves when stream completes
 */
export async function sendChatMessage(
  message: string,
  conversationId: string | null,
  callbacks: ChatCallbacks
): Promise<void> {
  const response = await fetch('/api/assistant/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      conversation_id: conversationId,
      message,
    }),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  if (!response.body) {
    throw new Error('No response body')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()

      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // Process complete SSE events
      const lines = buffer.split('\n')
      buffer = lines.pop() || '' // Keep incomplete line in buffer

      let currentEvent = ''
      let currentData = ''

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          currentData = line.slice(6)
        } else if (line === '' && currentEvent && currentData) {
          // Empty line = end of event
          try {
            const parsed = JSON.parse(currentData) as SSEEvent['data']

            switch (currentEvent) {
              case 'start':
                if (parsed.conversation_id && callbacks.onStart) {
                  callbacks.onStart(parsed.conversation_id)
                }
                break
              case 'text':
                if (parsed.delta && callbacks.onText) {
                  callbacks.onText(parsed.delta)
                }
                break
              case 'tool':
                if (parsed.name && parsed.summary && callbacks.onTool) {
                  callbacks.onTool(parsed.name, parsed.summary)
                }
                break
              case 'done':
                if (callbacks.onDone) {
                  callbacks.onDone()
                }
                break
              case 'error':
                if (parsed.message && callbacks.onError) {
                  callbacks.onError(parsed.message)
                }
                break
            }
          } catch (e) {
            console.warn('Failed to parse SSE data:', currentData, e)
          }

          currentEvent = ''
          currentData = ''
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

/**
 * Clear a conversation from the server.
 */
export async function clearConversation(conversationId: string): Promise<void> {
  await fetch(`/api/assistant/chat/${conversationId}`, {
    method: 'DELETE',
  })
}
