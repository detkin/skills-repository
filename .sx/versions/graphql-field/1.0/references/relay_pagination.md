# Relay Pagination Patterns

Complete guide to implementing relay-style pagination in GraphQL fields.

## Basic Pattern

Relay pagination uses Connection/Node pattern with cursor-based navigation.

### Step 1: Define Node Type

The node is your GraphQL type:

```python
from sleuth.apps.common.gql.django_object_type import SleuthDjangoObjectType

class MyItemNode(SleuthDjangoObjectType):
    class Meta:
        model = MyItem
        fields = ("name", "status", "created_on")

    id = graphene.Field(graphene.NonNull(graphene.ID), source="gid")
```

### Step 2: Define Connection Type

```python
from sleuth.apps.common.gql.relay.connection import SleuthRelayConnection

class MyItemConnection(SleuthRelayConnection):
    class Meta:
        node = MyItemNode
        add_total_count_field = True  # Optional: adds totalCount to connection
```

**Options:**
- `add_total_count_field = True` - Adds `totalCount` field for UI pagination
- `add_total_count_field = False` - Omits count for performance

### Step 3: Define Connection Field

```python
from sleuth.apps.common.gql.relay.connection_field import SleuthConnectionField
from sleuth.apps.common.gql.relay.connection import SleuthRelayResult
from asgiref.sync import sync_to_async

class MyItemsConnectionField(SleuthConnectionField):
    def __init__(self) -> None:
        super().__init__(
            type_=graphene.NonNull(MyItemConnection),
            args=dict(
                status=graphene.Argument(graphene.String),
            ),
            resolver=self.resolve,
            max_page_size=100,  # Optional: limit page size
        )

    @staticmethod
    @sync_to_async
    def resolve(parent, info, status=None, **kwargs):
        # Build QuerySet
        queryset = MyItem.objects.filter(organization_id=parent.org_id)

        if status:
            queryset = queryset.filter(status=status)

        # Order for consistent pagination
        queryset = queryset.order_by("-created_on", "id")

        # Wrap in SleuthRelayResult
        return SleuthRelayResult(data=queryset)
```

**Key points:**
- Inherit from `SleuthConnectionField`
- Return `SleuthRelayResult(data=queryset)`
- Always order QuerySet for consistent cursors
- Use `max_page_size` to prevent abuse

### Step 4: Register Field

```python
# In graphql.py
from sleuth.graphql.api import Field

fields = [
    Field("my_items", MyItemsConnectionField()),
]

types = [
    MyItemNode,  # Register node type
]
```

## GraphQL Query Usage

Frontend queries paginated fields:

```graphql
query GetMyItems($first: Int, $after: String) {
  myItems(first: $first, after: $after) {
    edges {
      cursor
      node {
        id
        name
        status
      }
    }
    pageInfo {
      hasNextPage
      hasPreviousPage
      startCursor
      endCursor
    }
    totalCount  # If add_total_count_field = True
  }
}
```

## Advanced Patterns

### Custom Processing with process_raw_items_fn

Transform items before returning:

```python
def _process_items(items):
    """Process raw items before conversion to nodes."""
    # Add annotations, prefetch related, etc.
    return items.select_related("owner").prefetch_related("tags")

@staticmethod
@sync_to_async
def resolve(parent, info, **kwargs):
    queryset = MyItem.objects.filter(organization_id=parent.org_id)
    return SleuthRelayResult(
        data=queryset,
        process_raw_items_fn=_process_items
    )
```

### Filtering with Multiple Arguments

```python
class MyItemsConnectionField(SleuthConnectionField):
    def __init__(self) -> None:
        super().__init__(
            type_=graphene.NonNull(MyItemConnection),
            args=dict(
                status=graphene.Argument(graphene.String),
                owner_id=graphene.Argument(graphene.ID),
                search=graphene.Argument(graphene.String),
            ),
            resolver=self.resolve,
        )

    @staticmethod
    @sync_to_async
    def resolve(parent, info, status=None, owner_id=None, search=None, **kwargs):
        queryset = MyItem.objects.filter(organization_id=parent.org_id)

        if status:
            queryset = queryset.filter(status=status)

        if owner_id:
            owner_db_id = MyItem.id_from_gid(parent.org_id, owner_id)
            queryset = queryset.filter(owner_id=owner_db_id)

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )

        return SleuthRelayResult(data=queryset.order_by("-created_on"))
```

