# GraphQL Mutation Patterns

Complete guide to implementing mutations in Graphene.

## Basic Mutation Pattern

Standard mutation with Arguments class and error handling.

### Step 1: Define Input Type (Optional)

For complex inputs, use `InputObjectType`:

```python
import graphene

class UpdateItemInput(graphene.InputObjectType):
    id = graphene.ID(required=True, description="Item ID")
    name = graphene.String(required=True, description="New item name")
    status = graphene.String(description="Optional status update")
    tags = graphene.List(graphene.String, description="List of tags")
```

**Benefits:**
- Groups related arguments
- Reusable across mutations
- Better documentation
- Frontend gets TypeScript type

### Step 2: Define Mutation Class

```python
from asgiref.sync import sync_to_async
from graphene_django.types import ErrorType
from sleuth.apps.common.gql import require_permission
from sleuth.apps.common.gql.exceptions import GQLError
from sleuth.apps.organization.constants import OrgPermission

class UpdateItemMutation(graphene.Mutation):
    class Arguments:
        input = UpdateItemInput(required=True)

    # Return fields
    item = graphene.Field(ItemType)
    errors = graphene.List(graphene.NonNull(ErrorType), required=True)

    @staticmethod
    @sync_to_async
    @require_permission(OrgPermission.CHANGE)
    def mutate(_, info, input):
        try:
            # Validate and fetch
            item = _get_item(input.id, info.context.org.id)

            # Update
            item.name = input.name
            if input.status:
                item.status = input.status
            if input.tags:
                item.tags.set(input.tags)

            item.save()

            return UpdateItemMutation(item=item, errors=[])

        except GQLError as e:
            return UpdateItemMutation(
                item=None,
                errors=[ErrorType(field=e.field, messages=e.messages)]
            )
```

**Key patterns:**
- `@sync_to_async` decorator required
- Stack with `@require_permission` for auth
- Return both result and errors
- Catch `GQLError` for validation failures

### Step 3: Register Mutation

```python
# In graphql.py
from sleuth.graphql.api import Field

mutations = [
    Field("update_item", UpdateItemMutation.Field()),
]
```

## Mutation Without Input Type

For simple mutations, use direct arguments:

```python
class DeleteItemMutation(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)

    success = graphene.NonNull(graphene.Boolean)
    message = graphene.String()

    @staticmethod
    @sync_to_async
    @require_permission(OrgPermission.DELETE)
    def mutate(_, info, id):
        item = _get_item(id, info.context.org.id)
        item.delete()
        return DeleteItemMutation(success=True, message="Item deleted")
```

## Form-Based Mutations (SleuthFormMutation)

Use Django forms for validation:

```python
from sleuth.apps.common.gql.mutations.mutation_form import SleuthFormMutation
from sleuth.apps.<app>.forms import UpdateItemForm

class UpdateItemFormMutation(SleuthFormMutation):
    class Meta:
        form_class = UpdateItemForm
        require_permission = OrgPermission.CHANGE

    item = graphene.Field(ItemType, required=True)

    @classmethod
    def get_form_kwargs(cls, info, **input):
        """Provide kwargs for form initialization."""
        item_id = input.get("id")
        item = _get_item(item_id, info.context.org.id)

        return {
            "instance": item,
            "data": input,
            "org": info.context.org,
        }

    @classmethod
    def get_payload_kwargs(cls, info, form, **input):
        """Return mutation result after form.save()."""
        item = form.save()
        return {"item": item}
```

**When to use:**
- Complex validation logic already in forms
- Need to reuse existing form validators
- Want Django's form validation features

**SleuthFormMutation handles:**
- Form initialization
- Validation
- Error conversion to ErrorType
- Permission checking

## Advanced Patterns

### Multiple Input Validation

```python
class CreateItemWithRelationsMutation(graphene.Mutation):
    class Arguments:
        item_input = CreateItemInput(required=True)
        owner_id = graphene.ID(required=True)
        workspace_id = graphene.ID(required=True)

    item = graphene.Field(ItemType)
    errors = graphene.List(graphene.NonNull(ErrorType), required=True)

    @staticmethod
    @sync_to_async
    @require_permission(OrgPermission.CREATE)
    def mutate(_, info, item_input, owner_id, workspace_id):
        try:
            # Validate related objects
            owner = _validate_owner(owner_id, info.context.org)
            workspace = _validate_workspace(workspace_id, info.context.org)

            # Create item
            item = Item.objects.create(
                organization=info.context.org,
                owner=owner,
                workspace=workspace,
                name=item_input.name,
                status=item_input.status,
            )

            return CreateItemWithRelationsMutation(item=item, errors=[])

        except GQLError as e:
            return CreateItemWithRelationsMutation(
                item=None,
                errors=[ErrorType(field=e.field, messages=e.messages)]
            )
```

