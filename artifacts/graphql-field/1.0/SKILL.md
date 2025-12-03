---
name: graphql-field
description: Add GraphQL fields, types, queries, and mutations to the Django Graphene-based GraphQL API. Handles type definitions, registration, schema generation, and testing patterns.
trigger_patterns:
  - "add.*graphql.*field"
  - "create.*gql.*field"
  - "add.*graphql.*query"
  - "add.*graphql.*mutation"
  - "expose.*graphql"
---

# GraphQL Field Addition Skill

Add GraphQL fields, types, queries, and mutations using Graphene framework.

## When to Use

- Adding GraphQL query/mutation/type
- Exposing Django model data via GraphQL API

## Critical Rules (ALWAYS)

1. **Filter by org:** `organization_id=info.context.org.id` in EVERY query
2. **Async resolvers:** Use `@sync_to_async` when calling sync Django ORM (`.filter()`, `.get()`). Use native `async def` with Django's async ORM (`.afilter()`, `.aget()`)
3. **Generate schema:** `make generate-gql-schema-and-types` after changes
4. **Absolute imports:** `from sleuth.apps.<app>.models` (never relative)
5. **Naming:** Types use `GqlType` suffix: `UserGqlType`, `ReviewGqlType`. Set GraphQL name via Meta: `class Meta: name = "User"`

## Quick Workflow

### 1. Create Type & Field

```python
# sleuth/apps/<app>/gql_fields/my_feature.py
import graphene
from asgiref.sync import sync_to_async
from sleuth.apps.common.gql.django_object_type import SleuthDjangoObjectType

class MyTypeGqlType(SleuthDjangoObjectType):
    class Meta:
        name = "MyType"
        model = MyModel
        fields = ("name", "status")
    id = graphene.Field(graphene.NonNull(graphene.ID), source="gid")

class MyQueryField(graphene.Field):
    def __init__(self) -> None:
        super().__init__(
            type_=graphene.List(graphene.NonNull(MyTypeGqlType)),
            resolver=self.resolve,
        )

    @staticmethod
    @sync_to_async
    def resolve(root, info):
        # ALWAYS filter by org
        return MyModel.objects.filter(organization_id=info.context.org.id)
```

### 2. Register in graphql.py

```python
# sleuth/apps/<app>/graphql.py
from sleuth.graphql.api import Field
from sleuth.apps.<app>.gql_fields.my_feature import MyQueryField, MyTypeGqlType

fields = [
    Field("my_query", MyQueryField()),
]

types = [
    MyTypeGqlType,
]
```

### 3. Generate Schema & Test

```bash
make generate-gql-schema-and-types
uv run pytest --reuse-db sleuth/apps/<app>/tests/integration/gql_fields/
```

### 4. Write Test

```python
# sleuth/apps/<app>/tests/integration/gql_fields/test_my_feature.py
from sleuth.apps.common.tests.integration.factory_shortcuts import execute_gql_query

def test_my_query(org):
    obj = MyModelFactory(organization=org)
    result = execute_gql_query(query='query { myQuery { id name } }', org=org)
    assert result["data"]["myQuery"][0]["id"] == str(obj.gid)
```

## Common Patterns Quick Reference

| Pattern | Class | Return Type | Key Points |
|---------|-------|-------------|------------|
| Single Item | `graphene.Field` | `graphene.NonNull(MyTypeGqlType)` | Use `filter_by_gid()`, raise `GraphQLError` if not found |
| List | `graphene.Field` | `graphene.List(MyTypeGqlType)` | Use `NonNull` wrapper |
| Paginated | `SleuthConnectionField` | Connection | Return `SleuthRelayResult(data=qs)` |
| Mutation | `graphene.Mutation` | Mutation class | Use `Arguments` nested class |

## Common Tasks

### Create Single-Item Query Field

Query a single entity by ID (GID):

