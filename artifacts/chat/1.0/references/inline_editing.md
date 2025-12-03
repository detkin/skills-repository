# Inline AI Editing Pattern

## Overview

The inline AI editing pattern allows users to select text within a document editor and trigger AI-assisted modifications (rewrite, expand, fix grammar, etc.). This pattern is used across multiple document types: PRD, TechDoc, Session, and Skill Files.

## Architecture

The pattern consists of three main layers:

### 1. Frontend Layer (Vue.js)

**Components:**
- **TipTapEditor.vue**: Rich text editor with text selection detection and floating AI action menu
- **TextSelectionModal.vue**: Modal dialog for capturing user instructions (optional for actions like "rewrite")
- **use-document-section-update composable**: State management and API integration

**Flow:**
1. User selects text in TipTapEditor
2. Floating menu appears with AI action buttons (Rewrite, Expand, Fix Grammar, Custom)
3. User clicks action → `@ai-action` event emitted with context
4. Composable shows modal (if needed) and calls API
5. Editor shows processing overlay over selected text
6. Document reloads with updated content when orchestration completes

### 2. Backend Layer (Python)

**Components:**
- **update_section_endpoint.py**: HTTP endpoint at `/specs/update-section/`
- **UpdateSectionTool**: Unified tool that routes to document-specific loaders
- **Document loaders**: Type-specific methods for loading and saving documents

**Flow:**
1. Endpoint receives section update request with document_type and document_id
2. Loads document and parent object using document-specific loader
3. Uses markdown_section_finder to locate exact text with formatting
4. Constructs message with action, instruction, and context
5. Posts message to domain chat orchestration
6. Orchestration processes with `update_section` tool
7. Tool updates document and saves new version

### 3. Chat Integration

The inline editing triggers a chat message that uses the `update_section` tool. The orchestrator processes this like any other chat message, allowing Claude to:
- Understand the context (surrounding text)
- Apply the requested action (rewrite, expand, fix)
- Use the `update_section` tool to save changes
- Provide brief confirmation to user

## Adding Inline Editing to a New Document Type

Follow these steps to add inline editing support to a new document type:

### Step 1: Frontend - Add Composable to Component

```vue
<script setup lang="ts">
import { useDocumentSectionUpdate } from '~/composables/use-document-section-update'

// Document ID format depends on your document type
// Simple: just the document ID
// Complex: "parent_id:child_id" format (e.g., skill_file uses "skill_hash:file_hash")
const { showAIModal, aiAction, aiSelectedText, handleAIAction, handleAISubmit, closeAIModal }
  = useDocumentSectionUpdate(
    'my_document_type',  // Document type identifier
    () => myDocumentId.value,  // Function that returns current document ID
    editorRef,  // Reference to TipTapEditor (for processing overlay)
  )
</script>

<template>
  <!-- Your TipTapEditor -->
  <IssuesTipTapEditor
    ref="editorRef"
    v-model="documentContent"
    @ai-action="handleAIAction"
  />

  <!-- Add TextSelectionModal -->
  <IssuesTextSelectionModal
    :show="showAIModal"
    :action="aiAction"
    :selected-text="aiSelectedText"
    document-type="my_document_type"
    :document-id="myDocumentId"
    @close="closeAIModal"
    @submit="handleAISubmit"
  />
</template>
```

**Document ID Formats:**
- Simple: `"techdoc_123"` - just pass the ID
- Composite: `"skill_hash:file_hash"` - for nested documents, use colon-separated format
- The format must match what your backend loader expects

### Step 2: Backend - Extend UpdateSectionTool

Add support for your document type in `sleuth/apps/issues/orchestration/update_section_tool.py`:

#### A. Update Tool Description and Schema

```python
class UpdateSectionTool(BaseUpdateSectionTool):
    description = (
        "Update a section of any document (TechDoc, PRD, Session, Skill File, or MyDocument) "
        "by providing the updated text..."
    )

    input_schema = {
        "type": "object",
        "properties": {
            # Add any document-specific parameters if needed
            "my_doc_param": {
                "type": "string",
                "description": "Special parameter for my document type",
            },
            # ... existing properties ...
        },
    }
```

#### B. Add Document Type Detection