### Complex Ordering with Annotations

```python
from django.db.models import Case, When, Value, IntegerField, F

@staticmethod
@sync_to_async
def resolve(parent, info, **kwargs):
    queryset = MyItem.objects.filter(organization_id=parent.org_id).annotate(
        # Custom ordering: active items first, then by priority
        sort_order=Case(
            When(status="active", then=Value(0)),
            When(status="pending", then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        )
    ).order_by("sort_order", "-priority", "-created_on")

    return SleuthRelayResult(data=queryset)
```

### Union Queries (Multiple Model Types)

Combine results from multiple models:

```python
from django.db.models import Value, CharField

@staticmethod
@sync_to_async
def resolve(parent, info, **kwargs):
    # Annotate with type discriminator
    teams = Team.objects.filter(org_id=parent.org_id).annotate(
        item_type=Value("team", output_field=CharField())
    )

    users = User.objects.filter(org_id=parent.org_id).annotate(
        item_type=Value("user", output_field=CharField())
    )

    # Union queries
    combined = teams.union(users).order_by("name")

    return SleuthRelayResult(
        data=combined,
        process_raw_items_fn=_hydrate_union_items  # Convert back to models
    )

def _hydrate_union_items(items):
    """Re-fetch actual model instances from union results."""
    # Implementation depends on your needs
    pass
```

## Real Examples from Codebase

### Access Tokens (organization/gql_fields/access_tokens.py:38-76)

```python
class AccessTokenConnection(SleuthRelayConnection):
    class Meta:
        node = AccessTokenNode
        add_total_count_field = False

class AccessTokenField(SleuthConnectionField):
    def __init__(self) -> None:
        super().__init__(
            type_=graphene.NonNull(AccessTokenConnection),
            resolver=self.resolve,
        )

    @staticmethod
    @sync_to_async
    def resolve(root: Organization, info: SleuthGQLResolveInfo, **kwargs):
        access_tokens = AccessToken.objects.filter(
            organization=root, token_type=AccessTokenType.API_TOKEN
        ).order_by("id")
        return SleuthRelayResult(data=access_tokens)
```

### Teams with Complex Filtering (organization/gql_fields/teams.py:85-154)

Shows annotation-based ordering and parent-based filtering.

### Comments with Processing (review/graphql/comment.py:93-116)

Shows `process_raw_items_fn` usage for related data.

## Performance Considerations

### Always Add Order By

Relay cursors rely on consistent ordering:

```python
# Good
queryset.order_by("-created_on", "id")

# Bad - inconsistent cursor positions
queryset  # No ordering
```

### Use select_related/prefetch_related

Prevent N+1 queries:

```python
def _optimize_queryset(items):
    return items.select_related("owner", "workspace").prefetch_related("tags")

return SleuthRelayResult(data=queryset, process_raw_items_fn=_optimize_queryset)
```

### Set max_page_size

Prevent clients from requesting too many items:

```python
super().__init__(
    type_=MyConnection,
    resolver=self.resolve,
    max_page_size=100,  # Enforce maximum
)
```

## Troubleshooting

### Inconsistent Cursor Positions

**Problem:** Cursors point to wrong items between requests

**Solution:** Always include deterministic ordering with unique field (usually `id`):

```python
.order_by("-created_on", "id")  # id makes it deterministic
```

### totalCount Missing

**Problem:** `totalCount` field not available in query

**Solution:** Set `add_total_count_field = True` in Connection Meta:

```python
class MyConnection(SleuthRelayConnection):
    class Meta:
        node = MyNode
        add_total_count_field = True
```

### Performance Issues with Large Pages

**Problem:** Queries with `first: 1000` are slow

**Solution:** Add `max_page_size` limit:

```python
super().__init__(
    type_=MyConnection,
    max_page_size=100,
    ...
)
```
