---
name: pql
description: This skill should be used when working with PQL (Project Query Language), Sleuth's custom DSL for querying and aggregating operational metrics. Invoke for tasks like "write a PQL query to count open issues", "implement a new PQL fragment for deployments", "add a filter tag for priority", "debug why my PQL query returns wrong data", or "optimize this slow PQL query".
---

# PQL (Project Query Language)

## Overview

PQL is Sleuth's custom declarative query language for aggregating operational metrics from issues, PRs, incidents, and DORA data. It's purpose-built for time-series analytics with tag-based filtering and built-in aggregators.

**Core syntax:** `[aggregator:]fragment{@tag_filters}[@field_selection]`

**Example:** `sum:issue.created{@status:'open', @priority:>2}[@id, @title]`

## CRITICAL: Multi-Tenant Security

**Every fragment MUST filter by organization.** Sleuth is multi-tenant SaaS. Without org filtering, queries leak data across customers.

```python
# ❌ SECURITY VULNERABILITY - Leaks data across organizations
def _exec_step_build_query(self, org: Organization) -> QuerySet:
    return MyModel.objects.all()

# ✅ CORRECT - First line must filter by org
def _exec_step_build_query(self, org: Organization) -> QuerySet:
    return MyModel.objects.filter(org=org).order_by("id")
```

**This is not optional. This is not a performance optimization. This is a security requirement.**

**Test every fragment** to ensure it only returns data for the specified org. Add assertions: `assert all(item.org == org for item in results)`.

## Core Design Principles

**Tag-based filtering** - Tags (@status, @priority) represent domain concepts, not database columns. Tags map to any filtering logic via Django Q objects. See `references/architecture.md` for why.

**Time-series first** - All queries operate within start/end date ranges. Mean aggregator divides by days (per-day average), not mathematical average. `mean:issue.created` returns "issues created per day on average" not "average of issue counts".

**LinkedObjectExecutor is the default** - 99% of fragments should extend LinkedObjectExecutor, not QueryFragmentExecutor. It provides tag auto-discovery, related fragments, proper execution hooks, and integration with `query_linked_table()`. Only use QueryFragmentExecutor for pure Sleuth data (no external providers).

**Never apply modifiers manually** - Let `query_linked_table()` handle modifier application. Modifiers must apply in security-critical order: IntegrationsModifier → DateModifier → ScopingFiltersModifier → TagFiltersModifier → UserQueryModifier. Manual application bypasses safeguards.

## Common Anti-Patterns

Learn what NOT to do. These mistakes violate PQL's design and cause bugs:

### Anti-Pattern 1: Using QueryFragmentExecutor

```python
# ❌ WRONG - Misses tag auto-discovery, related fragments, proper hooks
class MyFragment(QueryFragmentExecutor):
    pass

# ✅ RIGHT - Use LinkedObjectExecutor for 99% of cases
class MyFragment(LinkedObjectExecutor[MyModel, MyModelTag, MyDateField]):
    pass
```

**When to use QueryFragmentExecutor:** Only for pure Sleuth data with no external providers. If querying GitHub PRs, Jira issues, incidents, or any synced data, use LinkedObjectExecutor.

### Anti-Pattern 2: Applying Modifiers Manually

```python
# ❌ WRONG - Bypasses security-critical modifier ordering
def execute(self, aggregation):
    query = self._build_query(aggregation.org)
    query = self._apply_date_filter(query, aggregation.context.start, aggregation.context.end)
    query = self._apply_tags(query, aggregation.tag_filters)
    return query.count()

# ✅ RIGHT - Let query_linked_table() handle it
def _exec_step_build_query(self, org):
    return MyModel.objects.filter(org=org)
# query_linked_table() automatically applies modifiers in correct order
```

**Why it matters:** Modifier order is security-critical. If tags apply before scoping, users can bypass workspace restrictions.

### Anti-Pattern 3: Missing Standard Tags

