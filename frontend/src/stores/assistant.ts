import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  sendChatMessage,
  clearConversation,
  respondToAction,
  listConversations,
  getConversationMessages,
  type ActionProposal,
  type ConversationSummary,
} from '../services/assistantApi'

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  toolStatus?: string  // Shows "Looking up..." status during tool execution
  actions?: ActionProposal[]  // Proposed write actions awaiting approval
}

export const useAssistantStore = defineStore('assistant', () => {
  const messages = ref<Message[]>([])
  const conversationId = ref<string | null>(null)
  const isStreaming = ref(false)
  const error = ref<string | null>(null)
  const currentToolStatus = ref<string | null>(null)
  const pageContext = ref<string | null>(null)
  const conversations = ref<ConversationSummary[]>([])

  const hasMessages = computed(() => messages.value.length > 0)

  function generateId(): string {
    return Date.now().toString(36) + Math.random().toString(36).slice(2)
  }

  async function sendMessage(content: string): Promise<void> {
    if (isStreaming.value || !content.trim()) return

    error.value = null
    isStreaming.value = true
    currentToolStatus.value = null

    // Add user message
    const userMessage: Message = {
      id: generateId(),
      role: 'user',
      content: content.trim(),
      timestamp: new Date(),
    }
    messages.value.push(userMessage)

    // Add placeholder for assistant response
    const assistantMessage: Message = {
      id: generateId(),
      role: 'assistant',
      content: '',
      timestamp: new Date(),
    }
    messages.value.push(assistantMessage)

    try {
      await sendChatMessage(content.trim(), conversationId.value, {
        onStart: (convId) => {
          conversationId.value = convId
        },
        onText: (delta) => {
          // Append to the last assistant message
          const lastMsg = messages.value[messages.value.length - 1]
          if (lastMsg && lastMsg.role === 'assistant') {
            lastMsg.content += delta
            currentToolStatus.value = null  // Clear tool status when text arrives
          }
        },
        onTool: (_name, summary) => {
          currentToolStatus.value = summary
          // Update the assistant message to show tool status
          const lastMsg = messages.value[messages.value.length - 1]
          if (lastMsg && lastMsg.role === 'assistant') {
            lastMsg.toolStatus = summary
          }
        },
        onAction: (actionId, name, description, params) => {
          // Attach the proposal to the current assistant message
          const lastMsg = messages.value[messages.value.length - 1]
          if (lastMsg && lastMsg.role === 'assistant') {
            if (!lastMsg.actions) lastMsg.actions = []
            lastMsg.actions.push({
              id: actionId,
              name,
              description,
              params,
              status: 'pending',
            })
          }
        },
        onDone: () => {
          currentToolStatus.value = null
          const lastMsg = messages.value[messages.value.length - 1]
          if (lastMsg) {
            lastMsg.toolStatus = undefined
          }
        },
        onError: (message) => {
          error.value = message
          currentToolStatus.value = null
        },
      }, pageContext.value)
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to send message'
      // Remove empty assistant message on error
      const lastMsg = messages.value[messages.value.length - 1]
      if (lastMsg && lastMsg.role === 'assistant' && !lastMsg.content) {
        messages.value.pop()
      }
    } finally {
      isStreaming.value = false
      currentToolStatus.value = null
    }
  }

  async function respondAction(actionId: string, approve: boolean): Promise<void> {
    // Find the proposal across messages
    let proposal: ActionProposal | undefined
    for (const msg of messages.value) {
      proposal = msg.actions?.find((a) => a.id === actionId)
      if (proposal) break
    }
    if (!proposal || proposal.status !== 'pending') return

    try {
      const response = await respondToAction(actionId, approve)
      proposal.status = response.approved ? 'approved' : 'declined'
      const result = response.result || {}
      if (result.error) {
        proposal.status = 'error'
        proposal.result = String(result.error)
      } else if (response.approved) {
        proposal.result = 'Done'
      }
    } catch (e) {
      proposal.status = 'error'
      proposal.result = e instanceof Error ? e.message : 'Request failed'
    }
  }

  async function loadConversations(): Promise<void> {
    try {
      conversations.value = await listConversations()
    } catch (e) {
      console.warn('Failed to load conversations:', e)
      conversations.value = []
    }
  }

  async function loadConversation(id: string): Promise<void> {
    if (isStreaming.value) return
    try {
      const past = await getConversationMessages(id)
      messages.value = past.map((m) => ({
        id: generateId(),
        role: m.role,
        content: m.content,
        timestamp: new Date(m.created_at),
      }))
      conversationId.value = id
      error.value = null
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load conversation'
    }
  }

  async function clear(): Promise<void> {
    if (conversationId.value) {
      try {
        await clearConversation(conversationId.value)
      } catch (e) {
        console.warn('Failed to clear conversation on server:', e)
      }
    }
    messages.value = []
    conversationId.value = null
    error.value = null
    currentToolStatus.value = null
  }

  /** Start a fresh thread locally without deleting the old one from history. */
  function newChat(): void {
    messages.value = []
    conversationId.value = null
    error.value = null
    currentToolStatus.value = null
  }

  return {
    messages,
    conversationId,
    isStreaming,
    error,
    currentToolStatus,
    pageContext,
    conversations,
    hasMessages,
    sendMessage,
    respondAction,
    loadConversations,
    loadConversation,
    clear,
    newChat,
  }
})
