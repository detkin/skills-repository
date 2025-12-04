# VCR Patterns

## VCR in Sleuth Tests

VCR records/replays HTTP interactions. **Always look at existing examples first:**
- `sleuth/apps/github/tests/integration/test_client.py`
- `sleuth/apps/linear/tests/integration/test_client.py`
- `sleuth/apps/jira/tests/integration/test_client.py`

## Standard Pattern for API Clients

**For integration apps (github, linear, jira, etc.):**

```python
def test_api_call(vcr):
    # 1. Setup: Create org + integration auth
    org = OrganizationFactory()
    auth = ProviderIntegrationAuthenticationFactory(org=org)

    # 2. Wrap API call with vcr()
    with vcr():
        result = client.fetch_data()

    # 3. Assert response
    assert result is not None
```

**Example implementations:**
- `sleuth/apps/github/tests/integration/test_client.py` - Uses GitHubIntegrationAuthenticationFactory, IntegrationContext
- `sleuth/apps/linear/tests/integration/test_client.py` - Uses LinearIntegrationAuthenticationFactory
- `sleuth/apps/jira/tests/integration/test_client.py` - Uses JiraIntegrationAuthenticationFactory

**Cassette location**: Automatically saved to `sleuth/apps/<app>/tests/fixtures/vcr_cassettes/test_<module>_test_<function>.yaml`

## How VCR Works

**First run**: Makes real API call, records request/response to cassette YAML file

**Subsequent runs**: Replays response from cassette (no real API call)

## Regenerating Stale Cassettes

### When to Regenerate

Delete and regenerate cassettes when:
- Test fails with VCR matching error
- You modified the API client code
- External API response format changed

### Regeneration Workflow

1. **Delete the cassette:**
   ```bash
   rm sleuth/apps/<app>/tests/fixtures/vcr_cassettes/<test_file>_<test_function>.yaml
   ```

2. **Check API token is set:**
   - Look in `sleuth/apps/<app>/tests/factories.py` for required env var
   - Common vars:
     - `SLEUTH_TEST_GITHUB_TOKEN`
     - `SLEUTH_TEST_LINEAR_TOKEN`
     - `SLEUTH_TEST_JIRA_TOKEN`
   - Add to `.env` file if missing

3. **Run test to regenerate:**
   ```bash
   uv run pytest --reuse-db sleuth/apps/<app>/tests/integration/test_<module>.py::test_function
   ```

4. **Verify cassette created:**
   ```bash
   ls sleuth/apps/<app>/tests/fixtures/vcr_cassettes/
   # Should see the new .yaml cassette file
   ```

### Troubleshooting Regeneration

**Test still fails after regeneration:**
- Check the cassette YAML for API response format
- Verify API token has correct permissions
- Check if API endpoint changed

**VCR can't find cassette location:**
- Ensure `tests/fixtures/vcr_cassettes/` directory exists
- Check test file is in correct location (`tests/integration/`)

## Async Tests with VCR

VCR works the same way in async tests:

```python
@pytest.mark.asyncio
async def test_async_api_call(vcr):
    org = await OrganizationFactory.acreate()
    auth = await ProviderIntegrationAuthenticationFactory.acreate(org=org)

    with vcr():
        result = await some_async_api_call(auth)
        assert result is not None
```

**Note**: VCR is less common in async tests. Most async tests are for internal operations (trees, gardener) that don't make external API calls.

## VCR with Tenant Context

For org-scoped operations, combine VCR with tenant context:

```python
from sleuth import tenant

@pytest.mark.asyncio
async def test_with_tenant_context(vcr):
    org = await OrganizationFactory.acreate()

    with vcr(), tenant.context(org):
        result = await generate_tree_yaml_from_description(description, org)
        assert result is not None
```

**Important**: VCR context manager first, then tenant context.

## Filtering Sensitive Data

To filter sensitive data from cassettes, add filters to the `vcr` fixture in `sleuth/conftest.py` rather than individual tests.

Example locations where filters are configured:
- `sleuth/conftest.py` - Global VCR configuration
- `sleuth/tests/vcr.py` - VCR fixture implementation