```python
# ❌ WRONG - Missing GidTag and IntegrationTag
tags = TagSet([
    AttrTag("status", "Status", str),
])

# ✅ RIGHT - Always include GidTag and IntegrationTag first
tags = TagSet([
    GidTag(MyModel),        # REQUIRED for consistency
    IntegrationTag(),       # REQUIRED for consistency
    AttrTag("status", "Status", str),
])
```

**Why it matters:** GidTag enables filtering by Sleuth ID. IntegrationTag enables filtering by integration source. Missing them breaks UI assumptions.

### Anti-Pattern 4: Mathematical Mean

```python
# ❌ WRONG - Mathematical average (not time-series)
def _exec_step_aggregate_value(self, aggregation: AggregationData, query, selectors):
    if isinstance(aggregation.agg_type, Mean):
        values = query.values_list('count', flat=True)
        return sum(values) / len(values)

# ✅ RIGHT - Per-day average (time-series)
def _exec_step_aggregate_value(self, aggregation: AggregationData, query, selectors):
    if isinstance(aggregation.agg_type, Mean):
        days = get_num_of_days_for_average(aggregation.context.end, aggregation.context.start)
        return query.count() / days
```

**Why it matters:** PQL is for time-series metrics. "Average issues created" without time context is meaningless. "Issues per day on average" is the useful metric.

### Anti-Pattern 5: Production List Queries Without Field Selection

```python
# ❌ WRONG - Returns ALL fields, causes performance issues
query = "list:issue.created{@status:'open'}"

# ✅ RIGHT - Specify exactly what fields you need
query = "list:issue.created{@status:'open'}[@id, @title, @url]"
```

**Why it matters:** Without field selection, PQL returns all fields including prefetched tags. For 1000 issues, this can be 10MB+ response.

### Anti-Pattern 6: Quoting Variables

```python
# ❌ WRONG - Treats "$selectedProject" as literal string
query = "issue.created{@project:'$selectedProject'}"

# ✅ RIGHT - Variables are unquoted
query = "issue.created{@project:$selectedProject}"
context.variables = {"selectedProject": "PS"}
```

## Decision Trees

### Should I use PQL or SQL?

**Use PQL when:**
- Aggregating metrics across time ranges
- Filtering by domain concepts (status, priority, labels)
- Querying data synced from external providers
- Building user-facing dashboards with filters

**Use SQL when:**
- Complex multi-table joins beyond Django relationships
- Non-time-series queries (configuration, settings)
- Performance-critical queries needing hand-tuned SQL
- One-off data analysis scripts

### Should I create a new Fragment or add a Tag?

**Create a new Fragment when:**
- Exposing a completely new data source (e.g., new issue tracker)
- Providing a different time-based view of existing data (e.g., `issue.created` vs `issue.resolved` - different date fields)
- Implementing fundamentally different aggregation logic

**Add a Tag when:**
- Users need to filter existing data by a new attribute
- An integration provides new filterable metadata
- Adding custom filtering logic (date ranges, text search)

**Example:** If users want to filter issues by assignee → add AssigneeTag. If users want to see "issues resolved" vs "issues created" → create separate fragments.

### Which Tag type should I use?

**AttrTag** - For database columns (most common):
```python
AttrTag("status", "Status", str, db_name="status")
```

**LinkedTag** - For provider-specific metadata from LinkedTag tables:
```python
LinkedTag("labels", "Labels", str, allow_empty_keyword=True)
```

**Custom Tag (extend TagABC)** - For complex logic not mappable to single column:
```python
class LeadTimeBucketTag(TagABC):
    # Converts "elite" → timedelta, filters by range
```

**GidTag** - ALWAYS include (Sleuth global IDs)
**IntegrationTag** - ALWAYS include (filter by integration source)

## Writing PQL Queries

### Execute a Query

```python
from sleuth.apps.pql.api import execute_query
from sleuth.apps.pql.parsing.exec_context import ExecutionContext

context = ExecutionContext(
    org=my_org,          # REQUIRED
    start=start_date,    # REQUIRED
    end=end_date,        # REQUIRED
    integration_contexts=contexts,
    variables={"user": "john"}
)

result, help_text = execute_query(
    "sum:issue.created{@status:'open', @assignee:$user}",
    context
)
```

