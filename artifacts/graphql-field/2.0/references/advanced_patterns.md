# Advanced GraphQL Patterns

Advanced patterns for data loaders, dynamic types, interfaces, and context extensions.

## Data Loaders

Data loaders solve the N+1 query problem by batching database queries.

### Basic DataLoader Pattern

```python
from sleuth.apps.common.gql.data_loader import SleuthDataLoader
from asgiref.sync import sync_to_async

class ItemsByOwnerLoader(SleuthDataLoader[int, list[Item]]):
    """Load items grouped by owner ID."""

    @sync_to_async
    def load_fn(self, owner_ids: list[int]) -> Sequence[list[Item]]:
        """Batch load items for multiple owners."""
        # Single query for all owners
        items_by_owner = defaultdict(list)

        items = Item.objects.filter(owner_id__in=owner_ids).select_related("workspace")

        for item in items:
            items_by_owner[item.owner_id].append(item)

        # Return in same order as keys
        return [items_by_owner.get(owner_id, []) for owner_id in owner_ids]
```

**Key points:**
- Inherit from `SleuthDataLoader[KeyType, ValueType]`
- Implement `load_fn()` that takes list of keys
- Return values in same order as input keys
- Use `@sync_to_async` for DB operations

### Scalar DataLoader (One Value Per Key)

```python
class CommentCountLoader(SleuthDataLoader[int, int]):
    """Load comment counts for items."""

    def __init__(self, target_type: type[Item]):
        super().__init__()
        self._target_type = target_type

    @sync_to_async
    def load_fn(self, target_ids: list[int]) -> Sequence[int]:
        """Batch load comment counts."""
        # Aggregate query
        counts = (
            Comment.objects
            .filter(target_id__in=target_ids, target_type=self._target_type.__name__)
            .values("target_id")
            .annotate(count=Count("id"))
        )

        count_by_id = {item["target_id"]: item["count"] for item in counts}

        # Return count for each ID (0 if not found)
        return [count_by_id.get(target_id, 0) for target_id in target_ids]
```

### Context Mixin for DataLoaders

Make loaders available in GraphQL context:

```python
# sleuth/apps/<app>/gql_loaders/gql_context.py
from functools import cached_property
from sleuth.graphql.api import GQLContext

class GQL<App>ContextMixin:
    """Extend GraphQL context with app-specific loaders."""

    @cached_property
    def items_by_owner_loader(self) -> ItemsByOwnerLoader:
        return ItemsByOwnerLoader()

    @cached_property
    def comment_count_loader(self) -> CommentCountLoader:
        return CommentCountLoader(target_type=Item)
```

Register in `graphql.py`:

```python
# sleuth/apps/<app>/graphql.py
from sleuth.apps.<app>.gql_loaders.gql_context import GQL<App>ContextMixin

context = GQL<App>ContextMixin
```

**Auto-discovery:** The schema builder automatically discovers and mixes context classes.

### Using DataLoaders in Resolvers

```python
class ItemOwnerType(SleuthDjangoObjectType):
    class Meta:
        model = User
        fields = ("id", "name", "email")

    items = graphene.List(graphene.NonNull(ItemType), required=True)

    async def resolve_items(self, info):
        """Load items for this owner using DataLoader."""
        # Single batched query for all owners in the response
        items = await info.context.items_by_owner_loader.load(self.id)
        return items

class ItemType(SleuthDjangoObjectType):
    class Meta:
        model = Item
        fields = ("name", "status")

    comments_count = graphene.Int(required=True)

    async def resolve_comments_count(self, info):
        """Load comment count using DataLoader."""
        count = await info.context.comment_count_loader.load(self.id)
        return count
```

**Without loader (N+1 problem):**
```python
# ❌ BAD - Query per item
def resolve_comments_count(self, info):
    return self.comments.count()  # Executes query per item
```

**With loader:**
```python
# ✅ GOOD - Single batched query
async def resolve_comments_count(self, info):
    return await info.context.comment_count_loader.load(self.id)
```

## Dynamic Type Building

Use `build_dynamic_type()` for types with complex inheritance and interfaces.

### Basic Pattern

```python
from sleuth.graphql.types import build_dynamic_type

# Define base type with core fields
class ItemTypeBase(SleuthDjangoObjectType):
    class Meta:
        model = Item
        fields = ("name", "status", "created_on")

    id = graphene.Field(graphene.NonNull(graphene.ID), source="gid")

# Build final type with interfaces and dynamic fields
ItemType = build_dynamic_type(
    "ItemType",
    parent_type=ItemTypeBase,
    model=Item,
    fields=("name", "status", "created_on"),
    interfaces=(CommentableMixinGqlType, UserScopedMixinGqlType),
)
```

**Benefits:**
- Separates base definition from dynamic extensions
- Allows other modules to inject fields via `type_fields`
- Supports interface composition
- Enables field extension system

### With Parent Type

