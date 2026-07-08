<script setup lang="ts">
import { ref, watch, nextTick, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { useAssistantStore } from '../stores/assistant'

const router = useRouter()
const route = useRoute()
const store = useAssistantStore()

const inputMessage = ref('')
const messagesContainer = ref<HTMLElement | null>(null)
const showHistory = ref(false)

async function toggleHistory() {
  showHistory.value = !showHistory.value
  if (showHistory.value) {
    await store.loadConversations()
  }
}

async function openConversation(id: string) {
  showHistory.value = false
  await store.loadConversation(id)
}

function formatConversationDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

// Configure marked for safe rendering
marked.setOptions({
  breaks: true,
  gfm: true,
})

// Configure DOMPurify to allow target="_blank" on links
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank')
    node.setAttribute('rel', 'noopener noreferrer')
  }
})

const suggestedPrompts = [
  'How many parts are in assembly csa00010?',
  'Pull me the print of csp00200',
  'What projects are due soon?',
  'What does project WM2121 cost?',
  'Are there any failed tasks in the work queue?',
  'Where is csp00100 used?',
]

function renderMarkdown(content: string): string {
  if (!content) return ''
  const html = marked.parse(content) as string
  return DOMPurify.sanitize(html)
}

async function sendMessage() {
  if (!inputMessage.value.trim() || store.isStreaming) return

  const message = inputMessage.value
  inputMessage.value = ''
  await store.sendMessage(message)
}

