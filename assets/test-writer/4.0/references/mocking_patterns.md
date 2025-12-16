# Mocking and Patching Patterns

## Decorator-Style Patching

Use `@patch` decorator for mocking in async tests:

```python
from unittest.mock import patch
import pytest

@pytest.mark.asyncio
@patch("sleuth.apps.remote.api.remote.notifications")
async def test_with_mock(mock_notifications):
    mock_notifications.return_value.send_form.return_value = {"success": True}
    result = await some_function()
    assert result is not None
```

**Order matters:** Decorators apply bottom-to-top, so mock parameters appear in the same order:

```python
@pytest.mark.asyncio
@patch("module.second_thing")
@patch("module.first_thing")
async def test_two_mocks(mock_first, mock_second):
    # mock_first corresponds to first_thing
    # mock_second corresponds to second_thing
    pass
```

## Context Manager Patching

Use context managers for patching within fixtures:

```python
from unittest.mock import patch
import pytest_asyncio

@pytest_asyncio.fixture
async def redis_client():
    client = AsyncRedis.from_url("redis://localhost:6379/1")
    with patch("sleuth.apps.trees.services.blackboard._get_async_redis_client", return_value=client):
        yield client
    await client.aclose()
```

## Combining VCR and Mocking

VCR and `@patch` can be used together:

```python
@pytest.mark.asyncio
@patch("sleuth.apps.some_module.function")
async def test_vcr_with_mock(mock_function, vcr):
    mock_function.return_value = "mocked"
    with vcr():
        result = await function_that_calls_api()
        assert result is not None
```

## Tenant Context for Org Isolation

Use tenant context when code requires organization context:

```python
from sleuth import tenant

@pytest.mark.asyncio
async def test_with_tenant_context():
    org = await OrganizationFactory.acreate()
    with tenant.context(org):
        # Code that needs tenant/org context
        result = await some_org_scoped_function()
        assert result is not None
```

## Mock Return Values

Set return values on mocks:

```python
@patch("module.function")
def test_mock_return(mock_function):
    mock_function.return_value = {"key": "value"}
    result = call_function()
    assert result["key"] == "value"
```

For async functions, use regular return values (not async):

```python
@patch("module.async_function")
async def test_async_mock(mock_async):
    mock_async.return_value = "result"  # Not await mock_async.return_value
    result = await call_async_function()
    assert result == "result"
```

## Patching in Fixtures

Patch at fixture scope for tests that share the same mock:

```python
@pytest.fixture
def mock_external_service():
    with patch("sleuth.apps.service.external_api") as mock:
        mock.return_value.fetch.return_value = {"data": "test"}
        yield mock

def test_with_fixture(mock_external_service):
    # mock_external_service is available
    result = call_service()
    assert result["data"] == "test"
```

## Asserting Mock Calls

Verify mocks were called with expected arguments:

```python
@patch("module.function")
def test_mock_called(mock_function):
    call_function_that_uses_mock()

    # Assert called once
    mock_function.assert_called_once()

    # Assert called with specific args
    mock_function.assert_called_with(arg1="value")

    # Assert call count
    assert mock_function.call_count == 2
```
