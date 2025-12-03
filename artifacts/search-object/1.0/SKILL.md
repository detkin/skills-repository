---
name: search-object
description: This skill should be used when extending search with a new object type. Guides through adding new searchable objects to the GraphQL search field including backend, tests, schema generation, and UI updates.
---

# Search Object Extension

## Overview

Extend the GraphQL search functionality to include a new object type. This skill covers the complete workflow from backend implementation through UI integration.

## When to Use This Skill

Use when the user requests:

- "Add [object] to search"
- "Make [object] searchable"
- "Extend search with [object]"
- "Allow users to search for [object]"

## Complete Workflow

When adding a new object type to search, follow these steps in order:

### Step 1: Extend Backend Search Implementation

All search code lives in [sleuth/apps/search/](sleuth/apps/search/).

#### 1.1 Add Search Result Type

In [sleuth/apps/search/gql_fields.py:31-37](sleuth/apps/search/gql_fields.py#L31-L37), add your new type to the `SearchResultType` enum:

```python
class SearchResultType(graphene.Enum):
    REVIEW = "review"
    SURVEY = "survey"
    DASHBOARD = "dashboard"
    WORKSPACE = "workspace"
    SPEC = "spec"
    SESSION = "session"
    YOUR_NEW_TYPE = "your_new_type"  # Add this
```

#### 1.2 Implement QuerySet Generator Function

Create `_generate_<objects>_qs()` function following this pattern:

```python
def _generate_<objects>_qs(
    org: Organization,
    result_type: SearchResultType | None,
    workspace_id: int | None,
    term: str | None,
) -> QuerySet[YourModel]:
    # Early return if filtering for different type
    if result_type and result_type != SearchResultType.YOUR_NEW_TYPE:
        return YourModel.objects.none()

    # Base queryset filtered by org
    objects_qs = YourModel.objects.filter(
        org=org,
        **dict(workspace_id=workspace_id) if workspace_id else {}
    )

    # Filter by search term if provided
    if term:
        objects_qs = objects_qs.filter(name__icontains=term)

    objects_qs = objects_qs.distinct()

    return objects_qs
```

**Key points:**

- Always filter by `org` first
- Support optional `workspace_id` filtering
- Support optional `term` filtering (usually against name/title field, but could be different depending on source model)
- Return `.none()` if filtering for different result type
- Call `.distinct()` before returning

See [gql_fields.py:260-276](sleuth/apps/search/gql_fields.py#L260-L276) for SpecDB example.

#### 1.3 Implement QuerySet Annotator Function

Create `_annotate_<objects>_qs()` function to normalize fields:

```python
def _annotate_<objects>_qs(
    objects_qs: QuerySet[YourModel],
    fields: list[str]
) -> QuerySet[YourModel, dict[str, Any]]:
    marker_subquery = WorkspaceMarker.objects.filter(
        workspace=OuterRef("your_workspace_id_field")
    )

    annotated_objects = objects_qs.annotate(
        type=Value(SearchResultType.YOUR_NEW_TYPE.value, output_field=CharField()),
        workspace_marker_type=Subquery(marker_subquery.values("type")),
        workspace_marker_name=Subquery(marker_subquery.values("name")),
        workspace_marker_color=Subquery(marker_subquery.values("color")),
        workspace_raw_id=F("your_workspace_id_field"),
        workspace_name=F("your_workspace_name_field"),
        chain_count=Value(0, output_field=IntegerField()),
        last_viewed_on=F("your_timestamp_field"),
        name=F("your_name_field"),
        hash=F("your_hash_field"),  # Or Value("", ...) if no hash
    ).values(*fields)

    return annotated_objects
```

**Required annotations** (must match the `fields` list):

- `type`: SearchResultType value for this object
- `workspace_marker_type/name/color`: Workspace marker info via subquery
- `workspace_raw_id`: The raw database ID of the workspace
- `workspace_name`: Name of the workspace
- `chain_count`: Number of items in chain (usually 0, only relevant for Reviews)
- `last_viewed_on`: Timestamp for sorting results
- `name`: Display name for the object
- `hash`: Unique identifier (or empty string if using regular ID)
- `id`: Database ID (usually already present)
- `org_id`: Organization ID (usually already present)

See [gql_fields.py:279-294](sleuth/apps/search/gql_fields.py#L279-L294) for SpecDB example.

#### 1.4 Update Search Field Resolver

In the `SearchField.resolve()` method around [gql_fields.py:154-160](sleuth/apps/search/gql_fields.py#L154-L160):

1. Generate your queryset
2. Annotate it
3. Add to the union

```python
# Add your object type
your_objects_qs = _generate_<objects>_qs(org, result_type, workspace_db_id, term)
your_objects = _annotate_<objects>_qs(your_objects_qs, fields)

# Add to union
data = (
    workspaces.union(reviews)
    .union(specs)
    .union(sessions)
    .union(your_objects)  # Add here
    .order_by("-last_viewed_on", "name")
)
```

#### 1.5 Update Result Processor (if needed)

If your object uses a special ID format (like hash instead of GID), update `_process_search_results()` around [gql_fields.py:80-85](sleuth/apps/search/gql_fields.py#L80-L85):

```python
elif item["type"] == SearchResultType.YOUR_NEW_TYPE.value:
    artifact_gid = item["hash"]  # or encode_gid(...)
    artifact_name = item["name"]
```

### Step 2: Add Test Coverage

Tests live in [sleuth/apps/search/tests/test_search.py](sleuth/apps/search/tests/test_search.py).

#### 2.1 Create Test Factories (if needed)

If factories don't exist for your model, create them in your app's `tests/factories.py` following factoryboy patterns. See [sleuth/apps/issues/tests/factories.py](sleuth/apps/issues/tests/factories.py) for examples.

#### 2.2 Update Test Data Generator

In `_generate_test_data()` around [test_search.py:101-115](sleuth/apps/search/tests/test_search.py#L101-L115):

```python
# Create test objects
your_object_1 = YourModelFactory(
    name="Banana Thing",
    org=org,
    workspace=workspace_1
)
your_object_2 = YourModelFactory(
    name="Strawberry Thing",
    org=org,
    workspace=workspace_2
)

# Add to return tuple
return (
    org, not_org_owner, workspace_1, workspace_2,
    review_1, review_2, survey_1, survey_2, dashboard,
    spec_1, spec_2, session_1, session_2,
    your_object_1, your_object_2,  # Add here
)
```

#### 2.3 Update Test Assertions

Update test assertions to include your new objects in expected results:

1. **Main search test** - Add to default results around [test_search.py:156-168](sleuth/apps/search/tests/test_search.py#L156-L168)
2. **Term filtering test** - Add to "Banana" filtered results around [test_search.py:197-204](sleuth/apps/search/tests/test_search.py#L197-L204)
3. **Type filtering test** - Add new subtest for your type around [test_search.py:235-246](sleuth/apps/search/tests/test_search.py#L235-L246)
4. **All fields test** - Add full object details around [test_search.py:289-303](sleuth/apps/search/tests/test_search.py#L289-L303)
5. **Pagination test** - Update total count around [test_search.py:274](sleuth/apps/search/tests/test_search.py#L274)

**Example type filter subtest:**

```python
result = execute_gql_query(GQL_QUERY, org=org, variables={"resultType": "YOUR_NEW_TYPE"})

assert result == {
    "data": {
        "search": {
            "nodes": [
                {"workspaceName": workspace_2.name, "artifactName": "Strawberry Thing"},
                {"workspaceName": workspace_1.name, "artifactName": "Banana Thing"},
            ]
        }
    }
}
```

#### 2.4 Run Tests

```bash
uv run ./bin/test.sh --keep-db sleuth/apps/search/tests/test_search.py
```

Fix any failures before proceeding.

### Step 3: Regenerate GraphQL Schema and Types

After backend changes are complete and tested:

```bash
make generate-gql-schema-and-types
```

This updates the GraphQL schema and TypeScript types for the frontend.

### Step 4: Update Frontend UI

Frontend changes are needed in multiple locations to display and filter the new object type.

#### 4.1 Add Icon Assets

Add SVG icons in two styles to [frontend/assets/used-icons/](frontend/assets/used-icons/):

- `duotone-solid/<icon-name>.svg` - For larger displays
- `light/<icon-name>.svg` - For smaller displays

See commit [ed051dd24](https://github.com/sleuth-io/pulse/pull/3253/commits/ed051dd241d277413b47201e4f47b24e5af8770d) for examples.

#### 4.2 Update Search Filter Buttons

In [frontend/components/navigation/Search.vue:104-115](frontend/components/navigation/Search.vue#L104-L115), add filter button:

```typescript
{
  label: 'Your Objects',
  icon: 'light:your-icon-name',
  cb: () => toggleFilter(SearchResultType.YourNewType),
  active: searchType.value === SearchResultType.YourNewType,
},
```

#### 4.3 Update Search Item Display

In [frontend/components/navigation/SearchItem.vue:24-30](frontend/components/navigation/SearchItem.vue#L24-L30), add icon mapping:

```typescript
const icon = computed(
  () =>
    ({
      [SearchResultType.Review]: "light:file",
      [SearchResultType.Survey]: "light:clipboard-check",
      [SearchResultType.Dashboard]: "light:square-poll-vertical",
      [SearchResultType.Spec]: "light:folder-gear",
      [SearchResultType.Session]: "light:square-kanban",
      [SearchResultType.YourNewType]: "light:your-icon-name", // Add here
      [SearchResultType.Workspace]: null,
    }[props.type])
);
```

#### 4.4 Update Artifact Routing

In [frontend/utils/artifact.ts](frontend/utils/artifact.ts), add two mappings:

**Import IssuesArtifactType** and extend it with a new enum value for the new object:

```typescript
import { IssuesArtifactType } from "~/api";
```

**Add route mapping** around [artifact.ts:104-111](frontend/utils/artifact.ts#L104-L111):

```typescript
[YourArtifactType.YourType]: {
  name: 'your-route-name' as const,
  params: { workspaceId, yourIdParam: artifactId },
},
```

**Add type conversion** around [artifact.ts:122-125](frontend/utils/artifact.ts#L122-L125):

```typescript
[SearchResultType.YourNewType]: YourArtifactType.YourType,
```

**Add icon mapping** around [artifact.ts:143-154](frontend/utils/artifact.ts#L143-L154):

```typescript
[SearchResultType.YourNewType]: {
  bigIcon: 'duotone-solid:your-icon-name',
  smallIcon: 'regular:your-icon-name',  // Or light: prefix
  color: 'text-your-color-400',
},
```

### Step 5: Validate Changes

#### 5.1 Run Backend Tests

```bash
uv run pytest --reuse-db sleuth/apps/search/tests/test_search.py
```

#### 5.2 Run Code Quality Checks

```bash
make check-types  # mypy and black
make lint-py      # pylint
```

#### 5.3 Test Frontend

- Start dev server and test search functionality
- Verify new filter button appears
- Verify objects appear in search results
- Verify clicking results navigates correctly

## Common Patterns

### For Objects with Team/Workspace Relationship

If your object relates to workspace through a team:

```python
# In generator
objects_qs = YourModel.objects.filter(
    org=org,
    **dict(team__workspace=workspace_id) if workspace_id else {}
)

# In annotator
workspace_raw_id=F("team__workspace"),
workspace_name=F("team__workspace__name"),
```

See [gql_fields.py:269](sleuth/apps/search/gql_fields.py#L269) and [gql_fields.py:287-288](sleuth/apps/search/gql_fields.py#L287-L288) for examples.

### For Objects with Direct Workspace Relationship

If your object has direct workspace FK:

```python
# In generator
objects_qs = YourModel.objects.filter(
    org=org,
    **dict(workspace_id=workspace_id) if workspace_id else {}
)

# In annotator
workspace_raw_id=F("workspace_id"),
workspace_name=F("workspace__name"),
```

See [gql_fields.py:175](sleuth/apps/search/gql_fields.py#L175) and [gql_fields.py:196-197](sleuth/apps/search/gql_fields.py#L196-L197) for examples.

### For Objects with Last Viewed Tracking

If your object has `LastViewed` tracking (like Reviews):

```python
def _generate_<objects>_qs(...):
    # ...
    if term:
        objects_qs = objects_qs.filter(name__icontains=term)
    else:
        # Only show viewed objects unless searching
        objects_qs = objects_qs.filter(
            last_viewed__user=user,
            last_viewed__isnull=False
        )
    # ...

def _annotate_<objects>_qs(...):
    last_viewed_subquery = LastViewed.objects.filter(
        your_model=OuterRef("id"),
        user=user
    )

    annotated_objects = objects_qs.annotate(
        # ...
        last_viewed_on=Subquery(last_viewed_subquery.values("on")),
        # ...
    )
```

See [gql_fields.py:229-232](sleuth/apps/search/gql_fields.py#L229-L232) and [gql_fields.py:243](sleuth/apps/search/gql_fields.py#L243) for examples.

### For Objects without Last Viewed Tracking

Use the model's timestamp field:

```python
last_viewed_on=F("meta_last_updated_on"),  # or created_at, etc.
```

See [gql_fields.py:290](sleuth/apps/search/gql_fields.py#L290) for example.

## Troubleshooting

### Test Failures

**"Factory not found"**

- Create factory in your app's `tests/factories.py`
- See `references/factory_patterns.md` for examples

**"Annotation field mismatch"**

- Ensure all fields in the `fields` list are annotated
- Check field names match exactly
- Verify types match (CharField, IntegerField, etc.)

**"Union query incompatible"**

- All unioned querysets must have identical field names and types
- Check `.values(*fields)` includes all required fields

### Schema Generation Fails

```bash
# Check for Python errors first
make check-types
make lint-py

# Look for GraphQL schema errors
make generate-gql-schema-and-types
```

Common issues:

- Missing imports in `gql_fields.py`
- Type mismatches in annotate functions
- Invalid GraphQL enum values

### Frontend Routing Issues

**Objects don't navigate correctly**

- Verify route name exists in router config
- Check param names match route definition
- Ensure `artifactId` format matches expected format (GID vs hash vs plain ID)

**Icons don't appear**

- Verify SVG files exist in `used-icons/` directories
- Check icon names match in all locations (Search.vue, SearchItem.vue, artifact.ts)
- Restart dev server after adding new SVG assets

## Reference

See `references/complete_example.md` for a detailed walkthrough of adding SpecDB and SessionDB objects to search, including all code changes and test updates.
