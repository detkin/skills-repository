# Common Pitfalls and Debugging Tips

## Common Mistakes

### 1. Creating Domain-Specific API Endpoints (DON'T DO THIS!)

**Problem**: Created `/api/mydomain/{id}/chat/` and `/api/mydomain/{id}/stop/` endpoints for your domain

**Solution**: **DELETE THEM!** The system provides unified endpoints that work for ALL domain types:
- `POST /api/issues/{domain_type}/{domain_id}/chat/` - Universal chat endpoint
- `POST /api/issues/{domain_type}/{domain_id}/stop/` - Universal stop endpoint
- `GET /api/issues/streams/{stream_id}/stream/` - Universal streaming endpoint

You only need to register your domain type by updating three helper functions in `sleuth/apps/issues/utility/ninja_api.py`:
1. `get_streamable_object()` - Add your domain to the factory
2. `get_orchestrator_for_domain()` - Add your orchestrator to the map
3. `stream_events_generic()` - Add auto-registration for your stream_id pattern

See Step 4 in the main skill documentation for details.

### 2. Not Adding Domain to disk_context.py (CRITICAL!)

**Problem**: `404 Not Found` when connecting to stream, `WARNING Unknown stream_id format: {domain}_{id}`

**Solution**: Add your domain's stream_id pattern to `get_streaming_context()` in `sleuth/apps/issues/streaming/disk_context.py`:

```python
elif stream_id.startswith("mydomain_"):
    domain_id = stream_id.replace("mydomain_", "")
    from sleuth.apps.issues.mydomain.manager import get_mydomain_manager

    return await get_mydomain_manager().get_mydomain(domain_id, org)
```

This is **REQUIRED** for the streaming system to resolve your stream_id to the actual domain object. Without this, chat will not work at all.

### 3. Not Implementing StreamableObject Correctly

**Problem**: Chat doesn't work, events not appearing

**Solution**: Ensure domain object implements all three methods:
- `get_stream_id()` - Must return unique ID with format `{domain}_{id}`
- `get_event_log()` - Must return list of events
- `async save(org)` - Must persist to database

### 4. Wrong domainType/domainId Format

**Problem**: Frontend can't connect to stream

**Solution**:
- domainType should match stream_id prefix (e.g., "session" for "session_abc")
- domainId should match stream_id suffix (e.g., "abc" for "session_abc")
- Stream ID = `{domainType}_{domainId}`

### 5. Forgetting to Call super().__init__()

**Problem**: Orchestrator doesn't work, missing configuration

**Solution**: Always call parent constructor:
```python
class MyOrchestrator(BaseChatOrchestrator):
    def __init__(self, anthropic_client):
        config = OrchestratorConfig(...)
        super().__init__(anthropic_client, config)  # CRITICAL
```

### 6. Not Broadcasting Events

**Problem**: UI doesn't update, messages don't appear

**Solution**: Use `broadcast_event_async` or `self._dual_broadcast`:
```python
await self._dual_broadcast(org, stream_id, event, streamable_object)
```

### 7. Duplicate Tool Registration

**Problem**: Tools execute multiple times

**Solution**: Check ToolConfiguration - don't add the same tool twice:
```python
# Wrong
tool_config.add_domain_tool("my_tool", MyTool())
tool_config.add_domain_tool("my_tool", MyTool())  # Duplicate!

# Right
tool_config.add_domain_tool("my_tool", MyTool())  # Once only
```

### 8. Not Handling Stop Events

**Problem**: Chat continues after user clicks stop

**Solution**:
- Backend: Check stop flag regularly via `_check_stop_requested`
- Frontend: Handle stop button click and call stop API
- The unified stop endpoint handles setting Redis flags automatically

### 9. Misunderstanding How Orchestration Stops

**Problem**: Thinking you need a "completion tool" to stop orchestration

**Solution**: Orchestration stops automatically via Claude's native API `stop_reason`:
- `"end_turn"` - Claude signals natural end
- `"max_tokens"` - Token limit reached
- `"stop_sequence"` - Stop sequence encountered

Domain tools like `post_plan` or `save_pr_evaluation` are just regular tools that save results - they don't control orchestration flow. See `base.py:653-675`.

### 10. Event Log Not Persisting

**Problem**: Chat history disappears on reload

**Solution**: Ensure `save()` persists `event_log` to database

### 11. Frontend Not Filtering Events

**Problem**: Internal events show in UI

**Solution**: Use correct `objectId` matching in WebSocket watch:
```typescript
if (latestEvent.objectId !== currentStreamId) return
```

### 10. Tool Doesn't Have Proper Schema

**Problem**: LLM can't call tool correctly

**Solution**: Implement `get_anthropic_schema()` properly:
```python
def get_anthropic_schema(self):
    return {
        "name": "tool_name",
        "description": "Clear description of what tool does",
        "input_schema": {
            "type": "object",
            "properties": {
                "param": {"type": "string", "description": "Parameter description"}
            },
            "required": ["param"]
        }
    }
```

