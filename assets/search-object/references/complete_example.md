# Complete Example: Adding SpecDB and SessionDB to Search

This document walks through the complete implementation of adding two new object types (SpecDB and SessionDB) to search, based on [PR #3253](https://github.com/sleuth-io/pulse/pull/3253).

## Overview

This example demonstrates adding two related object types from the `sleuth/apps/issues` app to the search functionality:
- **SpecDB**: Technical specifications/requirements
- **SessionDB**: Development/work sessions

Both objects:
- Have a team relationship (linking to workspace via `team__workspace`)
- Use hash-based IDs instead of GIDs
- Don't have `LastViewed` tracking (use timestamp fields instead)
- Share similar patterns for implementation

## Step 1: Backend Implementation

### 1.1 Add Search Result Types

In [sleuth/apps/search/gql_fields.py](sleuth/apps/search/gql_fields.py), add the new enum values:

```python
class SearchResultType(graphene.Enum):
    REVIEW = "review"
    SURVEY = "survey"
    DASHBOARD = "dashboard"
    WORKSPACE = "workspace"
    SPEC = "spec"          # Added
    SESSION = "session"    # Added
```

### 1.2 Add Model Imports

At the top of `gql_fields.py`, add imports for the new models:

```python
from sleuth.apps.issues.models import SessionDB
from sleuth.apps.issues.models import SpecDB
```

### 1.3 Implement SpecDB QuerySet Functions

Add generator function:

```python
def _generate_specs_qs(
    org: Organization,
    result_type: SearchResultType | None,
    workspace_id: int | None,
    term: str | None,
) -> QuerySet[SpecDB]:
    if result_type and result_type != SearchResultType.SPEC:
        return SpecDB.objects.none()

    # Note: workspace relationship is through team
    specs_qs = SpecDB.objects.filter(
        org=org,
        **dict(team__workspace=workspace_id) if workspace_id else {}
    )

    if term:
        specs_qs = specs_qs.filter(title__icontains=term)

    specs_qs = specs_qs.distinct()

    return specs_qs
```

**Key points:**
- Filter by `team__workspace` (not direct workspace FK)
- Search against `title` field (not `name`)
- No `LastViewed` filtering logic

Add annotator function:

```python
def _annotate_specs_qs(
    specs_qs: QuerySet[SpecDB],
    fields: list[str]
) -> QuerySet[SpecDB, dict[str, Any]]:
    spec_marker_subquery = WorkspaceMarker.objects.filter(
        workspace=OuterRef("team__workspace")
    )

    annotated_specs = specs_qs.annotate(
        type=Value(SearchResultType.SPEC.value, output_field=CharField()),
        workspace_marker_type=Subquery(spec_marker_subquery.values("type")),
        workspace_marker_name=Subquery(spec_marker_subquery.values("name")),
        workspace_marker_color=Subquery(spec_marker_subquery.values("color")),
        workspace_raw_id=F("team__workspace"),
        workspace_name=F("team__workspace__name"),
        chain_count=Value(0, output_field=IntegerField()),
        last_viewed_on=F("meta_last_updated_on"),
        name=F("spec_key"),  # Use spec_key, not title
    ).values(*fields)

    return annotated_specs
```

**Key points:**
- `workspace_raw_id` uses `F("team__workspace")`
- `workspace_name` uses `F("team__workspace__name")`
- `last_viewed_on` uses model's timestamp field
- `name` mapped to `spec_key` (the display identifier)
- `chain_count` is 0 (no chaining for specs)

### 1.4 Implement SessionDB QuerySet Functions

Add generator function:

```python
def _generate_sessions_qs(
    org: Organization,
    result_type: SearchResultType | None,
    workspace_id: int | None,
    term: str | None,
) -> QuerySet[SessionDB]:
    if result_type and result_type != SearchResultType.SESSION:
        return SessionDB.objects.none()

    sessions_qs = SessionDB.objects.filter(
        org=org,
        **dict(team__workspace=workspace_id) if workspace_id else {}
    )

    if term:
        sessions_qs = sessions_qs.filter(name__icontains=term)

    sessions_qs = sessions_qs.distinct()

    return sessions_qs
```

**Same pattern as SpecDB but:**
- Filters against `name` field (sessions have name)
- Returns `SessionDB` queryset

Add annotator function:

```python
def _annotate_sessions_qs(
    sessions_qs: QuerySet[SessionDB],
    fields: list[str]
) -> QuerySet[SessionDB, dict[str, Any]]:
    session_marker_subquery = WorkspaceMarker.objects.filter(
        workspace=OuterRef("team__workspace")
    )

    annotated_sessions = sessions_qs.annotate(
        type=Value(SearchResultType.SESSION.value, output_field=CharField()),
        workspace_marker_type=Subquery(session_marker_subquery.values("type")),
        workspace_marker_name=Subquery(session_marker_subquery.values("name")),
        workspace_marker_color=Subquery(session_marker_subquery.values("color")),
        workspace_raw_id=F("team__workspace"),
        workspace_name=F("team__workspace__name"),
        chain_count=Value(0, output_field=IntegerField()),
        last_viewed_on=F("meta_last_updated_on"),
        hash=F("session_id"),
    ).values(*fields)

    return annotated_sessions
```

**Key differences from SpecDB:**
- `name` field is used as-is (not remapped)
- `hash` mapped to `session_id` (the unique identifier)
- No `spec_key` equivalent

### 1.5 Update Search Field Resolver

In the `SearchField.resolve()` method, add generation and annotation calls:

```python
@staticmethod
def resolve(
    _: None,
    info: GraphQLResolveInfo,
    term: str | None = None,
    result_type: SearchResultType | None = None,
    workspace_id: str | None = None,
    **kwargs: Any,
) -> SleuthRelayResult:
    org: Organization = info.context.org

    workspace_db_id: int | None = extract_raw_db_id(workspace_id, Workspace) if workspace_id else None

    fields = [
        "org_id",
        "id",
        "type",
        "workspace_raw_id",
        "workspace_name",
        "workspace_marker_type",
        "workspace_marker_name",
        "workspace_marker_color",
        "chain_count",
        "last_viewed_on",
        "name",
        "hash",
    ]

    workspaces_qs = _generate_workspaces_qs(org, info.context.user, result_type, workspace_db_id, term)
    workspaces = _annotate_workspaces_qs(workspaces_qs, info.context.user, fields)

    reviews_qs = _generate_reviews_qs(org, info.context.user, result_type, workspace_db_id, term)
    reviews = _annotate_reviews_qs(reviews_qs, info.context.user, fields)

    # Add specs
    specs_qs = _generate_specs_qs(org, result_type, workspace_db_id, term)
    specs = _annotate_specs_qs(specs_qs, fields)

    # Add sessions
    sessions_qs = _generate_sessions_qs(org, result_type, workspace_db_id, term)
    sessions = _annotate_sessions_qs(sessions_qs, fields)

    # Add to union
    data = workspaces.union(reviews).union(specs).union(sessions).order_by("-last_viewed_on", "name")

    return SleuthRelayResult(data=data, process_raw_items_fn=_process_search_results)
```

**Note:** The `fields` list didn't need changes - both new object types provide all required fields.

### 1.6 Update Result Processor

In `_process_search_results()`, handle the new ID formats:

```python
def _process_search_results(raw_search_results: list[dict]) -> list[dict]:
    search_results: list[dict] = []

    for item in raw_search_results:
        workspace_gid: str | None = None
        artifact_gid: str | None = None
        artifact_name: str | None = None

        workspace_gid = encode_gid(Workspace._gid_prefix, item["org_id"], item["workspace_raw_id"])

        if item["type"] in [
            SearchResultType.REVIEW.value,
            SearchResultType.SURVEY.value,
            SearchResultType.DASHBOARD.value,
        ]:
            artifact_gid = encode_gid(Review._gid_prefix, item["org_id"], item["id"])
            artifact_name = item["name"]
        elif item["type"] in [
            SearchResultType.SPEC.value,      # Added
            SearchResultType.SESSION.value,   # Added
        ]:
            # Use hash directly instead of encoding GID
            artifact_gid = item["hash"]
            artifact_name = item["name"]

        workspace_marker = None
        if item["workspace_marker_type"]:
            workspace_marker = WorkspaceMarker(
                type=item["workspace_marker_type"],
                name=item["workspace_marker_name"],
                color=item["workspace_marker_color"],
            )

        search_results.append(
            {
                **item,
                "workspace_id": workspace_gid,
                "artifact_id": artifact_gid,
                "artifact_name": artifact_name,
                "workspace_marker": workspace_marker,
            }
        )

    return search_results
```

**Key point:** Specs and Sessions use `item["hash"]` directly instead of encoding as GID.

## Step 2: Test Implementation

### 2.1 Create Test Factories

Create `sleuth/apps/issues/tests/factories.py`:

```python
import factory

from sleuth.apps.issues.session.models import SessionDB
from sleuth.apps.issues.specs.models import SpecDB
from sleuth.apps.issues.teamspace.models import IssuesTeamspaceDB
from sleuth.apps.organization.tests.factories import OrganizationFactory
from sleuth.apps.review.tests.factories import WorkspaceFactory
from sleuth.apps.tests.factories import LazyAttributeWithFaker
from sleuth.apps.tests.factories import lazy_attributeV2


class TeamspaceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = IssuesTeamspaceDB

    org = factory.SubFactory(OrganizationFactory)

    @lazy_attributeV2
    def workspace(self, **kwargs):
        kwargs["org"] = self.org
        return WorkspaceFactory(**kwargs)


class SpecFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SpecDB

    hash = factory.Sequence(lambda n: f"spec-hash-{n}")
    spec_key = factory.Sequence(lambda n: f"SD-SPEC-{n:03d}")
    title = LazyAttributeWithFaker(prefix="Spec", faker=factory.Faker("sentence"))
    original_prompt = LazyAttributeWithFaker(prefix="Prompt", faker=factory.Faker("sentence"))
    org = factory.SubFactory(OrganizationFactory)

    @lazy_attributeV2
    def team(self, **kwargs):
        kwargs["org"] = self.org
        return TeamspaceFactory(**kwargs)


class SessionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SessionDB

    session_id = factory.Sequence(lambda n: f"session-{n}")
    name = LazyAttributeWithFaker(prefix="Session", faker=factory.Faker("sentence"))
    issue_key = factory.Sequence(lambda n: f"ISSUE-{n}")
    github_repo = factory.Faker("word")
    github_org = factory.Faker("word")
    org = factory.SubFactory(OrganizationFactory)

    @lazy_attributeV2
    def team(self, **kwargs):
        kwargs["org"] = self.org
        return TeamspaceFactory(**kwargs)
```

**Key points:**
- `TeamspaceFactory` ensures `org` is consistent across related objects
- `SpecFactory` generates sequential spec keys and unique hashes
- `SessionFactory` generates session IDs and issue keys
- Both use `@lazy_attributeV2` to inherit org from parent factories

### 2.2 Update Test Data Generator

In `sleuth/apps/search/tests/test_search.py`, update `_generate_test_data()`:

```python
def _generate_test_data():
    from sleuth.apps.issues.tests.factories import TeamspaceFactory
    from sleuth.apps.review.tests.factories import WorkspaceFactory

    workspace_1 = WorkspaceFactory(name="Banana Workspace")
    org = workspace_1.org
    workspace_2 = WorkspaceFactory(name="Strawberry Workspace", org=org)

    review_1_old = ReviewFactory(name="Banana Review", workspace=workspace_1, status=ReviewStatus.PUBLISHED)
    review_1 = repeat_review(review_1_old, review_1_old.owner)
    review_2 = ReviewFactory(name="Strawberry Review", workspace=workspace_2)

    survey_1 = ReviewFactory(name="Banana Survey", review_type=ReviewType.SURVEY, workspace=workspace_1)
    survey_2 = ReviewFactory(name="Strawberry Survey", review_type=ReviewType.SURVEY, workspace=workspace_2)

    dashboard = ReviewFactory(name="Banana Dashboard", review_type=ReviewType.DASHBOARD, workspace=workspace_1)

    not_org_owner = UserFactory(org=org)
    add_member(org, not_org_owner)

    # Create LastViewed records for existing objects...
    LastViewedFactory(review=survey_2, on=datetime(2025, 1, 10))
    LastViewedFactory(review=review_1, on=datetime(2025, 1, 10))
    # ... etc

    # Create Specs and Sessions for the new search types
    teamspace_1 = TeamspaceFactory(org=org, workspace=workspace_1)
    teamspace_2 = TeamspaceFactory(org=org, workspace=workspace_2)

    spec_1 = SpecFactory(
        title="Banana Spec",
        spec_key="SD-SPEC-001",
        hash="spec-hash-1",
        org=org,
        team=teamspace_1
    )
    spec_2 = SpecFactory(
        title="Strawberry Spec",
        spec_key="SD-SPEC-002",
        hash="spec-hash-2",
        org=org,
        team=teamspace_2
    )

    session_1 = SessionFactory(
        name="Banana Session",
        session_id="session-1",
        org=org,
        team=teamspace_1,
        issue_key="BAN-1"
    )
    session_2 = SessionFactory(
        name="Strawberry Session",
        session_id="session-2",
        org=org,
        team=teamspace_2,
        issue_key="STR-1"
    )

    return (
        org,
        not_org_owner,
        workspace_1,
        workspace_2,
        review_1,
        review_2,
        survey_1,
        survey_2,
        dashboard,
        spec_1,
        spec_2,
        session_1,
        session_2,
    )
```

**Key points:**
- Create teamspaces first, linking to existing workspaces
- Create specs and sessions with explicit hash/session_id values
- Follow "Banana"/"Strawberry" naming pattern for consistency
- Return all new objects in the tuple

### 2.3 Update Test Assertions

#### Main Search Test

Update to include new objects in default results:

```python
with subtests.test("Returns list of viewed workspaces, surveys and reviews, sorted by last viewed, then by name"):
    result = execute_gql_query(GQL_QUERY, org=org)
    assert result == {
        "data": {
            "search": {
                "nodes": [
                    # Sessions/Specs appear first (newest timestamps)
                    {"workspaceName": session_2.team.workspace.name, "artifactName": session_2.name},
                    {"workspaceName": session_1.team.workspace.name, "artifactName": session_1.name},
                    {"workspaceName": spec_2.team.workspace.name, "artifactName": spec_2.spec_key},
                    {"workspaceName": spec_1.team.workspace.name, "artifactName": spec_1.spec_key},
                    # Then existing objects...
                    {"workspaceName": review_1.workspace.name, "artifactName": review_1.name},
                    {"workspaceName": survey_2.workspace.name, "artifactName": survey_2.name},
                    # ... etc
                ]
            }
        }
    }
```

#### Term Filtering Test

```python
with subtests.test("Supports filtering by term"):
    result = execute_gql_query(GQL_QUERY, org=org, variables={"term": "Banana"})

    assert result == {
        "data": {
            "search": {
                "nodes": [
                    {"workspaceName": "Banana Workspace", "artifactName": "Banana Session"},
                    {"workspaceName": "Banana Workspace", "artifactName": "SD-SPEC-001"},
                    {"workspaceName": "Banana Workspace", "artifactName": "Banana Review"},
                    {"workspaceName": "Banana Workspace", "artifactName": None},
                    {"workspaceName": "Banana Workspace", "artifactName": "Banana Survey"},
                    {"workspaceName": "Banana Workspace", "artifactName": "Banana Dashboard"},
                ]
            }
        }
    }
```

**Note:** Spec displays `spec_key` ("SD-SPEC-001") not title.

#### Type Filtering Test

Add new subtest for SPEC type:

```python
with subtests.test("Supports filtering by result type"):
    # ... existing SURVEY, DASHBOARD tests ...

    result = execute_gql_query(GQL_QUERY, org=org, variables={"resultType": "SPEC"})

    assert result == {
        "data": {
            "search": {
                "nodes": [
                    {"workspaceName": workspace_2.name, "artifactName": "SD-SPEC-002"},
                    {"workspaceName": workspace_1.name, "artifactName": "SD-SPEC-001"},
                ]
            }
        }
    }
```

#### All Fields Test

Add full object representation:

```python
with subtests.test("Exposes result type, artifact name + id, workspace name + id + marker and last viewed"):
    result = execute_gql_query(GQL_QUERY_ALL_FIELDS, org=org, variables={"term": "Banana"})

    assert result == {
        "data": {
            "search": {
                "nodes": [
                    {
                        "type": "SESSION",
                        "workspaceId": session_1.team.workspace.gid,
                        "workspaceName": session_1.team.workspace.name,
                        "artifactId": session_1.session_id,  # Note: hash, not GID
                        "artifactName": session_1.name,
                        "workspaceMarker": {
                            "color": "gray",
                            "name": "tag",
                            "type": "ICON",
                        },
                        "chainCount": 0,
                        "lastViewedOn": session_1.meta_last_updated_on.isoformat(),
                    },
                    {
                        "type": "SPEC",
                        "workspaceId": spec_1.team.workspace.gid,
                        "workspaceName": spec_1.team.workspace.name,
                        "artifactId": spec_1.hash,  # Note: hash, not GID
                        "artifactName": spec_1.spec_key,  # Note: spec_key, not title
                        "workspaceMarker": {
                            "color": "gray",
                            "name": "tag",
                            "type": "ICON",
                        },
                        "chainCount": 0,
                        "lastViewedOn": spec_1.meta_last_updated_on.isoformat(),
                    },
                    # ... other Banana objects ...
                ]
            }
        }
    }
```

#### Pagination Test

Update total count to include new objects:

```python
with subtests.test("Exposes standard pagination fields"):
    result = execute_gql_query(
        """
        query {
            search(first: 3) {
                totalCount
                pageInfo {
                    hasNextPage
                    hasPreviousPage
                }
            }
        }
        """,
        org=org,
    )

    assert result == {
        "data": {
            "search": {
                "totalCount": 11,  # Updated from 7 (added 4 new objects)
                "pageInfo": {
                    "hasNextPage": True,
                    "hasPreviousPage": False,
                },
            }
        }
    }
```

## Step 3: Frontend Updates

### 3.1 Add Icon Assets

Add four icon files:

**frontend/assets/used-icons/duotone-solid/folder-gear.svg** (for Specs):
```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <!-- SVG path content -->
</svg>
```

**frontend/assets/used-icons/light/folder-gear.svg** (for Specs):
```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <!-- SVG path content -->
</svg>
```

**frontend/assets/used-icons/duotone-solid/square-kanban.svg** (for Sessions):
```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 448 512">
  <!-- SVG path content -->
</svg>
```

**frontend/assets/used-icons/light/square-kanban.svg** (for Sessions):
```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 448 512">
  <!-- SVG path content -->
</svg>
```

### 3.2 Update Search Filter Buttons

In `frontend/components/navigation/Search.vue`:

```typescript
const filterButtons = computed(() => [
  {
    label: 'Reviews',
    icon: 'light:file',
    cb: () => toggleFilter(SearchResultType.Review),
    active: searchType.value === SearchResultType.Review,
  },
  {
    label: 'Surveys',
    icon: 'light:clipboard-check',
    cb: () => toggleFilter(SearchResultType.Survey),
    active: searchType.value === SearchResultType.Survey,
  },
  {
    label: 'Dashboards',
    icon: 'light:square-poll-vertical',
    cb: () => toggleFilter(SearchResultType.Dashboard),
    active: searchType.value === SearchResultType.Dashboard,
  },
  {
    label: 'Specs',  // Added
    icon: 'light:folder-gear',
    cb: () => toggleFilter(SearchResultType.Spec),
    active: searchType.value === SearchResultType.Spec,
  },
  {
    label: 'Tasks',  // Added (displayed as "Tasks" not "Sessions")
    icon: 'light:square-kanban',
    cb: () => toggleFilter(SearchResultType.Session),
    active: searchType.value === SearchResultType.Session,
  },
  {
    label: 'Teamspaces',
    icon: 'light:folder',
    cb: () => toggleFilter(SearchResultType.Workspace),
    active: searchType.value === SearchResultType.Workspace,
  },
])
```

### 3.3 Update Search Item Icon Mapping

In `frontend/components/navigation/SearchItem.vue`:

```typescript
const icon = computed(() => ({
  [SearchResultType.Review]: 'light:file',
  [SearchResultType.Survey]: 'light:clipboard-check',
  [SearchResultType.Dashboard]: 'light:square-poll-vertical',
  [SearchResultType.Spec]: 'light:folder-gear',        // Added
  [SearchResultType.Session]: 'light:square-kanban',   // Added
  [SearchResultType.Workspace]: null,
})[props.type])
```

### 3.4 Update Artifact Routing

In `frontend/utils/artifact.ts`:

**Import IssuesArtifactType:**
```typescript
import { IssuesArtifactType } from '~/api'
```

**Add route mappings:**
```typescript
export function getRouteForArtifact(
  artifactId: string,
  workspaceId: string,
  type: ReviewType | IssuesArtifactType,
): RouteLocationRaw {
  return {
    [ReviewType.Review]: {
      name: 'teamspace-workspaceId-reviews-reviewId' as const,
      params: { workspaceId, reviewId: artifactId },
    },
    [ReviewType.Survey]: {
      name: 'teamspace-workspaceId-surveys-surveyId' as const,
      params: { workspaceId, surveyId: artifactId },
    },
    [ReviewType.Dashboard]: {
      name: 'teamspace-workspaceId-dashboards-dashboardId' as const,
      params: { workspaceId, dashboardId: artifactId },
    },
    [IssuesArtifactType.Spec]: {  // Added
      name: 'issues-teams-teamId-specs-hash' as const,
      params: { teamId: workspaceId, hash: artifactId },
    },
    [IssuesArtifactType.Task]: {  // Added
      name: 'issues-teams-teamId-sessions-id' as const,
      params: { teamId: workspaceId, id: artifactId },
    },
  }[type]
}
```

**Add type conversions:**
```typescript
export function searchResultTypeToReviewType(
  searchResultType: SearchResultType,
): ReviewType | IssuesArtifactType {
  return {
    [SearchResultType.Dashboard]: ReviewType.Dashboard,
    [SearchResultType.Review]: ReviewType.Review,
    [SearchResultType.Survey]: ReviewType.Survey,
    [SearchResultType.Spec]: IssuesArtifactType.Spec,      // Added
    [SearchResultType.Session]: IssuesArtifactType.Task,   // Added
  }[searchResultType]
}
```

**Add icon mappings:**
```typescript
export const objectTypeIconMapping = {
  [SearchResultType.Review]: {
    bigIcon: 'duotone-solid:file',
    smallIcon: 'regular:file',
    color: 'text-blue-400',
  },
  [SearchResultType.Survey]: {
    bigIcon: 'duotone-solid:clipboard-check',
    smallIcon: 'regular:clipboard-check',
    color: 'text-purple-400',
  },
  [SearchResultType.Dashboard]: {
    bigIcon: 'duotone-solid:square-poll-vertical',
    smallIcon: 'regular:square-poll-vertical',
    color: 'text-green-400',
  },
  [SearchResultType.Spec]: {  // Added
    bigIcon: 'duotone-solid:folder-gear',
    smallIcon: 'regular:folder-gear',
    color: 'text-yellow-400',
  },
  [SearchResultType.Session]: {  // Added
    bigIcon: 'duotone-solid:square-kanban',
    smallIcon: 'regular:chart-kanban',
    color: 'text-jumbo-400',
  },
  [SearchResultType.Workspace]: {
    bigIcon: '',
    smallIcon: '',
    color: '',
  },
}
```

## Key Learnings

### 1. Team/Workspace Relationship Pattern

When objects relate to workspace through a team foreign key:
- Use `team__workspace` in filters
- Use `F("team__workspace")` for annotations
- The workspace marker subquery needs `OuterRef("team__workspace")`

### 2. Hash-Based IDs vs GIDs

Objects using hash IDs need special handling:
- Store hash in the `hash` field during annotation
- Update `_process_search_results()` to use hash directly
- Frontend routing uses hash as the ID parameter

### 3. Display Name vs Internal Name

For objects with multiple name fields:
- Specs: Use `spec_key` for display, `title` for searching
- Sessions: Use `name` for both
- Map appropriately in annotate function

### 4. Timestamp Field Selection

Without `LastViewed` tracking:
- Use `meta_last_updated_on` for sorting
- Objects appear in search regardless of user viewing history
- Still filterable by search term

### 5. Frontend Type Mapping

Need three separate type mappings:
- SearchResultType → IssuesArtifactType (for routing logic)
- SearchResultType → Icon name (for display)
- SearchResultType → Color class (for styling)

### 6. Test Data Consistency

Follow existing naming patterns:
- "Banana" prefix for workspace 1 objects
- "Strawberry" prefix for workspace 2 objects
- Maintains predictable sorting in test assertions

## Common Pitfalls

1. **Forgetting to add hash field annotation** - Results in union query errors
2. **Wrong workspace field path** - Use `team__workspace` not `workspace`
3. **Using title instead of spec_key** - Display shows wrong identifier
4. **Not updating all frontend locations** - Icons/routing don't work
5. **Incorrect test assertion ordering** - New objects appear first due to timestamps
