# Code Examples

## Complete Example: Adding Chat for a New Domain

This example shows how to add chat functionality for a hypothetical "Report" domain object.

### Step 1: Implement StreamableObject Interface

```python
# sleuth/apps/reports/models.py
from sleuth.apps.issues.streaming.interface import StreamableObject
from sleuth.apps.issues.models import AIEvent, UserEvent

class Report(StreamableObject):
    """Report domain object with chat support."""

    def __init__(self, report_id: str, org_id: str):
        self.report_id = report_id
        self.org_id = org_id
        self.event_log = []  # Chat history
        self.title = ""
        self.content = ""

    def get_stream_id(self) -> str:
        """Return unique stream identifier."""
        return f"report_{self.report_id}"

    def get_event_log(self) -> list:
        """Return chat event history."""
        return self.event_log or []

    async def save(self, org) -> None:
        """Persist report to database."""
        # Save to database
        await ReportManager.save_report(self, org)
```

### Step 2: Create Domain Orchestrator

```python
# sleuth/apps/reports/orchestration.py
import logging
from anthropic import AsyncAnthropic

from sleuth.apps.issues.orchestration.base import BaseChatOrchestrator
from sleuth.apps.issues.orchestration.tool_config import OrchestratorConfig, ToolConfiguration
from sleuth.apps.issues.orchestration.github_resolver import resolve_github_context
from sleuth.apps.issues.context_collectors import ContextCollectorOrchestrator
from sleuth.apps.reports.tools import GenerateReportTool
from sleuth.apps.issues.streaming.interface import StreamableObject

logger = logging.getLogger(__name__)

REPORT_SYSTEM_PROMPT = """You generate comprehensive reports for software projects.

**WORKFLOW:**
1. **Research Phase**: Gather context using research tools (fast model)
2. **Signal Transition**: Call research_complete when ready
3. **Generation Phase**: Create detailed report (smart model)
4. **Save**: Use generate_report tool to save

**CRITICAL:**
- Call related_code, related_issues, related_pull_requests CONCURRENTLY
- Call research_complete before generating report
- Use generate_report tool to save final report
- Keep responses brief after report generation
"""

class ReportOrchestrator(BaseChatOrchestrator):
    """Orchestrator for report generation and chat."""

    def __init__(self, anthropic_client: AsyncAnthropic):
        config = OrchestratorConfig(
            system_prompt=REPORT_SYSTEM_PROMPT,
            auto_start_conversation=True,
            temperature=0.15,
            max_conversation_turns=20,
            use_two_stage_models=True,  # Enable Haiku→Sonnet strategy
        )
        super().__init__(anthropic_client, config)

    async def get_tool_configuration(
        self,
        streamable_object: StreamableObject,
        org,
        **kwargs
    ) -> ToolConfiguration:
        """Configure tools for report generation."""
        report = streamable_object

        # Resolve GitHub context
        github_org, github_repo = await resolve_github_context(streamable_object, org)

        # Override with kwargs if provided
        if kwargs.get("github_org"):
            github_org = kwargs.get("github_org")
        if kwargs.get("github_repo"):
            github_repo = kwargs.get("github_repo")

        # Create tool configuration
        tool_config = ToolConfiguration(
            provider="linear",  # or "jira"
            github_org=github_org,
            github_repo=github_repo,
            issue_id=report.report_id,
            issue_key=report.report_id,
            enable_research_tools=True,  # Enables related_* tools
            enable_memory_tool=True,     # Enables remember tool
            enable_evaluation_tool=False,  # Evaluation is session-specific
        )

        # Add domain-specific completion tool FIRST
        tool_config.add_domain_tool(
            "generate_report",
            GenerateReportTool(
                report_id=report.report_id,
                org=org,
            ),
        )

        # Add context/research tools via FACTORY
        # CRITICAL: Always use make_context_tools() for consistency
        # Factory does NOT include domain-specific tools (post_plan, evaluation, etc.)
        context_tools = await ContextCollectorOrchestrator.make_context_tools(
            org=org,
            provider="linear",  # or "jira"
            issue_id=report.report_id,
            session_id=report.get_stream_id(),
            github_org=github_org,
            github_repo=github_repo,
            issue_team_key=None,  # Optional: Linear team or Jira project
        )

        # Add all factory tools to config
        for name, tool in context_tools.items():
            tool_config.add_context_tool(name, tool)

        return tool_config

    async def create_domain_prompt(
        self,
        streamable_object: StreamableObject,
        org,
        **kwargs
    ) -> str:
        """Create initial prompt for report generation."""
        report = streamable_object

        prompt = f"""You are generating a report for: {report.title}

**Report Requirements:**
{report.content}

**Your Task:**
1. Research the codebase using related_code, related_issues, related_pull_requests
2. Call research_complete when you have sufficient context
3. Generate a comprehensive report covering:
   - Executive Summary
   - Technical Analysis
   - Key Findings
   - Recommendations
4. Use generate_report tool to save the final report

Begin by researching the codebase."""

        return prompt
```