```python
def _detect_document_from_stream_id(self) -> tuple[str | None, str | None]:
    """Detect document type from stream_id."""
    # ... existing patterns ...

    # Add your pattern: stream_id format -> document_type, document_id
    elif self.stream_id.startswith("mydoc_"):
        doc_id = self.stream_id[6:]  # Remove 'mydoc_' prefix
        return "my_document", doc_id

    return None, None
```

#### C. Add Document Loader

```python
async def _load_my_document(self, doc_id: str, org: Organization) -> None:
    """Load MyDocument by ID."""
    from myapp.manager import get_my_document_manager

    manager = get_my_document_manager()
    self.document = await manager.get_document(doc_id, org)

    if not self.document:
        raise ToolCallError(f"MyDocument {doc_id} not found")

    self.document_type = "my_document"
```

#### D. Add to call() Method Routing

```python
async def call(self, input_args, org):
    # ... existing code ...

    elif document_type == "my_document":
        await self._load_my_document(document_id, org)
    else:
        raise ToolCallError(f"Unsupported document_type: {document_type}")
```

#### E. Implement Content Getter

```python
async def _get_my_document_content(self) -> tuple[str, str]:
    """Get current MyDocument content."""
    version = self.document.get_current_version() or self.document.get_latest_version()
    if not version:
        raise ToolCallError("MyDocument has no content to update")

    title = f"MyDocument: {self.document.title}"
    return version.content, title
```

#### F. Implement Content Saver

```python
async def _save_my_document_version(self, updated_content: str, change_summary: str) -> int:
    """Save updated MyDocument version."""
    from myapp.storage import get_storage

    new_version = self.document.add_version(
        content=updated_content,
        created_by=None,
        change_summary=change_summary,
        make_current=True,
    )

    storage = get_storage()
    await storage.save_document(self.document, self.org)

    return new_version.version
```

#### G. Add to Routing Methods

```python
async def get_current_content(self) -> tuple[str, str]:
    # ... existing types ...
    elif self.document_type == "my_document":
        return await self._get_my_document_content()

async def save_updated_version(self, updated_content: str, change_summary: str) -> int:
    # ... existing types ...
    elif self.document_type == "my_document":
        return await self._save_my_document_version(updated_content, change_summary)
```

### Step 3: Backend - Update Endpoint

Add support in `sleuth/apps/issues/utility/update_section_endpoint.py`:

#### A. Update _load_document_and_parent()

```python
async def _load_document_and_parent(data, org):
    """Load document and determine parent object."""
    document = None
    parent_object = None
    stream_id = None

    if data.document_type == "my_document":
        manager = get_my_document_manager()
        document = await manager.get_document(data.document_id, org)
        if not document:
            return None, None, None

        # If your document has a parent object for orchestration:
        parent_object = document.get_parent()  # or load separately
        stream_id = document.get_stream_id()  # or parent.get_stream_id()

    # ... existing types ...

    return document, parent_object, stream_id
```

#### B. Update _build_update_message()

```python
def _build_update_message(data, markdown_section):
    """Build message for orchestrator."""
    # ... existing code ...

    tool_params = f'original_text="{markdown_section}", updated_text="your {action_verb.lower()}ed version"'

    if data.document_type == "my_document":
        # Add document-specific parameters if needed
        tool_params = f'my_doc_param="{data.document_id}", {tool_params}'

    # ... rest of message building ...
```

#### C. Update Error Handling

```python
async def update_section_endpoint(request, data):
    """Handle section update requests."""
    # ... existing code ...

    if data.document_type not in ["techdoc", "prd", "session", "skill_file", "my_document"]:
        return JsonResponse(
            {"error": f"Unknown document_type: {data.document_type}. "
                     f"Must be one of: techdoc, prd, session, skill_file, my_document"},
            status=400,
        )

    # ... existing code ...

    if isinstance(parent_object, MyDocumentParent):
        parent_type = "my_document"
        parent_id = parent_object.id
```

### Step 4: Test Your Implementation

1. **Frontend Test**: Select text in your document editor and verify:
   - Floating menu appears
   - Modal opens with correct action
   - Processing overlay shows over selected text
   - Document reloads with changes

2. **Backend Test**: Send API request directly:
```bash
curl -X POST http://localhost:8000/api/specs/update-section/ \
  -H "Content-Type: application/json" \
  -d '{
    "document_type": "my_document",
    "document_id": "doc_123",
    "selected_text": "Original text here",
    "full_markdown": "# Document\n\nOriginal text here\n\nMore content",
    "context_before": "# Document\n\n",
    "context_after": "\n\nMore content",
    "action": "rewrite",
    "instruction": null
  }'
```