```python
class ReviewTypeBase(graphene.ObjectType):
    """Base fields for all review types."""
    title = graphene.Field(graphene.String, required=True)
    status = graphene.Field(graphene.String, required=True)

ReviewType = build_dynamic_type(
    "ReviewType",
    parent_type=ReviewTypeBase,
    model=Review,
    fields=("title", "status", "owner", "workspace"),
    interfaces=(
        AssessableMixinGqlType,
        CommentableMixinGqlType,
        UserScopedMixinGqlType,
    ),
)
```

### Field Selection

Only expose specific model fields:

```python
# Only expose safe fields
SafeUserType = build_dynamic_type(
    "SafeUserType",
    parent_type=UserTypeBase,
    model=User,
    fields=("id", "name", "email"),  # NOT password, tokens, etc.
    interfaces=(),
)
```

## Interface Patterns

Interfaces define shared fields across multiple types.

### Defining Interfaces

```python
class CommentableMixinGqlType(graphene.Interface):
    class Meta:
        name = "Commentable"

    comments_count = graphene.Field(graphene.Int, required=True)
    comments = CommentsConnectionField()
    comment_authors = CommentAuthorsConnectionField()

    @classmethod
    @sync_to_async
    def resolve_comments_count(cls, instance, info):
        """Resolve comment count for any commentable type."""
        return await info.context.comment_count_loader.load(instance.id)
```

**Key points:**
- Use `graphene.Interface`
- Can have `@classmethod` resolvers that work for all implementers
- Resolvers receive `cls` and `instance` parameters

### Implementing Interfaces

```python
class ItemType(SleuthDjangoObjectType):
    class Meta:
        model = Item
        interfaces = (CommentableMixinGqlType,)
        fields = ("name", "status")

class ReviewType(SleuthDjangoObjectType):
    class Meta:
        model = Review
        interfaces = (CommentableMixinGqlType, AssessableMixinGqlType)
        fields = ("title", "status")
```

Both types now have `comments_count`, `comments`, `comment_authors` fields automatically.

### Multiple Interfaces

Compose interfaces for cross-cutting concerns:

```python
class UserScopedMixinGqlType(graphene.Interface):
    """Types that can be scoped to users."""
    class Meta:
        name = "UserScoped"

    users = UserScopedField()

class TeamScopedMixinGqlType(graphene.Interface):
    """Types that can be scoped to teams."""
    class Meta:
        name = "TeamScoped"

    teams = TeamScopedField()

class TeamOrUserScopedMixinGqlType(graphene.Interface):
    """Types that can be scoped to teams OR users."""
    class Meta:
        name = "TeamOrUserScoped"
        interfaces = (UserScopedMixinGqlType, TeamScopedMixinGqlType)

# Use in types
class WorkspaceType(SleuthDjangoObjectType):
    class Meta:
        model = Workspace
        interfaces = (TeamOrUserScopedMixinGqlType, CommentableMixinGqlType)
```

### Interface with Custom Logic

```python
class AssessableMixinGqlType(graphene.Interface):
    """Types that can be assessed/reviewed."""
    class Meta:
        name = "Assessable"

    assessment = graphene.Field("AssessmentType")
    is_assessed = graphene.Boolean(required=True)

    @classmethod
    def resolve_is_assessed(cls, instance, info):
        """Check if item has been assessed."""
        return hasattr(instance, "assessment") and instance.assessment is not None

    @classmethod
    @sync_to_async
    def resolve_assessment(cls, instance, info):
        """Load assessment for this item."""
        try:
            return instance.assessment
        except Assessment.DoesNotExist:
            return None
```

## Type Field Extensions

Extend types from other apps without modifying them.

### Defining Extensions

```python
# sleuth/apps/<app>/graphql_extensions.py
from sleuth.graphql.types import TypeFields

# Extend UserType from account app with workspace-specific fields
type_fields = [
    TypeFields("UserGqlType", {"favorite_workspaces": FavoriteWorkspacesField()}),
    TypeFields("OrganizationType", {"custom_field": CustomField()}),
]
```

### How It Works

The `build_dynamic_type()` function calls `load_modules_list()` to find all `type_fields` exports:

```python
# sleuth/graphql/types.py
def build_dynamic_type(name, parent_type, model, fields, interfaces):
    # Collect extensions from all apps
    extensions = load_modules_list("graphql_extensions", "type_fields", TypeFields)

    # Find extensions for this type
    for ext in extensions:
        if ext.type_name == name:
            # Add fields to type
            pass
```

### Real Example

```python
# review/graphql_extensions.py
from sleuth.graphql.types import TypeFields

class FavoriteWorkspaceField(SleuthConnectionField):
    def __init__(self) -> None:
        super().__init__(
            type_=graphene.NonNull(WorkspaceConnection),
            resolver=self.resolve,
        )

    @staticmethod
    @sync_to_async
    def resolve(user, info, **kwargs):
        workspaces = Workspace.objects.filter(
            favorited_by=user,
            org_id=info.context.org.id
        )
        return SleuthRelayResult(data=workspaces)

type_fields = [
    TypeFields("UserGqlType", {"favorite_workspaces": FavoriteWorkspaceField()}),
]
```

