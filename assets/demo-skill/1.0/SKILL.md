---
name: test-writer
description: This skill should be used when writing or modifying Python tests. Covers pytest test execution with --reuse-db, function-style tests, factoryboy factories for models, and vcr for external API calls.
---

# Test Writer

## Overview

Write pytest tests for the Sleuth codebase following project-specific patterns.

## Test Writing Workflow

When writing tests for `sleuth/apps/<app>/<module>.py`:

1. **Find similar tests to copy**
   - Look at `sleuth/apps/<app>/tests/integration/test_<module>.py` for patterns
   - Check other test files in same app for setup patterns

2. **Identify required factories**
   - Check `sleuth/apps/<app>/tests/factories.py` for app-specific factories
   - Most tests need `OrganizationFactory` + `<Provider>IntegrationAuthenticationFactory`
   - See `sleuth/apps/organization/tests/factories.py` for core factories

3. **Copy existing test structure**
   - Use function-style tests with `@pytest.mark.asyncio` for async code
   - Use `vcr()` context manager for external API calls
   - Follow naming: `test_<function_name>_<scenario>`

4. **Run tests**
   ```bash
   uv run pytest --reuse-db sleuth/apps/<app>/tests/integration/test_<module>.py
   ```

5. **Validate code quality**
   ```bash
   make check-types  # Fix mypy/black errors
   make lint-py      # Fix pylint errors
   ```

## Test Location

Tests mirror the package structure:
- Code: `sleuth/apps/jenkins/client.py`
- Test: `sleuth/apps/jenkins/tests/integration/test_client.py`
- Factories: `sleuth/apps/jenkins/tests/factories.py`

## Test Execution

**ALWAYS run tests with --reuse-db:**

```bash
uv run pytest --reuse-db path/to/test_file.py
```

Never skip the `--reuse-db` flag.

## Test Style

**ALWAYS use pytest function-style tests:**

```python
# Correct
def test_user_creation():
    user = UserFactory()
    assert user.email is not None

# Incorrect - avoid class-based tests
class TestUser:
    def test_creation(self):
        ...
```

## Default Fixtures

The root `sleuth/conftest.py` automatically applies these fixtures to tests:

- **`clean_redis`** - Cleans Redis database before each test (uses test database db=1)
- **`ignore_session_context_validation`** - Auto-patches PQL execution context validation (opt-out with `@pytest.mark.no_ignore_session_context_validation`)
- **`disable_celery_transaction_check`** - Disables Celery transaction validation for tests running inside transactions
- **`no_requests_are_in_private_ip_range`** - Auto-patches private IP check to allow test requests
- **`no_requests_to_openai`** - Prevents real OpenAI API calls, returns stub responses (opt-out with `@pytest.mark.noblockopenai`)
- **`vcr`** - VCR fixture for recording/replaying HTTP interactions (imported from `sleuth.tests.vcr`)

These fixtures run automatically - no need to explicitly pass them to test functions unless opting out.

## Database Factories

**Factories are only needed for Django database models.** Apps without database models don't need a `factories.py` file.

**Before creating a factory, check these locations:**
1. `sleuth/apps/<app>/tests/factories.py` - App-specific factories
2. `sleuth/apps/organization/tests/factories.py` - Org/Auth factories (most tests need these)
3. `sleuth/apps/repository/tests/factories.py` - Repository factories

**Sync tests:** Call the factory directly:

```python
def test_organization_creation():
    org = OrganizationFactory()
    assert org.name is not None
```

**Async tests:** Use `.acreate()`:

```python
@pytest.mark.asyncio
async def test_async_organization():
    org = await OrganizationFactory.acreate()
    assert org.name is not None
```

See `references/factoryboy_patterns.md` for creating new factories.

## Common Test Patterns

### Pattern 1: Testing API Clients with VCR

For apps that make external API calls (github, linear, jira, etc.):

```python
def test_api_call(vcr):
    org = OrganizationFactory()
    auth = ProviderIntegrationAuthenticationFactory(org=org)

    with vcr():
        result = api_client.fetch_data()

    assert result is not None
```

**Examples to copy:**
- `sleuth/apps/github/tests/integration/test_client.py` - GitHub API patterns
- `sleuth/apps/linear/tests/integration/test_client.py` - Linear API patterns
- `sleuth/apps/jira/tests/integration/test_client.py` - Jira API patterns