### When to Use PQL

Use for:
- Aggregating metrics across time ranges
- Filtering by domain concepts (status, priority, assignee)
- Combining data sources (issues + PRs)
- User-defined filters in dashboards

Don't use for:
- Complex multi-table joins (use SQL)
- Real-time streaming data
- Non-time-series data (configuration, settings)

## Implementing a Fragment

### High-Level Structure

Every fragment needs:

1. **Extend LinkedObjectExecutor** with type parameters: `[MyModel, MyModelTag, MyDateField]`
2. **Define fields** - What data can be returned in list queries
3. **Define tags** - What filters users can apply (ALWAYS include GidTag + IntegrationTag)
4. **Declare aggregators** - Which aggregators work (usually `[Sum, Mean, List]`)
5. **Implement required methods**:
   - `_date_field` property - Which date field to filter/sort by
   - `_exec_step_build_query()` - Build base QuerySet (MUST filter by org)
   - `_exec_step_aggregate_value()` - Handle each aggregator type
   - `_get_tags_query()` - How to fetch tags from database

6. **Register in `/sleuth/apps/myapp/pql.py`**:
   ```python
   fragments = [MyFragmentExecutor(measure_name="myfeature.created")]
   ```

### Example Fragment (Minimal)

```python
from sleuth.apps.pql.parsing.agg_captor import AggregationData

class MyFragmentExecutor(LinkedObjectExecutor[MyModel, MyModelTag, MyDateField]):
    fields = [AttrField("id"), ValueField(), AttrField("title")]
    tags = TagSet([GidTag(MyModel), IntegrationTag(), AttrTag("status", "Status", str)])
    aggregators = [Sum, Mean, List]

    @property
    def _date_field(self) -> MyDateField:
        return MyDateField.CREATED_DATE

    def _exec_step_build_query(self, org: Organization) -> QuerySet:
        return MyModel.objects.filter(org=org).order_by("id")  # ✅ org filter!

    def _exec_step_aggregate_value(self, aggregation: AggregationData, query, selectors):
        if isinstance(aggregation.agg_type, Sum):
            return query.count()
        elif isinstance(aggregation.agg_type, Mean):
            return query.count() / get_num_of_days_for_average(aggregation.context.end, aggregation.context.start)
        elif isinstance(aggregation.agg_type, List):
            return self.build_list_result(query, selectors)
```

**For complete implementation patterns, see `references/implementation.md`.**

**For field types, tag implementation, and optimization patterns, see `references/implementation.md`.**

## Testing Requirements

**Every fragment MUST have tests.** PQL is security-critical. Untested code causes data leakage and incorrect metrics.

### Required Test Cases

1. **Org isolation** - Verify fragment only returns data for specified org:
   ```python
   def test_org_isolation():
       org1, org2 = OrganizationFactory.create_batch(2)
       MyModelFactory.create_batch(5, org=org1)
       MyModelFactory.create_batch(3, org=org2)

       result, _ = execute_query("sum:myfeature.created", context_for_org1)
       assert result == 5  # Only org1 data
   ```

2. **Aggregators work correctly** - Test Sum, Mean, List for each fragment
3. **Tag filtering** - Verify each tag actually filters results
4. **Field selection** - Ensure list queries return correct fields
5. **Performance** - Use `CaptureQueriesContext` to detect N+1 queries

### Testing Best Practices

- Use `pytest` with `--reuse-db` flag: `uv run pytest --reuse-db path/to/test.py`
- Use `factory_boy` factories for test data (see `/tests/factories.py`)
- Use `vcr` fixture for external API calls (per CLAUDE.md)
- Add assertions for org filtering: `assert all(item.org == org for item in results)`
- Test with multiple aggregators to ensure fragment handles all declared types

**For complete testing patterns, see `references/implementation.md` (Testing Patterns section).**

## Execution Pipeline

