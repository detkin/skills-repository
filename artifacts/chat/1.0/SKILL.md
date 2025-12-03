---
name: chat
description: This skill should be used when adding new chat functionality to the application or modifying existing chat behaviors. Use this skill when creating a new domain-specific chat interface (e.g., for Sessions, Specs, Pull Requests), adding new document types to existing chats, or debugging chat-related issues. The skill provides comprehensive patterns for both frontend Vue components and backend Python orchestrators.
---

# Chat System Implementation

## Overview

Add and modify AI-powered chat functionality in the application. The chat system uses a unified architecture with:
- **Frontend**: Universal ChatInterface.vue component for all chat types
- **Backend**: BaseChatOrchestrator abstract class providing 95% of orchestration logic
- **Streaming**: Real-time event broadcasting via Pushpin/WebSocket
- **Tools**: Extensible tool system for LLM capabilities

## When to Use This Skill

Use this skill when:
- **Creating** a new chat for a different kind of domain object (e.g., Tasks, Reports, Deployments)
- **Adding** a new document type to an existing chat (e.g., adding "Roadmap" to Spec chat)
- **Implementing** inline AI editing for a new document type (text selection → AI-assisted rewrite/expand/fix)
- **Modifying** chat behavior or adding new tools
- **Debugging** chat streaming, tool execution, or event handling issues
- **Understanding** how chat works end-to-end

## Core Architecture

The chat system has three main layers:

### 1. Frontend Layer (Vue.js)
- **ChatInterface.vue**: Universal component handling all chat types
- **Domain Wrappers**: Thin wrappers (SessionChat.vue, SpecFullChat.vue) for domain-specific configs
- **Event System**: WebSocket-based real-time updates via `$lastWsEvents`

### 2. Backend Layer (Python)
- **BaseChatOrchestrator**: Abstract base providing conversation management, tool execution, streaming
- **Domain Orchestrators**: Thin subclasses (PlanOrchestrator, SpecOrchestrator) configuring tools and prompts
- **StreamableObject Interface**: Domain objects implement get_stream_id(), get_event_log(), save()

### 3. Communication Layer
- **Events**: AIEvent, UserEvent, ToolCallEvent, ToolResultEvent, etc.
- **Broadcasting**: async broadcast_event_async() sends events to Pushpin/WebSocket
- **Streaming**: Server-Sent Events (SSE) for historical event replay

## Quick Start: Adding a New Chat

### Step 1: Implement StreamableObject Interface

Domain object must provide:
```python
def get_stream_id() -> str         # Unique identifier (e.g., "tasks_abc123")
def get_event_log() -> list[Event] # Chat history
async def save(org) -> None        # Persist changes
```

### Step 2: Create Domain Orchestrator

Extend BaseChatOrchestrator and implement two methods:
```python
class MyDomainOrchestrator(BaseChatOrchestrator):
    async def get_tool_configuration(self, streamable_object, org, **kwargs):
        # Configure domain-specific tools

    async def create_domain_prompt(self, streamable_object, org, **kwargs):
        # Create initial context prompt
```

### Step 3: Create Frontend Wrapper

Wrap ChatInterface.vue with domain-specific props:
```vue
<IssuesChatInterface
  domain-type="my_domain"
  :domain-id="myDomainId"
  @stop="handleStop"
  @session-updated="handleUpdate"
/>
```

### Step 4: Register Domain Type with Unified Endpoints

Update THREE files for complete streaming integration:

#### A. Add to `sleuth/apps/issues/utility/ninja_api.py`

**A1. Add to `get_streamable_object()` function** (around line 650):
```python
elif object_type == "my_domain":
    return await get_my_domain_manager().get_my_domain(object_id, org=org)
```

**A2. Add to `get_orchestrator_for_domain()` function** (around line 717) if you have a custom orchestrator:
```python
"my_domain": MyDomainOrchestrator,
```

**A3. Add stream auto-registration** in `stream_events_generic()` (around line 260):
```python
elif stream_id.startswith("mydomain_"):
    domain_id = stream_id[9:]  # Remove 'mydomain_' prefix
    my_domain = await get_my_domain_manager().get_my_domain(domain_id, org=org)
    if my_domain:
        await get_or_create_streaming_context(stream_id, my_domain, org)
        streamable_object = await get_streaming_context(stream_id, org)
```

#### B. **CRITICAL**: Add to `sleuth/apps/issues/streaming/disk_context.py`

