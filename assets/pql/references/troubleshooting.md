# PQL Troubleshooting Reference

Diagnostic procedures and solutions for common PQL problems. Load when queries fail, perform poorly, or return unexpected results.

## Diagnostic Tools

### Verbose Logging

Enable detailed execution logging:

```python
context.be_verbose = True
result, _ = execute_query(query, context)
```

**Shows:**
- Each execution step with timing
- Applied modifiers and their filters
- SQL query counts and content
- Tag resolution process
- Filter application order

**Use for:** Understanding why query returns specific results, finding performance bottlenecks, debugging modifier application.

### Fragment Inspection

Check what's registered:

```python
from sleuth.apps.pql.registry import get_fragment

fragment = get_fragment("myfeature.created")
print([tag.name for tag in fragment.tags])  # All available tags
print([field.name for field in fragment.fields])  # All available fields
print(fragment.aggregators)  # Supported aggregators
```

**Use for:** Verifying tag/field names, checking aggregator support, confirming fragment registration.

### SQL Query Counting

Detect N+1 problems:

```python
from django.test.utils import CaptureQueriesContext
from django.db import connection

with CaptureQueriesContext(connection) as queries:
    result, _ = execute_query(query, context)

print(f"Executed {len(queries)} queries")
for q in queries:
    print(f"  {q['time']}s: {q['sql'][:100]}")
```

**Use for:** Finding performance issues, detecting missing select_related/prefetch_related, identifying inefficient queries.

### AST Inspection

Verify query parsing:

```python
from sleuth.apps.pql.parsing.parsing import PulseQueryParser

parser = PulseQueryParser(query_str)
print(parser.expression)  # Shows parsed structure
print(parser.expression.fragment_name)  # Fragment name
print(parser.expression.tag_filters)  # Parsed filters
```

**Use for:** Debugging syntax errors, understanding how query is interpreted, verifying filter parsing.

## Problem Categories

### Fragment Discovery

**Symptom:** "Unknown fragment: myfeature.created"

**Diagnose:**
1. Check `/sleuth/apps/myapp/pql.py` exists
2. Verify it contains `fragments = [...]` list
3. Look for syntax errors preventing import
4. Confirm module in INSTALLED_APPS

**Fix:**
```python
# Create /sleuth/apps/myapp/pql.py
from sleuth.apps.myapp.pql_myfeature import MyFeatureExecutor

fragments = [
    MyFeatureExecutor(measure_name="myfeature.created"),
]
```

**Verify:** `from sleuth.apps.pql.registry import get_fragment; get_fragment("myfeature.created")`

### Silent Tag Filtering

**Symptom:** `{@mytag:'value'}` doesn't filter results

**Diagnose:**
1. Check if tag in fragment's TagSet: `print([t.name for t in fragment.tags])`
2. Verify tag name spelling matches exactly
3. Enable verbose logging to see which tags apply
4. Check for operator support (`supported_operators` list)

**Fix:**
```python
# Add missing tag
tags = TagSet([
    GidTag(MyModel),
    IntegrationTag(),
    AttrTag("mytag", "My Tag", str, db_name="my_tag_field"),  # Add this
])
```

**Why silent:** PQL doesn't error on unknown tags to support progressive rollout across environments. Unknown tags are simply ignored.

### Org Isolation Breach

**Symptom:** Seeing data from wrong organization

**THIS IS A CRITICAL SECURITY VULNERABILITY.** Stop everything and fix immediately.

**Diagnose:**
```python
# Check fragment's build_query method
def _exec_step_build_query(self, org: Organization) -> QuerySet:
    # MUST have .filter(org=org)
    return MyModel.objects.all()  # ❌ WRONG - no org filter
```

**Fix:**
```python
def _exec_step_build_query(self, org: Organization) -> QuerySet:
    return MyModel.objects.filter(org=org).order_by("id")  # ✅ CORRECT
```

**Verify fix with test:**
```python
def test_org_isolation():
    """CRITICAL: Verify fragment only returns data for specified org."""
    org1, org2 = OrganizationFactory.create_batch(2)
    MyModelFactory.create_batch(5, org=org1, status='open')
    MyModelFactory.create_batch(3, org=org2, status='open')

    context = ExecutionContext(org=org1, start=start, end=end)
    result, _ = execute_query("sum:myfeature.created{@status:'open'}", context)

    assert result == 5, f"Expected 5 (org1 only), got {result}"

    # Also verify list queries
    result, _ = execute_query("list:myfeature.created", context)
    assert all(item['org_id'] == org1.id for item in result if 'org_id' in item)
```

**Impact:** Without org filter, ALL customer data is exposed across organizations. This is the most severe type of bug in a multi-tenant SaaS system.

**Prevention:** Add org isolation tests for EVERY fragment. Make this a required check in PR reviews.