```python
from graphql import GraphQLError
from sleuth.ids import filter_by_gid, InvalidGIDError

class MyItemField(graphene.Field):
    def __init__(self) -> None:
        super().__init__(
            type_=graphene.NonNull(MyItemGqlType),
            args=dict(
                id=graphene.Argument(graphene.ID, required=True),
            ),
            resolver=self.resolve,
        )

    @staticmethod
    @sync_to_async
    def resolve(
        _: None, info: SleuthGQLResolveInfo, id: str  # pylint: disable=redefined-builtin
    ) -> MyItemDB:
        try:
            item = filter_by_gid(id, MyItemDB).select_related("related_model").get()
        except (MyItemDB.DoesNotExist, InvalidGIDError):
            raise GraphQLError(f"MyItem with id: `{id}` does not exist")

        return item
```

Register: `fields = [Field("my_item", MyItemField())]`

**Key points:**
- Use `graphene.NonNull` for type safety (item must exist or error)
- Use `filter_by_gid()` helper for GID-based lookups
- Raise `GraphQLError` when not found (immediate failure)
- Add `.select_related()` for related data to avoid N+1 queries
- No org filter needed if item doesn't belong to org (e.g., cross-org references)

**Real example:** `SkillsRepositoryField` in `sleuth/apps/issues/skills/graphql.py:168`

### Add Field to Existing Type

```python
# In gql_fields/<file>.py, add to class
class MyTypeGqlType(SleuthDjangoObjectType):
    class Meta:
        name = "MyType"
        model = MyModel

    new_field = graphene.String(required=True)

    @staticmethod
    @sync_to_async
    def resolve_new_field(parent, info):
        return parent.compute_new_field()
```

Then: `make generate-gql-schema-and-types`

### Create Mutation

```python
class UpdateItemInput(graphene.InputObjectType):
    id = graphene.ID(required=True)
    name = graphene.String(required=True)

class UpdateItemMutation(graphene.Mutation):
    class Arguments:
        input = UpdateItemInput(required=True)

    item = graphene.Field(ItemGqlType)
    errors = graphene.List(graphene.NonNull(ErrorType), required=True)

    @staticmethod
    @sync_to_async
    @require_permission(OrgPermission.CHANGE)
    def mutate(_, info, input):
        try:
            item = MyModel.objects.get(id=input.id, organization_id=info.context.org.id)
            item.name = input.name
            item.save()
            return UpdateItemMutation(item=item, errors=[])
        except GQLError as e:
            return UpdateItemMutation(
                item=None,
                errors=[ErrorType(field=e.field, messages=e.messages)]
            )
```

Register: `mutations = [Field("update_item", UpdateItemMutation.Field())]`

See `references/mutations.md` for complete patterns.

### Add Pagination

```python
from sleuth.apps.common.gql.relay.connection import SleuthRelayConnection, SleuthRelayResult
from sleuth.apps.common.gql.relay.connection_field import SleuthConnectionField

class MyItemConnection(SleuthRelayConnection):
    class Meta:
        node = MyItemGqlType

class MyItemsField(SleuthConnectionField):
    def __init__(self) -> None:
        super().__init__(
            type_=graphene.NonNull(MyItemConnection),
            resolver=self.resolve,
        )

    @staticmethod
    @sync_to_async
    def resolve(parent, info):
        qs = MyItem.objects.filter(organization_id=parent.org_id).order_by("-created_on")
        return SleuthRelayResult(data=qs)
```

See `references/relay_pagination.md` for complete patterns.

## File Organization

**Simple apps (<5 types):**
```
sleuth/apps/<app>/
└── graphql.py              # All-in-one
```

**Complex apps (>5 types):**
```
sleuth/apps/<app>/
├── graphql.py              # Registration only
├── gql_fields/             # Field implementations
├── gql_mutations/          # Mutation implementations
└── gql_services/           # Reusable resolvers
```

## Anti-Patterns (DON'T)

