# Backend Architecture Reference

## BaseChatOrchestrator - Core Orchestration Engine

Location: `sleuth/apps/issues/orchestration/base.py`

### Responsibilities

The base orchestrator provides 95% of common functionality:
1. **LLM Streaming**: Async streaming conversation management with Claude
2. **Tool Execution**: Concurrent and sequential tool execution with timeout handling
3. **Event Broadcasting**: Dual-stream broadcasting (Pushpin + optional parent callback)
4. **Error Handling**: Consecutive error tracking and recovery
5. **Stop Management**: Redis-backed stop signal checking
6. **Context Management**: Research context collection and metadata tracking
7. **Performance Logging**: Tool timing and orchestration metrics
8. **Two-Stage Models**: Automatic switching between research (Haiku) and generation (Sonnet) models

### Abstract Methods (Domain-Specific)

Subclasses must implement only these two methods:

```python
@abstractmethod
async def get_tool_configuration(self, streamable_object: StreamableObject, org, **kwargs) -> ToolConfiguration:
    """Configure domain-specific tools."""
    pass

@abstractmethod
async def create_domain_prompt(self, streamable_object: StreamableObject, org, **kwargs) -> str:
    """Create initial context prompt for this domain."""
    pass
```

### Orchestrator Configuration

```python
from sleuth.apps.issues.orchestration.tool_config import OrchestratorConfig

config = OrchestratorConfig(
    system_prompt=MY_SYSTEM_PROMPT,                 # Instructions for Claude
    auto_continuation_prompt=None,                  # Prompt to continue after completion (optional)
    auto_start_conversation=True,                   # Auto-start with initial prompt (vs wait for user)
    temperature=0.2,                                # LLM temperature
    model=None,                                     # Generation model (defaults to SLEUTH_ISSUES_SMART_MODEL)
    research_model=None,                            # Research model (defaults to SLEUTH_ISSUES_FAST_MODEL)
    max_tokens=None,                                # Max tokens (defaults to settings)
    max_conversation_turns=15,                      # Max turns before stopping
    max_consecutive_errors=3,                       # Max errors before aborting
    tool_timeout_seconds=300,                       # Timeout per tool call
    use_two_stage_models=True,                      # Enable Haiku→Sonnet strategy
)
```

### Two-Stage Model Strategy

When `use_two_stage_models=True`:
1. **Research Phase**: Uses fast model (Haiku) for context gathering
2. **Transition Signal**: Auto-injects `research_complete` tool
3. **Generation Phase**: Uses smart model (Sonnet) after `research_complete` is called

```python
def _select_model_for_turn(self, orchestration_context: OrchestrationContext) -> str:
    if not self.config.use_two_stage_models:
        return self.config.model

    research_complete_called = orchestration_context.get_runtime_data("research_complete_called", False)

    if research_complete_called:
        return self.config.model  # Sonnet for generation
    else:
        return self.config.research_model  # Haiku for research
```

## Domain Orchestrator Pattern

### Example: PlanOrchestrator