Now `UserGqlType` has `favorite_workspaces` field without modifying account app.

## Enum Creation

Convert Python enums to GraphQL enums with helper.

### Basic Usage

```python
from sleuth.apps.common.gql.gql_enums import create_gql_enum
from enum import Enum

class ItemStatus(Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"

# Create GraphQL enum
ItemStatusGqlEnum = create_gql_enum(ItemStatus, gql_enum_name="ItemStatus")

# Use in types
class ItemType(SleuthDjangoObjectType):
    status = graphene.Field(ItemStatusGqlEnum, required=True)
```

### With Django TextChoices

```python
from django.db import models

class ItemStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"

ItemStatusGqlEnum = create_gql_enum(ItemStatus, gql_enum_name="ItemStatus")
```

### With Descriptions

```python
ItemStatusGqlEnum = create_gql_enum(
    ItemStatus,
    gql_enum_name="ItemStatus",
    description="Status of an item in the system"
)
```

### Enum Caching

The `create_gql_enum()` function caches enums to prevent duplicates:

```python
# First call - creates enum
StatusEnum1 = create_gql_enum(Status, gql_enum_name="Status")

# Second call - returns cached enum
StatusEnum2 = create_gql_enum(Status, gql_enum_name="Status")

# StatusEnum1 is StatusEnum2  # True
```

## Context Extensions

Extend GraphQL context with app-specific utilities.

### Basic Context Mixin

```python
# sleuth/apps/<app>/gql_loaders/gql_context.py
from functools import cached_property
from typing import Protocol

class GQL<App>Context(Protocol):
    """Type hints for context with loaders."""
    items_by_owner_loader: ItemsByOwnerLoader
    comment_count_loader: CommentCountLoader

class GQL<App>ContextMixin:
    """Mixin to add loaders to GraphQL context."""

    @cached_property
    def items_by_owner_loader(self) -> ItemsByOwnerLoader:
        return ItemsByOwnerLoader()

    @cached_property
    def comment_count_loader(self) -> CommentCountLoader:
        return CommentCountLoader(target_type=Item)

    def get_item_by_id(self, item_id: int) -> Item | None:
        """Helper method available in context."""
        return Item.objects.filter(id=item_id).first()
```

### Registering Context

```python
# sleuth/apps/<app>/graphql.py
from sleuth.apps.<app>.gql_loaders.gql_context import GQL<App>ContextMixin

context = GQL<App>ContextMixin
```

**Auto-discovery:** Schema builder discovers all `context` exports and mixes them.

### Type Hints for Resolvers

Use Protocol for type hints:

```python
from typing import Protocol
from graphql import GraphQLResolveInfo, FieldNode

class GQL<App>ResolveInfo(Protocol):
    """Type hints for info with app context."""
    context: GQL<App>Context
    field_name: str
    field_nodes: list[FieldNode]

# Use in resolvers
async def resolve_items(self, info: GQL<App>ResolveInfo):
    # IDE knows about context.items_by_owner_loader
    items = await info.context.items_by_owner_loader.load(self.id)
    return items
```

## Real Examples

### DataLoader (review/gql_loaders/loaders.py:14-42)

```python
class CountNumOfCommentsForLoader(SleuthDataLoader[int, int]):
    def __init__(self, target_type: type[Review] | type[Section]):
        super().__init__()
        self._target_type = target_type

    @sync_to_async
    def load_fn(self, keys: list[int]) -> Sequence[int]:
        target_ids = keys
        count_by_target_id = self._fetch_count(target_ids=target_ids)
        return [count_by_target_id.get(target_id, 0) for target_id in target_ids]
```

### Context Mixin (review/graphql/gql_context.py:9-29)

Shows context with multiple loaders for different target types.

### Dynamic Type (review/graphql/review.py:176-203)

Complete example of `build_dynamic_type()` with interfaces.

### Interface (review/graphql/comment.py:136-146)

`CommentableMixinGqlType` interface with fields and resolvers.

### Type Extensions (review/graphql_extensions.py:52-54)

Extends `UserGqlType` with review-specific fields.

## Best Practices

1. **Use DataLoaders for N+1** - Always batch related queries
2. **Cache loaders in context** - Use `@cached_property`
3. **Type hint contexts** - Create Protocol for IDE support
4. **Interfaces for shared behavior** - Don't duplicate field definitions
5. **build_dynamic_type for extensibility** - Allow field injection
6. **create_gql_enum for consistency** - Don't define enums manually
7. **Order DataLoader results** - Return values in same order as keys
8. **Async DataLoader methods** - Use `async def` or `@sync_to_async`