Add your domain to `get_streaming_context()` function (around line 40):
```python
elif stream_id.startswith("mydomain_"):
    domain_id = stream_id.replace("mydomain_", "")
    from sleuth.apps.issues.mydomain.manager import get_mydomain_manager

    return await get_mydomain_manager().get_mydomain(domain_id, org)
```

**Why this is critical**: Without this, you'll get `404 Not Found` when connecting to the stream and chat will not work at all. This is the most commonly forgotten step!

**Note**: The unified endpoints `/issues/{domain_type}/{domain_id}/chat/` and `/issues/{domain_type}/{domain_id}/stop/` work automatically once your domain is registered!

### Step 5: Register Streaming Tools (If Applicable)

**CRITICAL**: If your domain uses sub-orchestrator tools (tools that themselves run orchestrators), you MUST register them in ChatInterface.vue's `isStreamingTool()` function. Otherwise, users won't see streaming progress in the UI.

```typescript
// frontend/components/issues/ChatInterface.vue
function isStreamingTool(toolName: string): boolean {
  return [
    // ... existing tools ...
    'your_sub_orchestrator_tool',  // Don't forget this!
  ].includes(toolName)
}
```

See `references/frontend_architecture.md` "Sub-Orchestrator Streaming" section for details.

## Detailed Documentation

Refer to the bundled reference files for comprehensive technical details:

### `references/frontend_architecture.md`
- ChatInterface.vue component API and patterns
- Wrapper component patterns (SessionChat, SpecFullChat)
- Event handling and state management
- Custom input slots and file uploads
- Auto-scroll behavior and user interaction patterns

### `references/backend_architecture.md`
- BaseChatOrchestrator responsibilities and lifecycle
- Tool configuration and ToolConfiguration class
- Event system and broadcasting patterns
- Two-stage model strategy (research vs generation)
- Stop handling and error management
- Context collection and metadata tracking

### `references/streamable_object_interface.md`
- Interface requirements and implementation patterns
- Stream ID conventions and naming
- Event log management
- Save/persistence patterns
- Examples from Session, Spec, PullRequest

### `references/code_examples.md`
- Complete working examples for common scenarios:
  - Creating a simple chat for a new domain
  - Adding document generation to existing chat
  - Implementing sub-orchestrators with dual-streaming
  - Custom tool creation and streaming tools
  - Complex event handling patterns

### `references/common_pitfalls.md`
- Frequent mistakes and how to avoid them
- Debugging tips and techniques
- Performance considerations
- Testing strategies

### `references/inline_editing.md`
- Inline AI editing pattern for document section updates
- TipTapEditor text selection and AI action menu
- use-document-section-update composable pattern
- TextSelectionModal integration
- Extending UpdateSectionTool to new document types
- Document ID format conventions and routing
- Complete implementation guide with examples

## Key Patterns to Follow

### Frontend Patterns
1. **Use ChatInterface.vue** - Never create a new base chat component
2. **Thin wrappers** - Domain components should only pass props and handle events
3. **domainType/domainId** - Use consistent naming (e.g., "session"/"session_123")
4. **Event emission** - Emit domain-specific events for UI refresh triggers

### Backend Patterns
1. **Extend BaseChatOrchestrator** - Never reimplement orchestration logic
2. **OrchestratorConfig** - Use configuration for behavior customization
3. **Tool organization** - Separate research and domain-specific tools
4. **System prompts** - Write clear, structured prompts with explicit workflows
5. **Auto-stop via stop_reason** - Orchestration stops automatically via Claude's API, not via tools

### Communication Patterns
1. **Event broadcasting** - Always use broadcast_event_async()
2. **Dual streaming** - Support parent callbacks for sub-orchestrators
3. **Event types** - Use appropriate event types (AI, User, Tool, System)
4. **Ephemeral events** - Mark streaming content as ephemeral to avoid storage

## Testing Your Implementation

1. **Frontend**: Test chat UI, message display, event handling, stop button
2. **Backend**: Test tool execution, event broadcasting, error handling
3. **Integration**: Test full conversation flow with real LLM
4. **Streaming**: Test real-time updates and reconnection behavior

## Next Steps

After reviewing this documentation:
1. Read the relevant reference files for your use case
2. Look at code examples similar to your needs
3. Implement following the patterns documented
4. Test thoroughly using the testing checklist
5. Iterate based on behavior and user feedback