### Conditional Logic Based on Input

```python
class UpdateOrCreateItemMutation(graphene.Mutation):
    class Arguments:
        input = UpdateItemInput(required=True)

    item = graphene.Field(ItemType)
    created = graphene.Boolean(required=True)
    errors = graphene.List(graphene.NonNull(ErrorType), required=True)

    @staticmethod
    @sync_to_async
    @require_permission(OrgPermission.CHANGE)
    def mutate(_, info, input):
        try:
            if input.id:
                # Update existing
                item = _get_item(input.id, info.context.org.id)
                item.name = input.name
                item.save()
                created = False
            else:
                # Create new
                item = Item.objects.create(
                    organization=info.context.org,
                    name=input.name,
                    owner=info.context.user,
                )
                created = True

            return UpdateOrCreateItemMutation(
                item=item, created=created, errors=[]
            )

        except GQLError as e:
            return UpdateOrCreateItemMutation(
                item=None, created=False,
                errors=[ErrorType(field=e.field, messages=e.messages)]
            )
```

### Async Operations in Mutations

```python
from sleuth.apps.<app>.tasks import process_item_async

class ProcessItemMutation(graphene.Mutation):
    class Arguments:
        item_id = graphene.ID(required=True)

    task_id = graphene.String(required=True)
    success = graphene.Boolean(required=True)

    @staticmethod
    @sync_to_async
    @require_permission(OrgPermission.CHANGE)
    def mutate(_, info, item_id):
        item = _get_item(item_id, info.context.org.id)

        # Trigger async task
        task = process_item_async.delay(item.id)

        return ProcessItemMutation(
            task_id=task.id,
            success=True
        )
```

### Batch Operations

```python
class BatchUpdateItemsMutation(graphene.Mutation):
    class Arguments:
        item_ids = graphene.List(graphene.NonNull(graphene.ID), required=True)
        status = graphene.String(required=True)

    updated_count = graphene.Int(required=True)
    items = graphene.List(graphene.NonNull(ItemType))
    errors = graphene.List(graphene.NonNull(ErrorType), required=True)

    @staticmethod
    @sync_to_async
    @require_permission(OrgPermission.CHANGE)
    def mutate(_, info, item_ids, status):
        try:
            # Convert GIDs to DB IDs
            db_ids = [Item.id_from_gid(info.context.org.id, gid) for gid in item_ids]

            # Bulk update
            updated_count = Item.objects.filter(
                id__in=db_ids,
                organization_id=info.context.org.id
            ).update(status=status)

            # Fetch updated items for return
            items = Item.objects.filter(id__in=db_ids)

            return BatchUpdateItemsMutation(
                updated_count=updated_count,
                items=list(items),
                errors=[]
            )

        except GQLError as e:
            return BatchUpdateItemsMutation(
                updated_count=0,
                items=[],
                errors=[ErrorType(field=e.field, messages=e.messages)]
            )
```

## Validation Helpers

Create reusable validation functions:

```python
from sleuth.apps.common.gql.exceptions import GQLError
from sleuth.graphql.gid import filter_by_gid, InvalidGIDError

def _get_item(gid: str, org_id: int, field: str = "id") -> Item:
    """Validate and fetch item by GID."""
    try:
        return filter_by_gid(gid, Item).filter(organization_id=org_id).get()
    except (Item.DoesNotExist, InvalidGIDError):
        raise GQLError(f"Item `{gid}` not found.", field=field)

def _validate_workspace(gid: str, org: Organization) -> Workspace:
    """Validate workspace belongs to org."""
    try:
        workspace = filter_by_gid(gid, Workspace).get()
        if workspace.org_id != org.id:
            raise GQLError("Workspace not in organization.", field="workspaceId")
        return workspace
    except (Workspace.DoesNotExist, InvalidGIDError):
        raise GQLError(f"Workspace `{gid}` not found.", field="workspaceId")

def _validate_permissions(item: Item, user: SleuthUser) -> None:
    """Check user has permission for item."""
    if item.owner != user and not user.is_staff:
        raise GQLError("You don't have permission to modify this item.", field="_All__")
```

## Real Examples from Codebase

### Simple Delete (organization/gql_fields/members.py:21-66)