### Step 3: Create Domain Tool

```python
# sleuth/apps/reports/tools.py
import logging
from sleuth.apps.organization.models import Organization

logger = logging.getLogger(__name__)

class GenerateReportTool:
    """Tool for saving generated reports."""

    name = "generate_report"
    description = "Save the generated report content"

    def __init__(self, report_id: str, org: Organization):
        self.report_id = report_id
        self.org = org

    def get_anthropic_schema(self):
        """Return Anthropic tool schema."""
        return {
            "name": "generate_report",
            "description": "Save the generated report content",
            "input_schema": {
                "type": "object",
                "properties": {
                    "report_content": {
                        "type": "string",
                        "description": "The full markdown content of the generated report",
                    },
                    "executive_summary": {
                        "type": "string",
                        "description": "Brief executive summary (2-3 sentences)",
                    },
                },
                "required": ["report_content", "executive_summary"],
            },
        }

    async def call(self, tool_input: dict, org: Organization):
        """Execute the tool."""
        report_content = tool_input.get("report_content", "")
        executive_summary = tool_input.get("executive_summary", "")

        # Save report to database
        from sleuth.apps.reports.manager import get_report_manager
        report_manager = get_report_manager()

        await report_manager.save_report_content(
            self.report_id,
            report_content,
            executive_summary,
            org
        )

        return f"Report saved successfully. Summary: {executive_summary}"
```

### Step 4: Register Domain with Unified Endpoints

**IMPORTANT**: You do NOT need to create domain-specific API endpoints. The unified endpoints at `/issues/{domain_type}/{domain_id}/chat/` and `/issues/{domain_type}/{domain_id}/stop/` work for ALL domain types.

Update `sleuth/apps/issues/utility/ninja_api.py` to register your domain:

```python
# sleuth/apps/issues/utility/ninja_api.py

# 1. Add to get_streamable_object() function (around line 650)
async def get_streamable_object(object_type: str, object_id: str, org: Organization):
    """Get StreamableObject by type and ID"""
    try:
        # ... existing domain types ...
        elif object_type == "report":
            return await get_report_manager().get_report(object_id, org=org)
        else:
            return None
    except Exception as e:
        logger.error(f"Error loading {object_type} {object_id}: {e}")
        return None


# 2. Add to get_orchestrator_for_domain() function (around line 717)
def get_orchestrator_for_domain(
    domain_type: str, anthropic_client: AsyncAnthropic, **kwargs
) -> Optional[BaseChatOrchestrator]:
    """Factory function to get the appropriate orchestrator for a domain type."""
    orchestrator_map = {
        # ... existing orchestrators ...
        "report": ReportOrchestrator,
    }

    orchestrator_class = orchestrator_map.get(domain_type.lower())
    if not orchestrator_class:
        logger.error(f"Unknown domain type: {domain_type}")
        return None

    return orchestrator_class(anthropic_client)


# 3. Add stream auto-registration in stream_events_generic() (around line 260)
@router.get("/issues/streams/{stream_id}/stream/")
async def stream_events_generic(request, stream_id: str, last_event_index: int = Query(0)):
    """Generic streaming endpoint for any streamable object using Pushpin."""
    org = await get_org(request)

    # ... existing auto-registration logic ...

    # Add your domain's auto-registration
    elif stream_id.startswith("report_"):
        report_id = stream_id[7:]  # Remove 'report_' prefix
        logger.info(f"Attempting to auto-register report {report_id} for streaming...")

        try:
            report_manager = get_report_manager()
            report = await report_manager.get_report(report_id, org)

            if report:
                await get_or_create_streaming_context(stream_id, report, org)
                streamable_object = await get_streaming_context(stream_id, org)
                logger.info(f"✅ Auto-registered report {report_id} for streaming")
            else:
                logger.warning(f"❌ Report {report_id} not found for auto-registration")
        except Exception as reg_error:
            logger.error(f"💥 Auto-registration failed for report {report_id}: {reg_error}")

    # ... rest of streaming logic ...
```

**That's it!** The unified endpoints will now work for your domain:
- `POST /api/issues/report/{report_id}/chat/` - Send messages
- `POST /api/issues/report/{report_id}/stop/` - Stop orchestration
- `GET /api/issues/streams/report_{report_id}/stream/` - Stream events