function useSuggestion(prompt: string) {
  inputMessage.value = prompt
  sendMessage()
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

// Auto-scroll to bottom when messages change
watch(
  () => store.messages.length,
  () => {
    nextTick(() => {
      if (messagesContainer.value) {
        messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
      }
    })
  }
)

// Also scroll when streaming text arrives
watch(
  () => store.messages[store.messages.length - 1]?.content,
  () => {
    nextTick(() => {
      if (messagesContainer.value) {
        messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
      }
    })
  }
)

onMounted(() => {
  // Page context: opened from a project or item page (e.g. ?project=WM2121)
  const project = route.query.project as string | undefined
  const item = route.query.item as string | undefined
  if (project) {
    store.pageContext = `The user opened the assistant from MRP project ${project}.`
  } else if (item) {
    store.pageContext = `The user opened the assistant from item ${item}.`
  } else {
    store.pageContext = null
  }

  // Focus input on mount
  const input = document.querySelector('.chat-input textarea') as HTMLTextAreaElement
  if (input) input.focus()
})
</script>

<template>
  <div class="assistant-view">
    <header class="assistant-header">
      <button class="back-btn" @click="router.push('/mrp/dashboard')">
        <i class="pi pi-arrow-left"></i>
        Dashboard
      </button>
      <div class="header-info">
        <h1>
          <i class="pi pi-comments"></i>
          Ask PDM
        </h1>
        <p>AI assistant for parts, BOMs, files, projects, and costs</p>
      </div>
      <div class="header-actions">
        <div class="history-wrapper">
          <button class="clear-btn" @click="toggleHistory" :disabled="store.isStreaming">
            <i class="pi pi-history"></i>
            History
          </button>
          <div v-if="showHistory" class="history-dropdown">
            <div v-if="!store.conversations.length" class="history-empty">
              No saved conversations
            </div>
            <button
              v-for="conv in store.conversations"
              :key="conv.id"
              class="history-item"
              @click="openConversation(conv.id)"
            >
              <span class="history-title">{{ conv.title || 'Untitled conversation' }}</span>
              <span class="history-date">{{ formatConversationDate(conv.updated_at) }}</span>
            </button>
          </div>
        </div>
        <button
          class="clear-btn"
          @click="store.newChat()"
          :disabled="!store.hasMessages || store.isStreaming"
        >
          <i class="pi pi-plus"></i>
          New Chat
        </button>
      </div>
    </header>

    <div class="chat-container">
      <!-- Empty state with suggestions -->
      <div v-if="!store.hasMessages" class="empty-state">
        <div class="welcome-icon">
          <i class="pi pi-sparkles"></i>
        </div>
        <h2>What can I help you find?</h2>
        <p>Ask about parts, BOMs, files, project timelines, costs, or shop tasks.</p>

        <div class="suggestions">
          <button
            v-for="prompt in suggestedPrompts"
            :key="prompt"
            class="suggestion-btn"
            @click="useSuggestion(prompt)"
          >
            {{ prompt }}
          </button>
        </div>
      </div>

      <!-- Messages -->
      <div v-else ref="messagesContainer" class="messages">
        <div
          v-for="message in store.messages"
          :key="message.id"
          class="message"
          :class="message.role"
        >
          <div class="message-avatar">
            <i v-if="message.role === 'user'" class="pi pi-user"></i>
            <i v-else class="pi pi-sparkles"></i>
          </div>
          <div class="message-content">
            <div v-if="message.role === 'user'" class="user-text">
              {{ message.content }}
            </div>
            <div
              v-else
              class="assistant-text"
              v-html="renderMarkdown(message.content)"
            ></div>

            <!-- Proposed write actions (require approval) -->
            <div
              v-for="action in message.actions"
              :key="action.id"
              class="action-card"
              :class="action.status"
            >
              <div class="action-header">
                <i class="pi pi-shield"></i>
                <span>Proposed change</span>
              </div>
              <div class="action-description">{{ action.description }}</div>
              <div v-if="action.status === 'pending'" class="action-buttons">
                <button class="action-approve" @click="store.respondAction(action.id, true)">
                  <i class="pi pi-check"></i> Approve
                </button>
                <button class="action-decline" @click="store.respondAction(action.id, false)">
                  <i class="pi pi-times"></i> Decline
                </button>
              </div>
              <div v-else class="action-result">
                <template v-if="action.status === 'approved'">
                  <i class="pi pi-check-circle"></i> Approved &mdash; {{ action.result || 'executed' }}
                </template>
                <template v-else-if="action.status === 'declined'">
                  <i class="pi pi-ban"></i> Declined
                </template>
                <template v-else>
                  <i class="pi pi-exclamation-triangle"></i> {{ action.result || 'Failed' }}
                </template>
              </div>
            </div>

            <!-- Tool status indicator -->
            <div v-if="message.toolStatus" class="tool-status">
              <i class="pi pi-spin pi-spinner"></i>
              {{ message.toolStatus }}
            </div>

            <!-- Loading indicator for empty streaming message -->
            <div
              v-if="message.role === 'assistant' && !message.content && store.isStreaming && !message.toolStatus"
              class="typing-indicator"
            >
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        </div>
      </div>

      <!-- Error display -->
      <div v-if="store.error" class="error-banner">
        <i class="pi pi-exclamation-triangle"></i>
        {{ store.error }}
      </div>

      <!-- Page context chip -->
      <div v-if="store.pageContext" class="context-chip">
        <i class="pi pi-map-marker"></i>
        {{ store.pageContext }}
      </div>

      <!-- Input area -->
      <div class="chat-input">
        <textarea
          v-model="inputMessage"
          @keydown="handleKeydown"
          placeholder="Ask about parts, BOMs, files, projects, or costs..."
          :disabled="store.isStreaming"
          rows="1"
        ></textarea>
        <button
          class="send-btn"
          @click="sendMessage"
          :disabled="!inputMessage.trim() || store.isStreaming"
        >
          <i v-if="store.isStreaming" class="pi pi-spin pi-spinner"></i>
          <i v-else class="pi pi-send"></i>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
* { box-sizing: border-box; }

.assistant-view {
  min-height: 100vh;
  background: #020617;
  color: #e5e7eb;
  font-family: system-ui, sans-serif;
  display: flex;
  flex-direction: column;
}

.assistant-header {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding: 1rem 1.5rem;
  background: #0f172a;
  border-bottom: 1px solid #1e293b;
}

.header-info {
  flex: 1;
}

.header-info h1 {
  margin: 0;
  font-size: 1.5rem;
  color: #fff;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.header-info h1 i {
  color: #38bdf8;
}

.header-info p {
  margin: 0.25rem 0 0 0;
  color: #9ca3af;
  font-size: 0.875rem;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: #374151;
  border: none;
  color: #e5e7eb;
  padding: 0.75rem 1.25rem;
  border-radius: 0.5rem;
  cursor: pointer;
  font-size: 0.9rem;
}

.back-btn:hover {
  background: #4b5563;
}

.header-actions {
  display: flex;
  gap: 0.75rem;
}

.clear-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: #374151;
  border: none;
  color: #e5e7eb;
  padding: 0.75rem 1.25rem;
  border-radius: 0.5rem;
  cursor: pointer;
  font-size: 0.875rem;
}

