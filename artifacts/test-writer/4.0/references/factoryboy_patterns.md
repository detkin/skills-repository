# Factory Patterns in Sleuth

## Finding Existing Factories

**Always check existing factories before creating new ones:**

1. `sleuth/apps/<app>/tests/factories.py` - App-specific factories
2. `sleuth/apps/organization/tests/factories.py` - Org/Auth/User factories (most common)
3. `sleuth/apps/repository/tests/factories.py` - Repository factories
4. `sleuth/apps/review/tests/factories.py` - Workspace factories

## Common Factory Base Classes

**AsyncDjangoModelFactory** - Use for all new factories:

```python
from sleuth.tests.async_factory import AsyncDjangoModelFactory

class MyModelFactory(AsyncDjangoModelFactory):
    class Meta:
        model = MyModel

    name = factory.Faker("company")
```

**Sync tests**: Call directly: `MyModelFactory()`

**Async tests**: Use acreate: `await MyModelFactory.acreate()`

## Pattern 1: IntegrationAuth Factories

Most integration tests need Organization + IntegrationAuthentication. Look at existing integration factories:

**Examples:**
- `sleuth/apps/github/tests/factories.py` - GitHubIntegrationAuthenticationFactory
- `sleuth/apps/linear/tests/factories.py` - LinearIntegrationAuthenticationFactory
- `sleuth/apps/jira/tests/factories.py` - JiraIntegrationAuthenticationFactory

**Structure:**
```python
class ProviderIntegrationAuthenticationFactory(IntegrationAuthenticationFactory):
    provider = "provider_name"
    type = "oauth"  # or "api_key"
    raw_api_token = os.getenv("SLEUTH_TEST_PROVIDER_TOKEN") or "__SET_IN_.env__"
    extra_data = {"key": "value"}
```

**Usage in tests:**
```python
org = OrganizationFactory()
auth = ProviderIntegrationAuthenticationFactory(org=org)
# auth.org == org (inherited from IntegrationAuthenticationFactory)
```

## Pattern 2: Nested Org References

Use `factory.SelfAttribute("..org")` to ensure nested factories share the same org:

```python
class MyFactory(AsyncDjangoModelFactory):
    org = factory.SubFactory(OrganizationFactory)
    integration_auth = factory.SubFactory(
        IntegrationAuthenticationFactory,
        org=factory.SelfAttribute("..org")  # Reference parent's org
    )
```

**The `..` notation**: Goes up one level in parent hierarchy. Use `...` for two levels, etc.

**Example from codebase:** `sleuth/apps/issue/tests/factories.py`

## Pattern 3: SubFactory for Relationships

Use `SubFactory` for foreign key relationships:

```python
class ProjectFactory(AsyncDjangoModelFactory):
    class Meta:
        model = Project

    name = factory.Faker("word")
    organization = factory.SubFactory(OrganizationFactory)
```

**Avoid circular imports** with string paths:

```python
class ProjectFactory(AsyncDjangoModelFactory):
    organization = factory.SubFactory(
        "sleuth.apps.organization.tests.factories.OrganizationFactory"
    )
```

## Pattern 4: Sequences for Unique Values

Use `Sequence` for fields requiring uniqueness:

```python
class UserFactory(AsyncDjangoModelFactory):
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    username = factory.Sequence(lambda n: f"user{n}")
```

## Pattern 5: LazyAttribute for Computed Values

Use `LazyAttribute` when a field depends on other fields:

```python
class ProjectFactory(AsyncDjangoModelFactory):
    name = factory.Faker("word")
    slug = factory.LazyAttribute(lambda obj: slugify(obj.name))
```

## Pattern 6: Post Generation Hooks

Use `@factory.post_generation` for many-to-many relationships or complex setup:

```python
class TeamFactory(AsyncDjangoModelFactory):
    class Meta:
        model = Team

    name = factory.Faker("word")

    @factory.post_generation
    def members(self, create, extracted, **kwargs):
        if extracted:
            for user in extracted:
                self.members.add(user)

# Usage
team = TeamFactory(members=[user1, user2])
```

## Pattern 7: Skipping Post-Generation Saves

Use `skip_postgeneration_save = True` to prevent extra database saves:

```python
class MyFactory(AsyncDjangoModelFactory):
    class Meta:
        model = MyModel
        skip_postgeneration_save = True  # Prevents extra DB save

    @factory.post_generation
    def setup(self, create, extracted, **kwargs):
        # This won't trigger an extra save
        self.some_field = "value"
```

**Use when:** Post-generation hooks modify fields but you don't need Django to save again (performance optimization).

**Example from codebase:** `sleuth/apps/organization/tests/factories.py`

## Async Database Operations in Tests

Beyond factories, directly manipulate models in async tests:

**Async model saves:**
```python
@pytest.mark.asyncio
async def test_update_model():
    issue = await LinkedIssueFactory.acreate()
    issue.title = "Updated title"
    await issue.asave()
    assert issue.title == "Updated title"
```

**Async model refresh:**
```python
@pytest.mark.asyncio
async def test_refresh_after_operation():
    node = await NodeStateFactory.acreate(status=Status.RUNNING)

    # Operation that modifies node
    cleanup_stuck_nodes_task()

    # Refresh to get updated state
    await node.arefresh_from_db()
    assert node.status == Status.ERROR
```

**Direct queryset operations:**
```python
@pytest.mark.asyncio
async def test_direct_create():
    # Create
    await LinkedIssueTag.objects.acreate(
        issue=issue,
        org=org,
        name="labels",
        value="urgent"
    )

    # Delete
    await LinkedIssueTag.objects.filter(org=org).adelete()

    # Get with relations
    tree = await Tree.objects.select_related("org", "workspace").aget(id=tree.id)
```