### Step 5: Create Frontend Wrapper Component

```vue
<!-- frontend/components/reports/ReportChat.vue -->
<script setup lang="ts">
const props = defineProps<{
  reportId: string | null
  reportData: any
}>()

const emit = defineEmits<{
  'report-updated': [reportId: string]
}>()

const chatInterfaceRef = ref()

function handleReportUpdated(reportId: string) {
  emit('report-updated', reportId)
}

function stopLLM() {
  console.log('Stop requested for report:', props.reportId)
}

defineExpose({
  clearMessages: () => chatInterfaceRef.value?.clearMessages(),
})
</script>

<template>
  <div class="report-chat-pane">
    <IssuesChatInterface
      ref="chatInterfaceRef"
      :messages="[]"
      domain-type="report"
      :domain-id="reportId"
      :has-data="!!reportId"
      placeholder="Select a report to view chat."
      empty-message="No chat yet."
      input-placeholder="Ask about the report or request changes..."
      :disabled="!reportId"
      waiting-message="Generating report..."
      @stop="stopLLM"
      @session-updated="handleReportUpdated"
    />
  </div>
</template>

<style scoped>
.report-chat-pane {
  height: 100%;
  display: flex;
  flex-direction: column;
}
</style>
```

### Step 6: Test Your Implementation

Test the unified endpoints work correctly:

1. **Chat**: `POST /api/issues/report/{report_id}/chat/`
   ```bash
   curl -X POST http://localhost:8000/api/issues/report/abc123/chat/ \
     -H "Content-Type: application/json" \
     -d '{"message": "Generate a report about authentication"}'
   ```

2. **Stop**: `POST /api/issues/report/{report_id}/stop/`
   ```bash
   curl -X POST http://localhost:8000/api/issues/report/abc123/stop/
   ```

3. **Stream**: `GET /api/issues/streams/report_abc123/stream/?last_event_index=0`
   ```bash
   curl http://localhost:8000/api/issues/streams/report_abc123/stream/?last_event_index=0
   ```

## Example: Adding Streaming Tool

```python
class MyStreamingTool:
    """Tool that streams its output progressively."""

    name = "analyze_codebase"
    description = "Analyze the codebase and stream findings"

    def get_anthropic_schema(self):
        return {
            "name": "analyze_codebase",
            "description": "Analyze the codebase and stream findings progressively",
            "input_schema": {
                "type": "object",
                "properties": {
                    "focus_area": {
                        "type": "string",
                        "description": "Area to focus analysis on",
                    },
                },
                "required": ["focus_area"],
            },
        }

    async def call_with_streaming(self, org, tool_input: dict, stream_callback):
        """Execute tool with streaming output."""
        focus_area = tool_input.get("focus_area", "")

        # Stream findings progressively
        stream_callback(f"Analyzing {focus_area}...\n\n")

        # Simulate progressive analysis
        findings = [
            "1. Found authentication module at /auth/handlers.py\n",
            "2. Identified 3 potential security issues\n",
            "3. Database schema includes users, sessions, tokens\n",
            "4. Test coverage is approximately 75%\n",
        ]

        for finding in findings:
            stream_callback(finding)
            await asyncio.sleep(0.5)  # Simulate work

        stream_callback("\n\nAnalysis complete!")

        # Return final summary
        return f"Completed analysis of {focus_area}. Found {len(findings)} key points."
```

## Example: Dynamic System Prompt

For domains where available features vary (like SpecOrchestrator with optional documents):

```python
async def _generate_dynamic_system_prompt(self, report: Report) -> str:
    """Generate system prompt based on report configuration."""

    # Determine available sections
    available_sections = []
    if report.include_executive_summary:
        available_sections.append("Executive Summary")
    if report.include_technical_analysis:
        available_sections.append("Technical Analysis")
    if report.include_recommendations:
        available_sections.append("Recommendations")

    sections_list = "\n".join([f"- {section}" for section in available_sections])

    dynamic_prompt = f"""{BASE_SYSTEM_PROMPT}

**AVAILABLE SECTIONS:**
You can generate the following sections for this report:
{sections_list}

**IMPORTANT:** Only generate sections listed above. If user requests other sections,
explain they are not configured for this report type.
"""

    return dynamic_prompt

# Update prompt before tool configuration
async def get_tool_configuration(self, streamable_object, org, **kwargs):
    report = streamable_object
    self.config.system_prompt = await self._generate_dynamic_system_prompt(report)
    # ... continue with tool configuration
```
