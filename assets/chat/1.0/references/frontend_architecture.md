# Frontend Architecture Reference

## ChatInterface.vue - Universal Chat Component

### Props

```typescript
interface Props {
  messages: ChatMessage[]           // Initial messages (usually empty, populated via streaming)
  loading?: boolean                 // Show loading state
  hasData?: boolean                 // Whether data is available
  placeholder?: string              // Placeholder when no data
  emptyMessage?: string             // Message when chat is empty
  inputPlaceholder?: string         // Input field placeholder
  disabled?: boolean                // Disable input
  waitingMessage?: string           // Message shown while AI is thinking
  error?: string                    // Error message to display

  // Unified stream identification
  domainType?: string              // 'session', 'spec_full', 'pull_request', 'techdoc', 'prototype', 'tasks'
  domainId?: string | null         // session_id, spec_hash, pr_hash, etc.
}
```

### Events Emitted

```typescript
emit('stop')                      // User clicked stop button
emit('session-updated', sessionId) // Session data changed, trigger refresh
emit('spec-updated', specHash)    // Spec data changed, trigger refresh
emit('evaluation-complete')       // Evaluation completed, trigger refresh
```

### Key Features

1. **Universal Streaming**: Connects to `/api/streams/{stream_id}/stream/` for event streaming
2. **Message Queue**: Delays system messages by 500ms for smooth UX
3. **Auto-scroll**: Tracks user scroll position, auto-scrolls only when near bottom
4. **File Autocomplete**: @ mention support for file references
5. **File Uploads**: Supports multiple file attachments via ChatInputWithUpload
6. **Tool Results**: Expandable/collapsible tool result displays with streaming support
7. **Waiting Indicator**: Shows "Waiting for AI response..." with stop button

### Stream ID Format

Stream ID = `{domainType}_{domainId}`

Examples:
- `session_abc123` - Session chat
- `spec_full_xyz789` - Spec orchestration chat
- `pr_123` - Pull request evaluation chat
- `techdoc_456` - TechDoc generation chat
- `prototype_789` - Prototype generation chat
- `tasks_abc` - Tasks breakdown chat

## Wrapper Component Pattern

### Minimal Wrapper Example

```vue
<script setup lang="ts">
const props = defineProps<{
  myDomainId: string | null
  myDomainData: any
}>()

const emit = defineEmits<{
  'domain-updated': [id: string]
}>()

const chatInterfaceRef = ref()

function handleDomainUpdated(id: string) {
  emit('domain-updated', id)
}

function stopLLM() {
  // ChatInterface handles stopping internally
  console.log('Stop requested for', props.myDomainId)
}

defineExpose({
  clearMessages: () => chatInterfaceRef.value?.clearMessages(),
})
</script>

<template>
  <div class="right-pane">
    <IssuesChatInterface
      ref="chatInterfaceRef"
      :messages="[]"
      domain-type="my_domain"
      :domain-id="myDomainId"
      :has-data="!!myDomainId"
      placeholder="Select an item to view chat."
      empty-message="No chat yet."
      input-placeholder="Type a message..."
      :disabled="!myDomainId"
      waiting-message="Waiting for AI response..."
      @stop="stopLLM"
      @session-updated="handleDomainUpdated"
    />
  </div>
</template>
```

### Custom Input Slot Example

For specialized inputs (e.g., image uploads for prototypes):

```vue
<IssuesChatInterface
  ref="chatInterfaceRef"
  domain-type="session"
  :domain-id="sessionId"
  @stop="stopLLM"
  @session-updated="handleSessionUpdated"
>
  <!-- Custom input for prototype sessions with image upload -->
  <template v-if="sessionData?.session_type === 'prototype'" #input>
    <IssuesPrototypeInputWithUpload
      ref="prototypeInputRef"
      v-model="currentMessage"
      input-placeholder="Describe your prototype or upload reference images..."
      :disabled="!sessionId"
      @send="sendCustomMessage"
      @images-changed="onImagesChanged"
    />
  </template>
</IssuesChatInterface>
```

## Event Handling Patterns

### WebSocket Event Processing

ChatInterface subscribes to `$lastWsEvents` via Nuxt plugin:

```typescript
watch($lastWsEvents, (events) => {
  const latestEvent = events[0]
  if (!latestEvent) return

  // Filter events for this stream by object_id
  const currentStreamId = getSessionIdentifier()
  if (!currentStreamId || latestEvent.objectId !== currentStreamId)
    return

  // Handle the event
  handleEvent(latestEvent)
})
```

### Event Types Handled

- `ai` - AI text content (accumulated for streaming)
- `user` - User message
- `system` - System notifications
- `tool_call` - Tool invocation started
- `tool_result` - Tool execution completed
- `tool_streaming` - Streaming tool output (typewriter effect)
- `ai_thinking` - AI started thinking (show waiting indicator)
- `ai_responded` - AI finished responding (hide waiting indicator)
- `ai_waiting` - AI is waiting to process
- `ai_noop` - No operation, end conversation
- `error` - Error occurred
- `plan` - Plan posted
- `evaluation` - Evaluation updated
- `agent_status` - Agent status update