```python
from anthropic import AsyncAnthropic
from sleuth.apps.issues.orchestration.base import BaseChatOrchestrator
from sleuth.apps.issues.orchestration.tool_config import OrchestratorConfig, ToolConfiguration

PLAN_SYSTEM_PROMPT = """You create implementation plans..."""

class PlanOrchestrator(BaseChatOrchestrator):
    def __init__(self, anthropic_client: AsyncAnthropic, auto_start_conversation: bool = True):
        config = OrchestratorConfig(
            system_prompt=PLAN_SYSTEM_PROMPT,
            completion_tool_name="post_plan",
            auto_start_conversation=auto_start_conversation,
            temperature=0.2,
            max_conversation_turns=15,
            use_two_stage_models=True,
        )
        super().__init__(anthropic_client, config)

    async def get_tool_configuration(self, streamable_object: StreamableObject, org, **kwargs) -> ToolConfiguration:
        # Resolve GitHub org/repo
        github_org, github_repo = await resolve_github_context(streamable_object, org)

        # Resolve provider and issue context
        provider, issue_team_key = await resolve_provider_context(streamable_object, org)

        # Create tool configuration
        tool_config = ToolConfiguration(
            provider=provider,
            github_org=github_org,
            github_repo=github_repo,
            issue_id=streamable_object.issue_key,
            issue_key=streamable_object.issue_key,
            enable_research_tools=True,
            enable_memory_tool=True,
            enable_evaluation_tool=True,
            completion_tool_name=self.config.completion_tool_name,
        )

        # Add domain-specific tools
        tool_config.add_domain_tool("post_plan", PostPlanTool(...))
        tool_config.add_domain_tool("evaluation", EvaluationTool(...))

        # Add research/context tools
        context_tools = await ContextCollectorOrchestrator.make_context_tools(...)
        for name, tool in context_tools.items():
            tool_config.add_context_tool(name, tool)

        return tool_config

    async def create_domain_prompt(self, streamable_object: StreamableObject, org, **kwargs) -> str:
        session = streamable_object
        issue_key = getattr(session, "issue_key", "")
        # ... compose prompt from session data
        return prompt
```

## Tool Configuration

### Tool Factory: ContextCollectorOrchestrator.make_context_tools()

**CRITICAL**: Always use the tool factory to get context/research tools. This ensures consistent tool instantiation across the codebase.

Location: `sleuth/apps/issues/context_collectors/context_collector_orchestrator.py:62`

```python
from sleuth.apps.issues.context_collectors.context_collector_orchestrator import ContextCollectorOrchestrator

# Get standardized context/research tools via factory
context_tools = await ContextCollectorOrchestrator.make_context_tools(
    org=org,
    provider="linear",                    # or "jira"
    issue_id=issue_key,
    session_id=session_id,
    github_org=github_org,
    github_repo=github_repo,
    issue_team_key=issue_team_key,       # Linear team ID or Jira project key
)

# Returns dict with standard context/research tools:
# - Core: remember
# - Research: related_issues, related_pull_requests, related_code
# - GitHub: github_code_search, github_file_read, github_pr_search, github_pr_read, github_list_commits
# - Provider: linear_search, linear_issue_read, linear_dependency (or jira_*)
# - Spec: spec_search_tool, spec_retrieve_tool
# - Web: web_page_retrieval, confluence_page_read

# Add all context tools to config
for name, tool in context_tools.items():
    tool_config.add_context_tool(name, tool)
```

**What the Factory Does NOT Include:**
- Domain-specific completion tools (e.g., `post_plan`, `generate_prd`, `save_pr_evaluation`)
- Domain-specific evaluation tools
- These must be added explicitly by each orchestrator as domain tools

**Why Use the Factory?**
1. Ensures consistent tool configuration across all orchestrators
2. Handles provider-specific tool selection automatically
3. Properly initializes tools with organization credentials
4. Maintains single source of truth for available tools
5. Prevents duplicate or inconsistent tool instantiation
6. Keeps domain-specific tools separate from shared research tools

### ToolConfiguration Class

```python
from sleuth.apps.issues.orchestration.tool_config import ToolConfiguration

tool_config = ToolConfiguration(
    provider="linear",                          # or "jira"
    github_org="myorg",
    github_repo="myrepo",
    issue_id="ABC-123",
    issue_key="ABC-123",
    enable_research_tools=True,                 # Adds related_*, spec_search, etc.
    enable_memory_tool=True,                    # Adds remember tool
    enable_evaluation_tool=True,                # Adds evaluation tool
    max_tool_calls_per_type=6,                  # Limit per tool type
    total_tool_call_budget=30,                  # Total tool call limit
    completion_tool_name="post_plan",           # Optional completion tool
)

# Add domain-specific tools FIRST
tool_config.add_domain_tool("my_tool", MyToolInstance())

# Add context/research tools via FACTORY (recommended)
context_tools = await ContextCollectorOrchestrator.make_context_tools(
    org=org,
    provider=provider,
    issue_id=issue_key,
    session_id=session_id,
    github_org=github_org,
    github_repo=github_repo,
    issue_team_key=issue_team_key,
)

for name, tool in context_tools.items():
    tool_config.add_context_tool(name, tool)

# Generate Anthropic schema
tool_config.generate_anthropic_schema()

# Access tools
tool = tool_config.get_tool("my_tool")
tools_schema = tool_config.anthropic_tools_schema
```