3. **Integration Test**: Verify orchestration:
   - Message posted to chat
   - `update_section` tool called correctly
   - Document version saved
   - User sees updated content

## Document Type Examples

### Simple Document (TechDoc)

**Document ID Format**: `"techdoc_123"`

**Stream ID**: `"techdoc_123"` (matches document ID)

**Loader**: Loads single document object directly

### Composite Document (Skill File)

**Document ID Format**: `"skill_hash:file_hash"` (parent:child)

**Stream ID**: `"skill_skill_hash"` (parent's stream)

**Loader**: Parses ID to load parent (Skill) and child (File)

```python
# In UpdateSectionTool.call()
if file_hash_param:
    self.file_hash = file_hash_param
    if self.stream_id and self.stream_id.startswith("skill_"):
        skill_hash = self.stream_id[6:]
        await self._load_skill_file(skill_hash, file_hash_param, org)
```

## Key Patterns and Best Practices

### 1. Document ID Conventions

- **Simple**: Use document ID directly when document has its own orchestration
- **Composite**: Use `"parent_id:child_id"` when child document uses parent's orchestration
- **Consistent**: Use same format in frontend composable and backend loader

### 2. Version Management

Always use versioning pattern:
```python
new_version = document.add_version(
    content=updated_content,
    created_by=None,  # System-generated
    change_summary=change_summary,  # From AI: "Rewrote for clarity" etc.
    make_current=True,  # Make this the active version
)
```

### 3. Error Handling

Provide clear error messages:
```python
if not document:
    raise ToolCallError(f"MyDocument {doc_id} not found")

if not version:
    raise ToolCallError("MyDocument has no content to update")
```

### 4. Context Preservation

The markdown_section_finder preserves formatting:
- Extracts text with exact markdown (bold, links, code, etc.)
- Finds position in document using fuzzy matching
- Ensures AI sees and preserves formatting

### 5. Orchestration Integration

The inline edit posts a message to the domain's chat:
- Uses existing orchestration and system prompt
- Tool `update_section` is automatically available
- AI can use other tools if needed (rare)
- Keeps edit in chat history for context

## Common Pitfalls

### 1. Forgetting to Add @ai-action Handler

**Problem**: Editor emits event but nothing happens

**Solution**: Add handler and modal:
```vue
<IssuesTipTapEditor @ai-action="handleAIAction" />
<IssuesTextSelectionModal ... @submit="handleAISubmit" />
```

### 2. Wrong Document ID Format

**Problem**: Backend can't find document

**Solution**: Check document ID format matches backend expectations:
- Simple: `"doc_123"`
- Composite: `"parent_id:child_id"`

### 3. Missing Document Type in Routing

**Problem**: "Unsupported document_type" error

**Solution**: Add type to all routing points:
- `_detect_document_from_stream_id()`
- `call()` method routing
- `get_current_content()` routing
- `save_updated_version()` routing
- Endpoint `_load_document_and_parent()`

### 4. Not Handling Parent vs Document

**Problem**: Orchestration context missing or wrong stream

**Solution**:
- Composite documents: parent_object provides orchestration context
- Simple documents: document itself is parent_object
- Stream ID should match orchestration stream

### 5. Missing Processing Overlay

**Problem**: User doesn't see feedback during processing

**Solution**: Pass editorRef to composable:
```typescript
const { ... } = useDocumentSectionUpdate(
  'my_type',
  () => docId.value,
  editorRef,  // ← Don't forget this!
)
```

## Related Files

**Frontend:**
- `frontend/composables/use-document-section-update.ts` - Composable for state management
- `frontend/components/issues/TipTapEditor.vue` - Rich text editor with selection menu
- `frontend/components/issues/TextSelectionModal.vue` - Modal for user instructions
- `frontend/components/issues/SkillFileDetailTab.vue` - Example implementation
- `frontend/components/issues/SpecPRDTab.vue` - Example implementation

**Backend:**
- `sleuth/apps/issues/orchestration/update_section_tool.py` - Unified tool for all document types
- `sleuth/apps/issues/utility/update_section_endpoint.py` - HTTP endpoint
- `sleuth/apps/issues/utility/markdown_section_finder.py` - Text matching with formatting
- `sleuth/apps/issues/orchestration/base_update_section_tool.py` - Base class with core logic