### Mean Calculation Confusion

**Symptom:** Expected 100, got 3.33

**Cause:** Mean divides by days, not by count

**Fix implementation:**
```python
def _exec_step_aggregate_value(self, aggregation: AggregationData, query, selectors):
    if isinstance(aggregation.agg_type, Mean):
        days = get_num_of_days_for_average(aggregation.context.end, aggregation.context.start)
        return query.count() / days  # Per-day average
```

**Not:** `return sum(values) / len(values)` (mathematical average)

### List Query Timeout

**Symptom:** Query takes >10 seconds, eventually times out

**Diagnose:**
1. Check if field selection specified: `list:fragment[@fields]`
2. Count SQL queries with CaptureQueriesContext
3. Check result size: `len(result)`
4. Verify date range isn't too wide

**Fix:**
```python
# Add field selection
query = "list:myfeature.created[@id, @title, @status]"  # Not all fields

# Add select_related/prefetch_related
fields = [
    AttrField("repository", db_name="repository__slug",
        select_related=["repository"]),  # Prevents N+1
]
```

**Test:** Use CaptureQueriesContext to verify query count < 10.

### Relative Date Confusion

**Symptom:** `@created_date:>'-30d'` returns unexpected data

**Explanation:** Relative dates are NOW-relative, not query-range-relative.

`'-30d'` means "30 days before current time", NOT "30 days before query start date".

**Fix if query-relative needed:**
```python
# Use absolute dates from context
query = f"myfeature.created{{@created_date:>'{context.start}'}}"
```

**Not a bug:** This is by design. Document clearly to avoid confusion.

### Scoping Error

**Symptom:** `PqlMissingScopingFiltersError: Missing scoping for Jira`

**Cause:** Provider requires workspace scoping but context doesn't provide it.

**Fix:**
```python
context = ExecutionContext(
    org=org,
    start=start,
    end=end,
    scoping_filters_by_int_auth={
        jira_auth_id: "project:PS OR epic:CTO",  # Add scoping
    }
)
```

**Why intentional:** Better to fail than return wrong data. Scoping is security boundary.

### Variable Literal Treatment

**Symptom:** `{@project:$selectedProject}` treats '$selectedProject' as literal string

**Diagnose:**
1. Check if quoted: `@project:'$var'` ❌ vs `@project:$var` ✅
2. Verify variable in context: `print(context.variables)`
3. Check for typo in variable name

**Fix:**
```python
# Don't quote variables
query = "myfeature.created{@project:$selectedProject}"  # ✅

# Add to context
context.variables = {"selectedProject": "PS"}
```

### EMPTY Keyword Failure

**Symptom:** `{@epic:EMPTY}` doesn't filter for null values

**Cause:** Tag doesn't handle EMPTY keyword

**Fix:**
```python
class EpicTag(AttrTag):
    def __init__(self):
        super().__init__("epic", "Epic", str, db_name="epic_id",
            allow_empty_keyword=True)  # Enable EMPTY support

    def build_filter_clauses(self, db_prefix, single_filter, context):
        value = self._obtain_raw_value(single_filter, context)

        if value == "EMPTY":
            if single_filter.operator.is_equals():
                return None, Q(**{f"{db_prefix}epic_id__isnull": True})
            elif single_filter.operator.is_not_equals():
                return None, Q(**{f"{db_prefix}epic_id__isnull": False})

        return super().build_filter_clauses(db_prefix, single_filter, context)
```

### Stale Data

**Symptom:** Query returns old data, not latest from integration

**Cause:** Query uses cached DB data, not fresh from API

**Diagnose:**
1. Check integration last sync time
2. Verify integration is connected
3. Check if `ignore_cache` needed

**Fix:**
```python
# Force remote fetch
context.ignore_cache = True
result, _ = execute_query(query, context)
```

**Trade-off:** Slower and hits API rate limits. Use sparingly.

### Empty Results

**Symptom:** Expected data, got empty list/zero count

**Diagnostic checklist:**
1. **Date range** - Data within start/end? Try wider range
2. **Scoping** - Do scoping filters exclude data? Check scoping rules
3. **Tag filters** - Too restrictive? Try without filters
4. **Integration** - Connected and syncing? Check integration status
5. **Org isolation** - Querying correct org? Verify context.org

**Procedure:**
```python
# Start with minimal query
result, _ = execute_query("sum:myfeature.created", context)
print(f"Total: {result}")

# Add filters one by one
result, _ = execute_query("sum:myfeature.created{@status:'open'}", context)
print(f"With status: {result}")

# Enable verbose logging
context.be_verbose = True
result, _ = execute_query(query, context)
# Check which filters eliminate results
```

### Field Not Found