### 11. Sub-Orchestrator Tool Not Streaming in UI (THE QUIRK)

**Problem**: Created a sub-orchestrator tool with `call_with_streaming`, but the streaming progress doesn't show in the tool result block in the UI. The tool executes successfully, but users see no progress.

**Solution**: Add the tool name to `isStreamingTool()` array in ChatInterface.vue:

```typescript
// frontend/components/issues/ChatInterface.vue
function isStreamingTool(toolName: string): boolean {
  return [
    'related_issues',
    'related_pull_requests',
    'related_code',
    'generate_prd',
    'generate_prototype',
    'generate_techdoc',
    'generate_tasks',
    'your_new_tool_name',  // ⚠️ ADD YOUR TOOL HERE
  ].includes(toolName)
}
```

**Why This Happens**: ChatInterface uses this registry to determine whether to:
- Accumulate `tool_streaming` events into `streamingOutput`
- Display streaming content with typewriter effect
- Combine streaming output with final result using separator

Without registration, the tool's streaming events are broadcast but ignored by the UI.

## Debugging Tips

### Check Event Log

```python
# Get event log from streamable object
events = streamable_object.get_event_log()
for event in events:
    print(f"{event.type}: {event.content[:50]}")
```

### Monitor Redis Stop Flags

```bash
# Check if stop flag is set
redis-cli GET "orchestration_stop:{org_id}:{stream_id}"
```

### Enable Debug Logging

```python
import logging
logging.getLogger('sleuth.apps.issues.orchestration').setLevel(logging.DEBUG)
```

### Test Orchestrator Directly

```python
# Test orchestrator without UI
from anthropic import AsyncAnthropic
import asyncio

async def test_orchestrator():
    client = AsyncAnthropic(api_key="...")
    orchestrator = MyOrchestrator(client)

    event_queue = asyncio.Queue()

    await orchestrator.run_orchestration(
        org=org,
        streamable_object=my_object,
        event_queue=event_queue,
        github_org="myorg",
        github_repo="myrepo",
    )

asyncio.run(test_orchestrator())
```

### Check Tool Configuration

```python
tool_config = await orchestrator.get_tool_configuration(streamable_object, org)
print("Domain tools:", tool_config.domain_tools.keys())
print("Context tools:", tool_config.context_tools.keys())
print("Anthropic schema:", len(tool_config.anthropic_tools_schema), "tools")
```

### Test Frontend Events

```javascript
// In browser console
window.debugInternalMessages  // Check messages array
window.debugProps              // Check component props
```

### Verify Streaming Connection

```bash
# Test SSE endpoint
curl -N "http://localhost:8000/api/streams/session_abc123/stream/"
```

## Performance Considerations

### 1. Tool Execution

- **Concurrent**: Use concurrent execution for independent tools
- **Sequential**: Only when tools depend on each other
- **Timeout**: Set reasonable timeouts (default 300s)

### 2. Event Broadcasting

- **Ephemeral**: Mark streaming content as ephemeral to avoid storage bloat
- **Batching**: Don't broadcast every character, batch for efficiency

### 3. Context Window

- **Two-stage models**: Use fast model for research, smart for generation
- **Tool limits**: Set reasonable tool call budgets
- **Prompt caching**: Use cache_control for system prompts

### 4. Database

- **Save frequency**: Don't save after every event, batch where possible
- **Event log size**: Monitor event log growth, implement cleanup if needed

## Testing Strategies

### Unit Tests

```python
@pytest.mark.asyncio
async def test_orchestrator_tool_configuration():
    """Test tool configuration."""
    orchestrator = MyOrchestrator(mock_client)
    tool_config = await orchestrator.get_tool_configuration(mock_object, mock_org)

    assert "my_tool" in tool_config.domain_tools
    assert tool_config.completion_tool_name == "my_completion_tool"
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_full_chat_flow(mock_anthropic):
    """Test complete chat flow."""
    # Create mock streamable object
    obj = MockStreamableObject()

    # Run orchestration
    orchestrator = MyOrchestrator(mock_anthropic)
    await orchestrator.run_orchestration(org=org, streamable_object=obj, ...)

    # Verify events
    assert len(obj.event_log) > 0
    assert any(e.type == "ai" for e in obj.event_log)
```

### Frontend Tests

```vue
<script setup>
import { mount } from '@vue/test-utils'
import ChatInterface from './ChatInterface.vue'

test('sends message correctly', async () => {
  const wrapper = mount(ChatInterface, {
    props: {
      domainType: 'test',
      domainId: '123',
    },
  })

  await wrapper.vm.sendMessage('test message')
  expect(wrapper.emitted('messageSent')).toBeTruthy()
})
</script>
```