```
PQL String → Grammar → Parser → AST
  ↓
Registry → Lookup fragment
  ↓
Fragment._exec_step_build_query() → Base QuerySet with org filter
  ↓
Query Modifiers (in order):
  1. IntegrationsModifier
  2. DateModifier
  3. ScopingFiltersModifier
  4. TagFiltersModifier
  5. UserQueryModifier
  ↓
Fragment._exec_step_aggregate_value() → Compute result
  ↓
Return (result, help_text)
```

## Debugging Quick Reference

**Enable verbose logging to see execution steps:**
```python
context.be_verbose = True
result, _ = execute_query(query, context)
```

**Check what's registered:**
```python
from sleuth.apps.pql.registry import get_fragment
fragment = get_fragment("myfeature.created")
print([tag.name for tag in fragment.tags])  # All available tags
```

**Detect N+1 queries:**
```python
from django.test.utils import CaptureQueriesContext
from django.db import connection

with CaptureQueriesContext(connection) as queries:
    result, _ = execute_query(query, context)
print(f"{len(queries)} queries")  # Should be < 10
```

**Common issues:**
- **Fragment not found** → Check `/sleuth/apps/{app}/pql.py` exists with `fragments` list
- **Tag filter ignored** → Verify tag in fragment's TagSet
- **Wrong org data** → Missing `.filter(org=org)` in `_exec_step_build_query()` (SECURITY BUG)
- **List query timeout** → Add field selection: `list:fragment[@id, @title]`
- **PqlMissingScopingFiltersError** → Intentional. Add scoping to context or fix integration config.

**For comprehensive troubleshooting procedures, see `references/troubleshooting.md`.**

## Reference Documentation

SKILL.md provides workflow guidance and anti-patterns. For deep implementation details, load these references:

### `references/architecture.md` - WHY Things Work This Way

Load when you need to understand design rationale or are debugging unexpected behavior.

**Contains:**
- Query modifier ordering and why it matters for security
- Scoping logic (complex OR pattern)
- Why tags aren't database columns
- Why mean is per-day not mathematical average
- Why relative dates are NOW-relative
- All major design decisions with trade-offs explained

**Use when:** Questioning "why does PQL work this way?" or "can I change this pattern?"

### `references/implementation.md` - HOW to Implement Features

Load when implementing fragments, tags, or advanced patterns beyond basic examples.

**Contains:**
- Multi-step execution hooks (when to override each)
- Related fragments implementation
- Fragment variations
- Custom tag patterns with value transformation
- Tag options (dropdowns, enums, custom functions)
- EMPTY keyword support
- Performance optimization patterns
- Complete testing patterns with factories and VCR

**Use when:** Implementing new fragments/tags or need patterns beyond SKILL.md examples.

### `references/troubleshooting.md` - Fixing Problems

Load when queries fail, return wrong data, or perform poorly.

**Contains:**
- Diagnostic procedures for all common issues
- SQL query counting and N+1 detection
- Fragment discovery debugging
- Org isolation breach detection
- Performance issue diagnosis
- Testing issue patterns (intermittent failures, hitting real APIs)
- When to escalate to architectural changes

**Use when:** Something isn't working and you need systematic diagnostic procedures.

## Key File Locations

| Component | Location |
|-----------|----------|
| API | `/sleuth/apps/pql/api.py` |
| Grammar | `/sleuth/apps/pql/parsing/grammar.py` |
| Parser | `/sleuth/apps/pql/parsing/parsing.py` |
| Fragment base | `/sleuth/apps/pql/processor.py` |
| LinkedObjectExecutor | `/sleuth/apps/pql/linked/linked_query_executor.py` |
| Registry | `/sleuth/apps/pql/registry.py` |
| Tags | `/sleuth/apps/pql/filtering/tag.py` |
| Common tags | `/sleuth/apps/pql/filtering/common_tags.py` |
| SQL builder | `/sleuth/apps/pql/filtering/sql_builder.py` |
| Query modifiers | `/sleuth/apps/pql/modifiers/` |

**Example fragments:**
- `/sleuth/apps/issue/pql_issue.py`
- `/sleuth/apps/dora/tracker/pr_merged/pql_merged_pr_fragment.py`
- `/sleuth/apps/incident/pql_incident.py`