**Symptom:** `PQLInvalidSelectorError: Field 'titel' not found`

**Cause:** Typo in field name or field not in fragment's fields list

**Fix:**
```python
# Check available fields
fragment = get_fragment("myfeature.created")
print([field.name for field in fragment.fields])

# Use correct name
query = "list:myfeature.created[@title]"  # Not @titel

# Or add field if missing
fields = [
    AttrField("title", db_name="title"),  # Add this
]
```

### N+1 Query Problem

**Symptom:** List query generates 100+ SQL queries

**Diagnose:**
```python
with CaptureQueriesContext(connection) as queries:
    result, _ = execute_query("list:myfeature.created[@repository]", context)
print(f"{len(queries)} queries")  # Should be < 10
```

**Fix:**
```python
# Add select_related to field
fields = [
    AttrField("repository", db_name="repository__slug",
        select_related=["repository"]),  # Add this
]

# Or override _add_prefetch_related
def _add_prefetch_related(self, query, selectors):
    query = super()._add_prefetch_related(query, selectors)
    if "repository" in selectors:
        query = query.select_related("repository")
    return query
```

**Test:** Add assertion to catch regressions:
```python
def test_no_n_plus_1():
    with CaptureQueriesContext(connection) as queries:
        result, _ = execute_query("list:myfeature.created[@repository]", ctx)
    assert len(queries) < 5, f"N+1 problem: {len(queries)} queries"
```

## Performance Issues

### Slow Query General

**Diagnostic procedure:**
1. Enable verbose logging - check execution time per step
2. Count SQL queries - look for N+1
3. Run EXPLAIN on slow query - check index usage
4. Check result size - maybe returning too much data
5. Check date range - narrower is faster

**Common fixes:**
- Add database indexes on filtered fields
- Add select_related/prefetch_related
- Specify field selection to reduce data
- Narrow date range
- Use scoping filters to pre-filter

### High Memory Usage

**Symptom:** Large list query causes OOM

**Cause:** Result set too large

**Fix:**
```python
# Specify field selection
query = "list:myfeature.created[@id, @title]"  # Not all fields

# Narrow date range
context = ExecutionContext(start=recent_start, end=recent_end, ...)

# Use sum/mean instead of list if possible
query = "sum:myfeature.created"  # Not list
```

### Slow Tag Resolution

**Symptom:** Long delay before query executes

**Cause:** Tag auto-discovery fetching from remote

**Fix:**
```python
class MyFragmentExecutor(LinkedObjectExecutor):
    @property
    def does_autosync_tags(self) -> bool:
        return False  # Use cached tags only
```

**Trade-off:** Faster but potentially stale tag values.

## Testing Issues

### Intermittent Failures

**Symptom:** Tests pass sometimes, fail others

**Common causes:**
- Date-dependent logic using `datetime.now()`
- Non-deterministic ordering without `.order_by()`
- Test data leaking between tests
- Race conditions in async code

**Fix:**
```python
# Use fixed dates
from datetime import datetime
start = datetime(2024, 1, 1)  # Not datetime.now()

# Always order queries
query = MyModel.objects.filter(org=org).order_by("id")  # Add order_by

# Use factory_boy for isolation
MyModelFactory.create_batch(5, org=org)  # Clean data per test

# Use pytest-randomly to catch order dependencies
# It will surface ordering issues quickly
```

### Hitting Real APIs

**Symptom:** Tests slow and require network

**Cause:** Not mocking external API calls

**Fix using VCR:**
```python
import pytest

@pytest.mark.vcr()
def test_with_vcr():
    # First run records HTTP interactions to cassette
    # Subsequent runs replay from cassette (fast, no network)
    context.ignore_cache = True  # Triggers API fetch
    result, _ = execute_query("sum:myfeature.created", context)
```

Per project CLAUDE.md: Use 'vcr' fixture for external calls.

## When to Escalate

Signs of genuine architectural issue requiring core PQL changes:

1. **Modifier order seems wrong** - Maybe security requirements changed
2. **Tag filtering breaks related fragments** - Could be SQL builder bug
3. **Scoping logic backwards** - Might be misunderstanding of requirements
4. **Multi-tenant isolation failing** - Needs immediate attention

For these, file issue with:
- Verbose logs showing problem
- Minimal reproduction case
- Expected vs actual behavior
- Security impact assessment (if applicable)

## Key Files for Debugging

- Main API: `/sleuth/apps/pql/api.py`
- Exceptions: `/sleuth/apps/pql/exceptions.py`
- SQL Builder: `/sleuth/apps/pql/filtering/sql_builder.py`
- Query execution: `/sleuth/apps/pql/linked/querying.py`
- Modifiers: `/sleuth/apps/pql/modifiers/`
- Registry: `/sleuth/apps/pql/registry.py`
