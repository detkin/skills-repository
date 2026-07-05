# GraphQL Error Handling Patterns

Comprehensive guide to error handling in GraphQL mutations and queries.

## Three-Tier Error Handling

The codebase uses three distinct error types for different scenarios:

### 1. GQLError - Validation Errors (Field-Specific)

Use for validation failures that should return with field information:

```python
from sleuth.apps.common.gql.exceptions import GQLError

def _validate_email(email: str) -> str:
    if not email or "@" not in email:
        raise GQLError("Invalid email address", field="email")
    return email

def _get_item(gid: str, org_id: int) -> Item:
    try:
        return Item.objects.get(gid=gid, organization_id=org_id)
    except Item.DoesNotExist:
        raise GQLError(f"Item `{gid}` not found", field="id")
```

**When to use:**
- Input validation failures
- Object not found errors
- Business rule violations
- Any error that maps to a specific input field

**Benefits:**
- Frontend can highlight specific form fields
- Error messages appear next to relevant inputs
- Better UX than generic errors

### 2. ErrorType - Mutation Response Errors

Use in mutation return values for structured error responses:

```python
from graphene_django.types import ErrorType

class UpdateItemMutation(graphene.Mutation):
    item = graphene.Field(ItemType)
    errors = graphene.List(graphene.NonNull(ErrorType), required=True)

    @staticmethod
    @sync_to_async
    def mutate(_, info, input):
        try:
            item = _validate_and_update(input)
            return UpdateItemMutation(item=item, errors=[])
        except GQLError as e:
            return UpdateItemMutation(
                item=None,
                errors=[ErrorType(field=e.field, messages=e.messages)]
            )
```

**When to use:**
- All mutations should return errors list
- Catch GQLError and convert to ErrorType
- Return empty list on success

**ErrorType structure:**
```python
ErrorType(
    field="fieldName",      # Which input field caused error
    messages=["Error 1", "Error 2"]  # List of error messages
)
```

### 3. GraphQLError - Immediate Failures

Use for errors that should halt execution immediately:

```python
from graphql import GraphQLError

@staticmethod
@sync_to_async
@require_permission(OrgPermission.CHANGE)
def mutate(_, info, item_id):
    item = _get_item(item_id, info.context.org.id)

    if item.is_locked:
        raise GraphQLError("Cannot modify locked item")

    if info.context.user != item.owner and not info.context.user.is_staff:
        raise GraphQLError("Permission denied")

    # Continue with mutation
```

