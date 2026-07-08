<script setup lang="ts">
import { ref, watch, nextTick, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { useAssistantStore } from '../stores/assistant'

const router = useRouter()
const store = useAssistantStore()

const inputMessage = ref('')
const messagesContainer = ref<HTMLElement | null>(null)

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
  "What's the lifecycle state of stp02810?",
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
        <p>AI assistant for parts, BOMs, and files</p>
      </div>
      <div class="header-actions">
        <button
          class="clear-btn"
          @click="store.clear()"
          :disabled="!store.hasMessages || store.isStreaming"
        >
          <i class="pi pi-trash"></i>
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
        <p>Ask about parts, assemblies, BOMs, or request file downloads.</p>

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

      <!-- Input area -->
      <div class="chat-input">
        <textarea
          v-model="inputMessage"
          @keydown="handleKeydown"
          placeholder="Ask about parts, BOMs, or files..."
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
</style>