### Message Filtering

ChatInterface filters messages to match backend logic:

```typescript
const skipTypes = [
  'error', 'ai_waiting', 'ai_thinking',
  'ai_responded', 'ai_noop', 'tool_streaming',
  'tool_call', 'ai_transitional'
]
```

System messages with `group_id` are shown (progress messages).
Tool results are always shown.
System prompts (very long user messages with instructions) are filtered out.

## Auto-scroll Behavior

```typescript
// Track if user is near bottom
function isNearBottom(): boolean {
  const distanceFromBottom = scrollHeight - (scrollTop + clientHeight)
  return distanceFromBottom <= 50
}

// Handle user scroll
function handleScroll() {
  autoScrollEnabled.value = isNearBottom()
}

// Auto-scroll when content changes (if enabled)
watch(filteredMessages, () => {
  if (autoScrollEnabled.value) {
    nextTick(() => scrollToBottom())
  }
})
```

## File Autocomplete

Triggered by @ symbol:

```typescript
function onInput() {
  const val = currentMessage.value
  const atIdx = val.lastIndexOf('@')

  if (atIdx !== -1 && (atIdx === 0 || /\s/.test(val[atIdx - 1]))) {
    const textAfterAt = val.slice(atIdx + 1)

    if (!textAfterAt.includes(' ')) {
      fileAutocomplete.value.active = true
      fileAutocomplete.value.query = textAfterAt
      debouncedFetchFileAutocomplete(textAfterAt)
    }
  }
}
```

Fetches results from `/api/issues/autocomplete/files/` with session context.

## Tool Result Display

Streaming tools show typewriter effect:

```typescript
function addTypewriterContent(id: string, newContent: string) {
  const currentBuffer = streamingBuffers.get(id) || ''
  streamingBuffers.set(id, currentBuffer + newContent)
  startTypewriterEffect(id)
}

function startTypewriterEffect(id: string) {
  // Add 3-5 characters at a time every 20ms
  const chunkSize = Math.min(3, buffer.length - currentDisplay.length)
  const nextContent = buffer.slice(0, currentDisplay.length + chunkSize)
  existingMsg.streamingOutput = nextContent

  setTimeout(() => startTypewriterEffect(id), 20)
}
```

## Stop Button Behavior

```typescript
function handleStop() {
  // End conversation for UI feedback
  endConversation('user_stopped')

  // Stop the stream via API
  if (domainType && domainId) {
    stopUniversalOrchestration(domainType, domainId)
  }

  // Emit stop event for parent
  emit('stop')
}
```

Backend API: `POST /api/universal-orchestration/{domainType}/{domainId}/stop/`

## Sub-Orchestrator Streaming (CRITICAL QUIRK)

### The Problem

When a tool is actually a sub-orchestrator (e.g., `generate_prd`, `generate_prototype`, `generate_techdoc`), the progress of that sub-orchestrator needs to display in the UI within the tool result block. This is a common source of confusion.

### The Solution: Streaming Tool Registry

**Location**: ChatInterface.vue

You must register sub-orchestrator tools in the `isStreamingTool()` function:

```typescript
function isStreamingTool(toolName: string): boolean {
  return [
    'related_issues',
    'related_pull_requests',
    'related_code',
    'generate_prd',           // Sub-orchestrator tool
    'generate_prototype',      // Sub-orchestrator tool
    'generate_techdoc',        // Sub-orchestrator tool
    'generate_tasks',          // Sub-orchestrator tool
    'generate_subtasks_from_steps',
    'analyze_task_dependencies',
    'create_sessions_from_subtasks',
  ].includes(toolName)
}
```

**Why This Is Critical**: If you forget to add a sub-orchestrator tool to this list, its streaming output will NOT display in the tool result block, and users won't see the progress.

### How It Works

#### 1. Backend: Tool Implements `call_with_streaming`

```python
class GeneratePRDTool:
    name = "generate_prd"

    async def call_with_streaming(self, org, tool_input, stream_callback):
        """
        Execute PRD generation with streaming output.

        Args:
            stream_callback: Callback for streaming progress chunks
        """
        # Stream progress updates
        stream_callback("Starting PRD generation...\n")
        stream_callback("📋 Extracting context from conversation history...\n")
        stream_callback("📝 Context extracted (1234 chars)\n")

        # Run sub-orchestrator (which streams its own progress)
        result = await generator.generate(
            context_summary=context_summary,
            stream_callback=stream_callback,  # Pass through to sub-orchestrator
        )

        # Return final result
        return result
```

#### 2. Backend: BaseChatOrchestrator Broadcasts Streaming Events

When a tool has `call_with_streaming`, the base orchestrator:

```python
# base.py:1329
has_streaming = hasattr(tool, "call_with_streaming")

if has_streaming and tool_call_id and streamable_object:
    def stream_callback(content: str):
        streaming_event = ToolStreamingEvent(
            tool_call_id=tool_call_id,
            content=content,
            tool=tool_name,
        )
        streaming_queue.append(streaming_event)

    # Execute tool with streaming
    result = await tool.call_with_streaming(org, tool_input, stream_callback)

    # Broadcast streaming events to UI
    for event in streaming_queue:
        await broadcast_event_async(org, stream_id, event, streamable_object, ephemeral=True)
```

#### 3. Frontend: ChatInterface Handles Streaming Events

**Step 1**: When `tool_call` event arrives, create both tool_call and tool_result containers:

```typescript
// ChatInterface.vue:1344
else if (event.type === 'tool_call') {
  // Store tool_call for reference
  internalMessages.value.push({
    type: 'tool_call',
    id: event.tool_call_id,
    tool: event.tool,
    streamingOutput: '',  // Will accumulate streaming content
  })

  // Create tool_result container immediately
  internalMessages.value.push({
    type: 'tool_result',
    id: event.tool_call_id,
    tool: event.tool,
    streamingOutput: '',  // Will populate from streaming events
    expanded: true,       // Start expanded during streaming
  })
}
```

**Step 2**: When `tool_streaming` events arrive, accumulate content with typewriter effect:

```typescript
// ChatInterface.vue:1366
else if (event.type === 'tool_streaming') {
  // Add content to typewriter queue for smooth display
  addTypewriterContent(event.tool_call_id, event.content)
}

function addTypewriterContent(id: string, newContent: string) {
  const currentBuffer = streamingBuffers.get(id) || ''
  streamingBuffers.set(id, currentBuffer + newContent)
  startTypewriterEffect(id)
}

function startTypewriterEffect(id: string) {
  // Find the tool_result message
  const toolResultIndex = internalMessages.value.findIndex(
    msg => msg.type === 'tool_result' && msg.id === id
  )

  const existingMsg = internalMessages.value[toolResultIndex]
  const currentDisplay = existingMsg.streamingOutput || ''
  const buffer = streamingBuffers.get(id)

  // Add 3-5 characters at a time every 20ms
  const chunkSize = Math.min(3, buffer.length - currentDisplay.length)
  const nextContent = buffer.slice(0, currentDisplay.length + chunkSize)
  existingMsg.streamingOutput = nextContent

  setTimeout(() => startTypewriterEffect(id), 20)
}
```

**Step 3**: When `tool_result` event arrives, preserve streaming content and add final result:

```typescript
// ChatInterface.vue:1490
else if (event.type === 'tool_result') {
  const toolResultIndex = internalMessages.value.findIndex(
    msg => msg.type === 'tool_result' && msg.id === event.tool_call_id
  )

  const existingMsg = internalMessages.value[toolResultIndex]
  existingMsg.result = event.result || event.content

  // Preserve accumulated streaming content
  const accumulatedStreamingContent = streamingBuffers.get(event.tool_call_id)
  if (accumulatedStreamingContent) {
    existingMsg.streamingOutput = accumulatedStreamingContent
  }

  // Collapse after completion
  existingMsg.expanded = false
}
```

**Step 4**: Display combined content with separator:

```typescript
// ChatInterface.vue:642
function getCombinedToolContent(toolResultMsg: any): string {
  if (isStreamingTool(toolResultMsg.tool)) {  // ⚠️ MUST be in registry
    if (toolResultMsg.streamingOutput && toolResultMsg.streamingOutput.trim()) {
      const finalResult = toolResultMsg.result || toolResultMsg.content || ''

      // Show streaming output + separator + final result
      if (finalResult && finalResult !== toolResultMsg.streamingOutput) {
        return `${toolResultMsg.streamingOutput}\n\n---\n\n**Final Result:**\n\n${finalResult}`
      }

      // Just streaming output if no separate final result
      return toolResultMsg.streamingOutput
    }
  }

  // For non-streaming tools, return just the result
  return toolResultMsg.result || toolResultMsg.content || ''
}
```

### Adding a New Sub-Orchestrator Tool

**Checklist**:

1. ✅ **Backend**: Implement `call_with_streaming(org, tool_input, stream_callback)` on tool class
2. ✅ **Backend**: Call `stream_callback(content)` for progress updates
3. ✅ **Backend**: Pass `stream_callback` to any sub-orchestrators
4. ✅ **Frontend**: Add tool name to `isStreamingTool()` array in ChatInterface.vue

**Example**:

```typescript
// ChatInterface.vue
function isStreamingTool(toolName: string): boolean {
  return [
    // ... existing tools ...
    'generate_my_new_document',  // ⚠️ DON'T FORGET THIS!
  ].includes(toolName)
}
```

If you forget step 4, the tool will execute successfully but users won't see any streaming progress in the UI!