**When to use:**
- Permission denied errors
- System errors (not user's fault)
- Critical failures where returning partial data doesn't make sense
- Errors that don't map to specific fields

**Result:**
- GraphQL response has top-level `errors` array
- No data returned
- Frontend sees complete failure

## GQLError Detailed Usage

### Basic Pattern

```python
from sleuth.apps.common.gql.exceptions import GQLError

class GQLError(ValueError):
    """Structured GraphQL error with field information."""

    def __init__(self, message: str, field: str):
        self.message = message
        self.field = field
        super().__init__(message)

    @property
    def messages(self) -> list[str]:
        """Returns messages as list for ErrorType compatibility."""
        return [self.message]
```

### Validation Helpers with GQLError

Create reusable validators:

```python
def _validate_item_id(item_id: str, org_id: int) -> Item:
    """Validate item exists and belongs to org."""
    try:
        db_id = Item.id_from_gid(org_id, item_id)
        return Item.objects.get(id=db_id, organization_id=org_id)
    except (Item.DoesNotExist, InvalidGIDError, ValueError):
        raise GQLError(f"Item `{item_id}` not found", field="itemId")

def _validate_workspace(workspace_id: str, org: Organization) -> Workspace:
    """Validate workspace belongs to organization."""
    try:
        workspace = filter_by_gid(workspace_id, Workspace).get()
    except (Workspace.DoesNotExist, InvalidGIDError):
        raise GQLError(f"Workspace `{workspace_id}` not found", field="workspaceId")

    if workspace.org_id != org.id:
        raise GQLError("Workspace not in this organization", field="workspaceId")

    return workspace

def _validate_email(email: str) -> str:
    """Validate email format."""
    import re

    if not email:
        raise GQLError("Email is required", field="email")

    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        raise GQLError("Invalid email format", field="email")

    return email.lower()

def _validate_status(status: str, allowed_statuses: list[str]) -> str:
    """Validate status is in allowed list."""
    if status not in allowed_statuses:
        raise GQLError(
            f"Invalid status. Must be one of: {', '.join(allowed_statuses)}",
            field="status"
        )
    return status
```

### Using Validation Helpers in Mutations

```python
class UpdateItemMutation(graphene.Mutation):
    class Arguments:
        input = UpdateItemInput(required=True)

    item = graphene.Field(ItemType)
    errors = graphene.List(graphene.NonNull(ErrorType), required=True)

    @staticmethod
    @sync_to_async
    @require_permission(OrgPermission.CHANGE)
    def mutate(_, info, input):
        try:
            # All validators can raise GQLError
            item = _validate_item_id(input.id, info.context.org.id)
            workspace = _validate_workspace(input.workspace_id, info.context.org)
            email = _validate_email(input.email)
            status = _validate_status(input.status, ["draft", "active", "archived"])

            # Update item
            item.workspace = workspace
            item.email = email
            item.status = status
            item.save()

            return UpdateItemMutation(item=item, errors=[])

        except GQLError as e:
            # Convert to ErrorType for response
            return UpdateItemMutation(
                item=None,
                errors=[ErrorType(field=e.field, messages=e.messages)]
            )
```

### Field Name Conventions

Use consistent field names for better frontend handling:

```python
# Specific fields
raise GQLError("Invalid email", field="email")
raise GQLError("Workspace not found", field="workspaceId")

# Generic/multiple field errors
raise GQLError("You must provide either name or description", field="_All__")
raise GQLError("Permission denied", field="__all__")

# Nested fields (for InputObjectType)
raise GQLError("Invalid URL", field="input.settings.webhookUrl")
```

### Multiple Validation Errors

For complex validation, collect multiple errors:

```python
@staticmethod
@sync_to_async
def mutate(_, info, input):
    errors_list = []

    # Validate all fields
    try:
        item = _validate_item_id(input.id, info.context.org.id)
    except GQLError as e:
        errors_list.append(ErrorType(field=e.field, messages=e.messages))

    try:
        email = _validate_email(input.email)
    except GQLError as e:
        errors_list.append(ErrorType(field=e.field, messages=e.messages))

    try:
        workspace = _validate_workspace(input.workspace_id, info.context.org)
    except GQLError as e:
        errors_list.append(ErrorType(field=e.field, messages=e.messages))

    # Return all errors at once
    if errors_list:
        return UpdateItemMutation(item=None, errors=errors_list)

    # All validations passed - continue
    item.email = email
    item.workspace = workspace
    item.save()

    return UpdateItemMutation(item=item, errors=[])
```

## GraphQLError Usage

### Permission Checks

```python
from graphql import GraphQLError

@staticmethod
@sync_to_async
def mutate(_, info, item_id):
    item = _get_item(item_id, info.context.org.id)

    # Check permissions
    user = info.context.user
    if not user.has_perm(OrgPermission.CHANGE, info.context.org):
        raise GraphQLError("Permission denied")

    if item.owner != user and not user.is_staff:
        raise GraphQLError("You can only modify your own items")

    # Continue...
```

### System Errors

```python
@staticmethod
@sync_to_async
def resolve(parent, info, **kwargs):
    try:
        # Some external API call
        result = external_api.fetch_data(parent.id)
        return result
    except ExternalAPIError as e:
        # System error - not user's fault
        raise GraphQLError(f"External service unavailable: {e}")
    except Timeout:
        raise GraphQLError("Request timed out, please try again")
```

### Conflicting State

```python
@staticmethod
@sync_to_async
def mutate(_, info, item_id):
    item = _get_item(item_id, info.context.org.id)

    if item.is_locked:
        raise GraphQLError("Item is locked by another user")

    if item.status == "archived":
        raise GraphQLError("Cannot modify archived items")

    # Continue...
```

## Real Examples from Codebase

### Simple Validation (organization/gql_fields/contributors.py:48-70)

```python
class SetContributorEmailMutation(graphene.Mutation):
    class Arguments:
        input = SetContributorEmailInput(required=True)

    contributor = graphene.Field(ContributorGqlType)
    errors = graphene.List(graphene.NonNull(ErrorType), required=True)

    @staticmethod
    @sync_to_async
    @require_permission(OrgPermission.CHANGE_CONFIG)
    def mutate(_, info: GraphQLResolveInfo, input: SetContributorEmailInput):
        org: Organization = info.context.org

        try:
            contributor = _validate_contributor_id(input.id, org)
            email = _validate_email(input.email)

            contributor.email = email
            contributor.save()

        except GQLError as e:
            return SetContributorEmailMutation(
                contributor=None,
                errors=[ErrorType(field=e.field, messages=e.messages)]
            )

        return SetContributorEmailMutation(contributor=contributor, errors=[])
```

### Permission with GraphQLError (organization/gql_fields/members.py:29-66)

```python
class DeleteMemberMutation(graphene.Mutation):
    @staticmethod
    @sync_to_async
    @require_permission(OrgPermission.CHANGE)
    def mutate(_: None, info: GraphQLResolveInfo, user_id: str):
        org: Organization = info.context.org
        user = _get_user_by_gid(org, user_id)

        # GraphQLError for permission issues
        if user == info.context.user:
            raise GraphQLError("You can't remove yourself from an organization.")

        if user.is_org_owner(org):
            raise GraphQLError("Cannot remove the owner from an organization.")

        # Continue with deletion
        membership = user.get_membership(org)
        membership.delete()

        return DeleteMemberMutation(success=True)
```

### Multiple Validators (review/graphql/review.py:400-481)

Shows extensive validation chain with multiple validators.

### Validation Helpers (review/graphql/review.py:502-548)

Complete set of reusable validation functions with GQLError.

## Frontend Error Handling

### Handling ErrorType (Mutation Errors)

```typescript
interface MutationResult {
  data?: {
    updateItem: {
      item: Item | null;
      errors: Array<{ field: string; messages: string[] }>;
    };
  };
}

const result: MutationResult = await executeGqlMutation(UPDATE_ITEM, variables);

const mutationData = result.data?.updateItem;

if (mutationData?.errors && mutationData.errors.length > 0) {
  // Display field-specific errors
  mutationData.errors.forEach((error) => {
    const fieldElement = document.querySelector(`[name="${error.field}"]`);
    if (fieldElement) {
      // Show error next to field
      showFieldError(fieldElement, error.messages.join(", "));
    } else if (error.field === "_All__" || error.field === "__all__") {
      // Show general error
      showGeneralError(error.messages.join(", "));
    }
  });
} else if (mutationData?.item) {
  // Success
  showSuccess("Item updated successfully");
}
```

### Handling GraphQLError (Top-Level Errors)

```typescript
try {
  const result = await executeGqlMutation(UPDATE_ITEM, variables);

  if (result.errors && result.errors.length > 0) {
    // GraphQLError - top level failure
    result.errors.forEach((error) => {
      showErrorToast(error.message);
    });
  } else {
    // Check mutation-level errors
    // ... (see above)
  }
} catch (networkError) {
  showErrorToast("Network error, please try again");
}
```

## Testing Error Handling

### Test Validation Errors

```python
def test_update_item_invalid_email(org, user):
    item = ItemFactory(organization=org)

    mutation = """
    mutation UpdateItem($input: UpdateItemInput!) {
        updateItem(input: $input) {
            item { id }
            errors { field messages }
        }
    }
    """

    variables = {
        "input": {
            "id": str(item.gid),
            "email": "invalid-email",  # No @ symbol
        }
    }

    result = execute_gql_query(query=mutation, variables=variables, org=org, user=user)

    # Check error structure
    errors = result["data"]["updateItem"]["errors"]
    assert len(errors) == 1
    assert errors[0]["field"] == "email"
    assert "Invalid email" in errors[0]["messages"][0]

    # Item should be None
    assert result["data"]["updateItem"]["item"] is None
```

### Test Permission Errors

```python
def test_delete_item_permission_denied(org):
    item = ItemFactory(organization=org)
    non_owner = SleuthUserFactory()

    mutation = """
    mutation DeleteItem($id: ID!) {
        deleteItem(id: $id) {
            success
        }
    }
    """

    result = execute_gql_query(
        query=mutation,
        variables={"id": str(item.gid)},
        org=org,
        user=non_owner  # User without permission
    )

    # Should have top-level GraphQLError
    assert "errors" in result
    assert "Permission denied" in result["errors"][0]["message"]
```

## Best Practices

1. **Use GQLError for validation** - Maps to specific fields
2. **Use ErrorType in mutations** - Always return errors list
3. **Use GraphQLError for system errors** - Permission, locks, etc.
4. **Create validation helpers** - Reusable `_validate_*` functions
5. **Consistent field naming** - Use `_All__` for general errors
6. **Collect multiple errors** - Show all validation issues at once
7. **Descriptive messages** - Help users fix the problem
8. **Test error paths** - Verify error structure and messages