| ❌ DON'T | ✅ DO |
|---------|-------|
| `MyModel.objects.all()` | `MyModel.objects.filter(organization_id=org_id)` |
| `def resolve(...)` with sync ORM | `@sync_to_async def resolve(...)` with `.filter()` |
| `@sync_to_async async def` with async ORM | `async def resolve(...)` with `.afilter()` |
| `from ..models import X` | `from sleuth.apps.<app>.models import X` |
| `raise Exception("Error")` | `raise GQLError("Error", field="fieldName")` |
| Return raw QuerySet | Return `SleuthRelayResult(data=queryset)` |
| Skip `errors=[]` in mutation | Always return `errors` field |

## Error Handling

Three-tier pattern:

```python
# 1. GQLError - field-specific validation errors
from sleuth.apps.common.gql.exceptions import GQLError
raise GQLError("Invalid email", field="email")

# 2. ErrorType - mutation response errors
from graphene_django.types import ErrorType
return MyMutation(result=None, errors=[ErrorType(field="email", messages=["Invalid"])])

# 3. GraphQLError - immediate failures (permissions, system errors)
from graphql import GraphQLError
raise GraphQLError("Permission denied")
```

See `references/error_handling.md` for complete patterns.

## Permission Checks

```python
from sleuth.apps.common.gql import require_permission
from sleuth.apps.organization.constants import OrgPermission

@staticmethod
@sync_to_async
@require_permission(OrgPermission.CHANGE)  # Before @sync_to_async
def mutate(_, info, input):
    # Mutation logic
```

## Interface Mixins

Reuse common fields across types:

```python
class CommentableMixinGqlType(graphene.Interface):
    class Meta:
        name = "Commentable"
    comments_count = graphene.Int(required=True)
    comments = CommentsConnectionField()

class MyTypeGqlType(SleuthDjangoObjectType):
    class Meta:
        name = "MyType"
        model = MyModel
        interfaces = (CommentableMixinGqlType,)  # Adds comment fields
```

Common interfaces: `CommentableMixinGqlType`, `UserScopedMixinGqlType`, `AssessableMixinGqlType`

See `references/advanced_patterns.md` for interfaces, data loaders, dynamic types.

## Type Utilities

**Enums:**
```python
from sleuth.apps.common.gql.gql_enums import create_gql_enum
StatusEnum = create_gql_enum(MyStatus, gql_enum_name="StatusType")
```

**Dynamic types with interfaces:**
```python
from sleuth.graphql.types import build_dynamic_type

MyTypeGqlType = build_dynamic_type(
    "MyType",
    parent_type=MyTypeBaseGqlType,
    model=MyModel,
    fields=("name", "status"),
    interfaces=(CommentableMixinGqlType,),
)
```

## Troubleshooting

### Types Not Appearing in Schema

1. Check exports: `fields = [Field("name", FieldClass())]` in `graphql.py`
2. Check Field() wrapper used
3. Run `make generate-gql-schema-and-types`
4. Verify in `schema.graphql` (backend) and `frontend/codegen/graphql.ts` (frontend)

### Permission Errors

- Stack decorators correctly: `@sync_to_async` then `@require_permission`
- Check `info.context.org` is accessible
- Verify `OrgPermission` enum value

### Test Failures

- Use `--reuse-db`: `uv run pytest --reuse-db`
- Use `execute_gql_query()` helper (not `gql_client`)
- Check factories exist in `<app>/tests/factories.py`

## Real Examples

**Simple field:** `AccessTokenField` in `sleuth/apps/organization/gql_fields/access_tokens.py`
**Pagination:** `TeamsField` in `sleuth/apps/organization/gql_fields/teams.py`
**Mutation:** `CreateReviewMutation` in `sleuth/apps/review/graphql/review.py`
**Error handling:** `SetContributorEmailMutation` in `sleuth/apps/organization/gql_fields/contributors.py`
**Interface:** `CommentableMixinGqlType` in `sleuth/apps/review/graphql/comment.py`

## References

- `references/relay_pagination.md` - Complete relay/connection patterns
- `references/mutations.md` - Mutations, forms, InputObjectType, validation
- `references/error_handling.md` - GQLError, ErrorType, GraphQLError patterns
- `references/advanced_patterns.md` - Data loaders, interfaces, dynamic types, context extensions