.clear-btn:hover:not(:disabled) {
  background: #4b5563;
}

.clear-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Chat container */
.chat-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  max-width: 900px;
  width: 100%;
  margin: 0 auto;
  padding: 1.5rem;
}

/* Empty state */
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 2rem;
}

.welcome-icon {
  width: 80px;
  height: 80px;
  background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 1.5rem;
  border: 2px solid #38bdf8;
}

.welcome-icon i {
  font-size: 2.5rem;
  color: #38bdf8;
}

.empty-state h2 {
  margin: 0 0 0.5rem 0;
  font-size: 1.5rem;
  color: #fff;
}

.empty-state p {
  margin: 0 0 2rem 0;
  color: #9ca3af;
}

.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  justify-content: center;
  max-width: 600px;
}

.suggestion-btn {
  background: #1e293b;
  border: 1px solid #334155;
  color: #e5e7eb;
  padding: 0.75rem 1.25rem;
  border-radius: 2rem;
  cursor: pointer;
  font-size: 0.875rem;
  transition: all 0.15s;
}

.suggestion-btn:hover {
  background: #334155;
  border-color: #38bdf8;
}

/* Messages */
.messages {
  flex: 1;
  overflow-y: auto;
  padding-bottom: 1rem;
}

.messages::-webkit-scrollbar { width: 8px; }
.messages::-webkit-scrollbar-track { background: #0f172a; }
.messages::-webkit-scrollbar-thumb { background: #374151; border-radius: 4px; }
.messages::-webkit-scrollbar-thumb:hover { background: #4b5563; }

.message {
  display: flex;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.message.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.message.user .message-avatar {
  background: #374151;
}

.message.assistant .message-avatar {
  background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
  border: 1px solid #38bdf8;
}

.message.assistant .message-avatar i {
  color: #38bdf8;
}

.message-content {
  flex: 1;
  max-width: 80%;
}

.message.user .message-content {
  text-align: right;
}

.user-text {
  display: inline-block;
  background: #2563eb;
  color: #fff;
  padding: 0.75rem 1rem;
  border-radius: 1rem 1rem 0 1rem;
  font-size: 0.95rem;
  text-align: left;
}

.assistant-text {
  background: #1e293b;
  padding: 1rem;
  border-radius: 0 1rem 1rem 1rem;
  font-size: 0.95rem;
  line-height: 1.6;
}

/* Markdown content styling */
.assistant-text :deep(p) {
  margin: 0 0 0.75rem 0;
}

.assistant-text :deep(p:last-child) {
  margin-bottom: 0;
}

.assistant-text :deep(code) {
  background: #0f172a;
  padding: 0.15rem 0.4rem;
  border-radius: 0.25rem;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 0.875em;
  color: #38bdf8;
}

.assistant-text :deep(pre) {
  background: #0f172a;
  padding: 1rem;
  border-radius: 0.5rem;
  overflow-x: auto;
  margin: 0.75rem 0;
}

.assistant-text :deep(pre code) {
  background: none;
  padding: 0;
}

.assistant-text :deep(a) {
  color: #38bdf8;
  text-decoration: none;
}

.assistant-text :deep(a:hover) {
  text-decoration: underline;
}

.assistant-text :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 0.75rem 0;
  font-size: 0.875rem;
}

.assistant-text :deep(th),
.assistant-text :deep(td) {
  padding: 0.5rem 0.75rem;
  border: 1px solid #334155;
  text-align: left;
}

.assistant-text :deep(th) {
  background: #0f172a;
  font-weight: 600;
}

.assistant-text :deep(ul),
.assistant-text :deep(ol) {
  margin: 0.5rem 0;
  padding-left: 1.5rem;
}

.assistant-text :deep(li) {
  margin: 0.25rem 0;
}

/* Tool status */
.tool-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.75rem;
  padding: 0.5rem 0.75rem;
  background: #0f172a;
  border-radius: 0.5rem;
  color: #9ca3af;
  font-size: 0.875rem;
}

.tool-status i {
  color: #38bdf8;
}

/* Typing indicator */
.typing-indicator {
  display: flex;
  gap: 0.25rem;
  padding: 0.5rem 0;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  background: #38bdf8;
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out;
}

.typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
.typing-indicator span:nth-child(2) { animation-delay: -0.16s; }

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

/* Error banner */
.error-banner {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  background: #7f1d1d;
  border-radius: 0.5rem;
  color: #fca5a5;
  margin-bottom: 1rem;
}

/* Chat input */
.chat-input {
  display: flex;
  gap: 0.75rem;
  padding: 1rem;
  background: #0f172a;
  border-radius: 1rem;
  border: 1px solid #1e293b;
}

.chat-input textarea {
  flex: 1;
  background: transparent;
  border: none;
  color: #e5e7eb;
  font-size: 1rem;
  font-family: inherit;
  resize: none;
  outline: none;
  padding: 0.5rem;
  min-height: 24px;
  max-height: 120px;
}

.chat-input textarea::placeholder {
  color: #6b7280;
}

.send-btn {
  width: 44px;
  height: 44px;
  background: #2563eb;
  border: none;
  border-radius: 0.75rem;
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}

.send-btn:hover:not(:disabled) {
  background: #1d4ed8;
}

.send-btn:disabled {
  background: #374151;
  cursor: not-allowed;
}

.send-btn i {
  font-size: 1.1rem;
}

/* --- Action approval cards --- */
.action-card {
  margin-top: 0.75rem;
  padding: 0.75rem 1rem;
  background: #0f172a;
  border: 1px solid #334155;
  border-left: 3px solid #f59e0b;
  border-radius: 8px;
}

.action-card.approved {
  border-left-color: #22c55e;
}

.action-card.declined,
.action-card.error {
  border-left-color: #ef4444;
  opacity: 0.85;
}

.action-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #94a3b8;
  margin-bottom: 0.35rem;
}

.action-description {
  font-size: 0.95rem;
  color: #e5e7eb;
  margin-bottom: 0.6rem;
}

.action-buttons {
  display: flex;
  gap: 0.5rem;
}

.action-approve,
.action-decline {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.35rem 0.9rem;
  border-radius: 6px;
  border: 1px solid transparent;
  font-size: 0.85rem;
  cursor: pointer;
}

.action-approve {
  background: #16a34a;
  color: #fff;
}

.action-approve:hover {
  background: #15803d;
}

.action-decline {
  background: transparent;
  border-color: #475569;
  color: #cbd5e1;
}

.action-decline:hover {
  border-color: #ef4444;
  color: #ef4444;
}

.action-result {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
  color: #94a3b8;
}

.action-card.approved .action-result {
  color: #4ade80;
}

/* --- Conversation history dropdown --- */
.header-actions {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.history-wrapper {
  position: relative;
}

.history-dropdown {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  width: 340px;
  max-height: 380px;
  overflow-y: auto;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 8px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
  z-index: 50;
  padding: 0.35rem;
}

.history-empty {
  padding: 1rem;
  font-size: 0.85rem;
  color: #64748b;
  text-align: center;
}

.history-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.15rem;
  width: 100%;
  padding: 0.5rem 0.65rem;
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  text-align: left;
}

.history-item:hover {
  background: #1e293b;
}

.history-title {
  font-size: 0.85rem;
  color: #e5e7eb;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.history-date {
  font-size: 0.7rem;
  color: #64748b;
}

/* --- Page context chip --- */
.context-chip {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0 auto;
  max-width: 800px;
  width: 100%;
  padding: 0.3rem 0.75rem;
  font-size: 0.75rem;
  color: #94a3b8;
}
</style>