### Tool Categories

1. **Domain Tools**: Domain-specific tools unique to each orchestrator
   - Examples: `post_plan`, `generate_prd`, `save_pr_evaluation`, `evaluation`
   - Added via `tool_config.add_domain_tool()`
   - **NOT included in factory** - must be added explicitly by orchestrator

2. **Context Tools**: Shared research/context tools across all orchestrators
   - Added via `tool_config.add_context_tool()`
   - **Use `ContextCollectorOrchestrator.make_context_tools()` factory**
   - Includes:
     - Core: `remember`
     - Research: `related_code`, `related_issues`, `related_pull_requests`
     - GitHub: `github_code_search`, `github_file_read`, `github_pr_search`, `github_pr_read`
     - Provider: `linear_search`, `linear_issue_read`, `jira_search`, etc. (auto-selected by provider)
     - Spec: `spec_search_tool`, `spec_retrieve_tool`
     - Web: `web_page_retrieval`, `confluence_page_read`

### How Orchestration Stops

**IMPORTANT**: Orchestration completion is handled automatically via Claude's native API `stop_reason` values, NOT via a completion tool.

The conversation loop checks Claude's `stop_reason` after each turn:
- `"end_turn"` - Claude signals natural conversation end → **Stops**
- `"max_tokens"` - Token limit reached → **Stops**
- `"stop_sequence"` - Stop sequence encountered → **Stops**
- `"tool_use"` - Claude wants to use tools → **Continues**

See `base.py:653-675` for the implementation. Domain-specific tools like `post_plan` or `save_pr_evaluation` are just regular tools that save results - they don't control orchestration flow.

## Event System

### Event Types

```python
from sleuth.apps.issues.models import (
    AIEvent,              # AI text content
    UserEvent,            # User message
    SystemEvent,          # System notification
    ToolCallEvent,        # Tool invocation
    ToolResultEvent,      # Tool result
    ToolStreamingEvent,   # Streaming tool output
    AIThinkingEvent,      # AI started thinking
    AIRespondedEvent,     # AI finished
    AIWaitingEvent,       # AI waiting
    AINoopEvent,          # No operation
    ErrorEvent,           # Error occurred
)
```

### Broadcasting Events

```python
from sleuth.apps.issues.streaming.broadcaster import broadcast_event_async

# Broadcast to Pushpin/WebSocket
await broadcast_event_async(
    org,
    stream_id,
    event,
    streamable_object,
    ephemeral=False  # True for streaming content that shouldn't be stored
)

# Dual streaming (broadcast + parent callback)
await self._dual_broadcast(
    org,
    stream_id,
    event,
    streamable_object,
    ephemeral=False
)
```

### Event Storage

Events are stored in `streamable_object.event_log` as JSON:
- `ephemeral=False`: Stored permanently in event log
- `ephemeral=True`: Broadcast to UI but not stored (streaming content)

## Stop Handling

### Redis-backed Stop Management

```python
from sleuth.apps.issues.orchestration.stop_manager import get_stop_manager

stop_manager = await get_stop_manager()

# Set stop flag
await stop_manager.set_stop(org_id, stream_id)

# Check stop flag
is_stopped = await stop_manager.is_stop_requested(org_id, stream_id)

# Clear stop flag
await stop_manager.clear_stop(org_id, stream_id)
```