See `references/vcr_patterns.md` for VCR details.

### Pattern 2: Testing Async Operations

For apps with async operations (trees, gardener, etc.):

```python
@pytest.mark.asyncio
async def test_async_operation():
    org = await OrganizationFactory.acreate()
    workspace = await WorkspaceFactory.acreate(org=org)

    result = await some_async_function(workspace)

    assert result.status == "success"
```

**Examples to copy:**
- `sleuth/apps/trees/tests/services/test_tree.py` - Tree service patterns
- `sleuth/apps/gardener/tests/nodes/test_analyze_stale_issues.py` - Node testing patterns

### Pattern 3: Testing Django Models/Services

For apps with models and business logic:

```python
def test_model_creation():
    org = OrganizationFactory()
    project = ProjectFactory(org=org)

    assert project.org == org
    assert project.name is not None
```

**Examples to copy:**
- Look in `sleuth/apps/<app>/tests/test_models.py` for model tests
- Look in `sleuth/apps/<app>/tests/services/` for service tests

### Async Tests

Use `@pytest.mark.asyncio` for async test functions:

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    org = await OrganizationFactory.acreate()
    result = await some_async_function(org)
    assert result is not None
```

**Async fixtures** use `pytest_asyncio.fixture`:

```python
import pytest_asyncio

@pytest_asyncio.fixture
async def workspace_with_org():
    org = await OrganizationFactory.acreate()
    workspace = await WorkspaceFactory.acreate(org=org)
    return workspace
```

### Tenant Context for Org-Scoped Operations

Some operations require tenant context:

```python
from sleuth import tenant

@pytest.mark.asyncio
async def test_org_scoped_operation():
    org = await OrganizationFactory.acreate()

    with tenant.context(org):
        result = await some_org_scoped_function()
        assert result is not None
```

See `references/mocking_patterns.md` for more details.

## Troubleshooting

### Test Fails with "Factory not found"

1. **Check if factory exists:**
   ```bash
   grep -r "class.*Factory" sleuth/apps/<app>/tests/factories.py
   ```

2. **Check parent factories:**
   - `sleuth/apps/organization/tests/factories.py` - Most common factories
   - `sleuth/apps/repository/tests/factories.py` - Repository factories

3. **Create factory if missing:**
   - See `references/factoryboy_patterns.md` for patterns
   - Copy similar factory from same app or related app
   - Use `AsyncDjangoModelFactory` as base class

### Test Fails with VCR Error

1. **Delete the cassette:**
   ```bash
   rm sleuth/apps/<app>/tests/fixtures/vcr_cassettes/<test_name>.yaml
   ```

2. **Ensure API token is set:**
   - Check `tests/factories.py` for required environment variable
   - Common vars: `SLEUTH_TEST_GITHUB_TOKEN`, `SLEUTH_TEST_LINEAR_TOKEN`
   - Add to `.env` file

3. **Re-run test to regenerate cassette:**
   ```bash
   uv run pytest --reuse-db sleuth/apps/<app>/tests/integration/test_client.py::test_name
   ```

4. **If still failing:**
   - Check the new cassette YAML for API response
   - Verify API token has correct permissions

See `references/vcr_patterns.md` for more details.

### Test Fails with "No org context"

Some operations require tenant context:

```python
from sleuth import tenant

with tenant.context(org):
    result = await some_org_scoped_function()
```

See `references/mocking_patterns.md` for examples.

### Import Errors

**Always use absolute imports:**
```python
# Correct
from sleuth.apps.organization.tests.factories import OrganizationFactory

# Incorrect - avoid relative imports
from ..factories import OrganizationFactory
```

## Post-Test Validation

After writing tests, run from project root:

```bash
make check-types  # mypy and black
make lint-py      # pylint
```

## Advanced Patterns

For more complex testing scenarios, see:
- `references/factoryboy_patterns.md` - Sleuth-specific factory patterns including IntegrationAuth setup
- `references/vcr_patterns.md` - VCR cassette management and regeneration workflows
- `references/mocking_patterns.md` - Mocking and patching patterns for async code, context managers, and tenant isolation