```python
class DeleteMemberMutation(graphene.Mutation):
    class Arguments:
        user_id = graphene.ID(required=True)

    success = graphene.NonNull(graphene.Boolean)

    @staticmethod
    @sync_to_async
    @require_permission(OrgPermission.CHANGE)
    def mutate(_: None, info: GraphQLResolveInfo, user_id: str):
        org: Organization = info.context.org
        user = _get_user_by_gid(org, user_id)

        if user == info.context.user:
            raise GraphQLError("You can't remove yourself from an organization.")

        if user.is_org_owner(org):
            raise GraphQLError("Cannot remove the owner from an organization.")

        membership = user.get_membership(org)
        membership.delete()

        return DeleteMemberMutation(success=True)
```

### With Input Type (review/graphql/review.py:273-297)

```python
class CreateReviewInput(graphene.InputObjectType):
    workspace_id = graphene.ID(required=True)
    template_id = graphene.String(required=True)

class CreateReviewMutation(graphene.Mutation):
    class Arguments:
        input = CreateReviewInput(required=True)

    review = graphene.Field(ReviewGqlType)
    errors = graphene.List(graphene.NonNull(ErrorType), required=True)

    @staticmethod
    @sync_to_async
    def mutate(_: None, info: GraphQLResolveInfo, input: CreateReviewInput):
        org: Organization = info.context.org
        user: SleuthUser = validate_user(info)

        try:
            workspace = _get_workspace(input.workspace_id)
            review = create_blank_review(org, workspace, str(input.template_id), owner=user)
        except GQLError as e:
            return CreateReviewMutation(
                review=None,
                errors=[ErrorType(field=e.field, messages=e.messages)]
            )

        return CreateReviewMutation(review=review, errors=[])
```

### Form-Based (organization/gql_fields/invitations.py:54-121)

Shows `SleuthFormMutation` with `get_form_kwargs` and `get_payload_kwargs` overrides.

### Complex with Validation (review/graphql/review.py:400-481)

Shows extensive validation, permissions, and error handling.

## Frontend Usage

### Simple Mutation

```graphql
mutation UpdateItem($input: UpdateItemInput!) {
  updateItem(input: $input) {
    item {
      id
      name
      status
    }
    errors {
      field
      messages
    }
  }
}
```

Variables:
```json
{
  "input": {
    "id": "SXRlbTo1",
    "name": "Updated Name",
    "status": "active"
  }
}
```

### Handling Errors

TypeScript example:

```typescript
const result = await executeGqlMutation(UPDATE_ITEM, { input });

if (result.data?.updateItem.errors.length > 0) {
  // Display field-specific errors
  result.data.updateItem.errors.forEach(error => {
    console.error(`${error.field}: ${error.messages.join(', ')}`);
  });
} else {
  // Success
  const item = result.data.updateItem.item;
}
```

## Testing Mutations

```python
from sleuth.apps.common.tests.integration.factory_shortcuts import execute_gql_query

def test_update_item_mutation(org, user):
    item = ItemFactory(organization=org)

    mutation = """
    mutation UpdateItem($input: UpdateItemInput!) {
        updateItem(input: $input) {
            item {
                id
                name
            }
            errors {
                field
                messages
            }
        }
    }
    """

    variables = {
        "input": {
            "id": str(item.gid),
            "name": "New Name",
        }
    }

    result = execute_gql_query(query=mutation, variables=variables, org=org, user=user)

    assert result["data"]["updateItem"]["errors"] == []
    assert result["data"]["updateItem"]["item"]["name"] == "New Name"

def test_update_item_validation_error(org, user):
    mutation = """..."""  # Same as above

    variables = {
        "input": {
            "id": "InvalidID",
            "name": "Name",
        }
    }

    result = execute_gql_query(query=mutation, variables=variables, org=org, user=user)

    errors = result["data"]["updateItem"]["errors"]
    assert len(errors) == 1
    assert errors[0]["field"] == "id"
```

## Best Practices

1. **Always return errors list** - Even if empty, helps frontend consistency
2. **Use InputObjectType for 3+ args** - Improves readability
3. **Validate org_id** - Filter all queries by organization
4. **Create validation helpers** - Reuse `_get_*`, `_validate_*` functions
5. **Use @sync_to_async** - Required for all mutation methods
6. **Stack permission decorators** - `@require_permission` before `@sync_to_async`
7. **Return result object** - Even on error, return mutation class with errors populated
8. **Field-specific errors** - Use `field` parameter in GQLError for better UX