Base orchestrator checks stop flag every 500ms during LLM streaming and tool execution.

## Context Collection

### StreamingContext and ContextData

Used to track research metadata for evaluation:

```python
from sleuth.apps.issues.session.context import StreamingContext, ContextData

context_data = ContextData()

# Track tool usage
context_data.update_tool_usage("related_issues", successful=1, metadata={...})

# Track discovered resources
context_data.add_similar_issue("ABC-123", "Issue title", source="related_issues")
context_data.add_related_pull_request("456", "PR title", relevant=True)
context_data.add_code_file_access("/path/to/file.py", lines_read=100)

# Store in streaming context
streaming_ctx = StreamingContext(
    system_blocks=[],
    context_tools={},
    tools=[],
    event_log=[],
    messages=[],
    session_id=stream_id,
    context_data=context_data,
)
```

Base orchestrator automatically collects context from research tool results.

## Conversation Management

### Conversation Loop

```python
async def _conversation_loop(self, org, streamable_object, orchestration_context, tool_config, event_queue):
    while self.conversation_turns < self.config.max_conversation_turns:
        # Check stop
        if await self._check_stop_requested(org, orchestration_context):
            break

        # Process one turn
        turn_had_content = await self._process_one_turn(...)

        if turn_had_content:
            self.conversation_turns += 1
        else:
            break  # No content, end loop

        # Check completion
        last_stop_reason = orchestration_context.get_runtime_data("last_stop_reason")
        if last_stop_reason in ["end_turn", "max_tokens", "stop_sequence"]:
            break  # Natural completion
```

### Stop Reasons

Claude's native stop reasons:
- `end_turn`: Natural conversation end
- `tool_use`: Claude wants to use tools
- `max_tokens`: Token limit reached
- `stop_sequence`: Stop sequence encountered

Orchestrator uses stop reason to determine whether to continue conversation.

## Tool Execution

### Concurrent Tool Execution

```python
async def _execute_tools_concurrently(self, org, tool_calls, streamable_object, orchestration_context, tool_config, event_queue):
    # Deduplicate by ID
    unique_tool_calls = {tc.get("id"): tc for tc in tool_calls}

    # Execute all concurrently
    results = await asyncio.gather(*[execute_single_tool(tc) for tc in unique_tool_calls.values()])

    # Broadcast results
    for tool_id, tool_name, result in results:
        tool_result_event = ToolResultEvent(
            tool_call_id=tool_id,
            content=f"Tool {tool_name} completed",
            tool=tool_name,
            result=result,
        )
        await self._dual_broadcast(org, stream_id, tool_result_event, streamable_object)
```

### Streaming Tools

Tools can support streaming via `call_with_streaming`:

```python
class MyStreamingTool:
    async def call_with_streaming(self, org, tool_input, stream_callback):
        # Stream content progressively
        for chunk in generate_content():
            stream_callback(chunk)  # Broadcasts ToolStreamingEvent

        # Return final result
        return final_result
```

Base orchestrator handles streaming automatically, broadcasting `ToolStreamingEvent` to UI.

## Sub-Orchestrator Pattern

### Dual Streaming for Sub-Orchestrators

When an orchestrator invokes another orchestrator (e.g., SpecOrchestrator calls PRDOrchestrator):

```python
# Parent orchestrator provides stream_callback
sub_orchestrator = PRDOrchestrator(anthropic_client)
await sub_orchestrator.run_orchestration(
    org=org,
    streamable_object=prd_object,
    event_queue=event_queue,
    stream_callback=lambda content: parent_stream_callback(content),  # Dual streaming
    **kwargs
)
```

Base orchestrator's `_dual_broadcast` sends events to:
1. Pushpin/WebSocket (for UI)
2. Parent's stream_callback (for parent orchestrator)

This enables nested orchestration with proper event propagation.
