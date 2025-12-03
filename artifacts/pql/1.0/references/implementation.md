# PQL Implementation Reference

Deep-dive implementation patterns for fragments and tags. Load when implementing new PQL features beyond the basic patterns in SKILL.md.

## Fragment Implementation Patterns

### Multi-Step Execution Hooks

LinkedObjectExecutor provides hooks at each execution step. Override only what's needed:

```python
from sleuth.apps.pql.parsing.agg_captor import AggregationData

def _exec_step_pre_execute(self, aggregation: AggregationData) -> None:
    """Validation or setup before execution. Rarely needed."""
    pass

def _exec_step_ignore_cache(self, aggregation: AggregationData) -> None:
    """Fetch from remote API if context.ignore_cache is True."""
    if aggregation.context.ignore_cache:
        fetch_and_store_data(org=aggregation.org, contexts=aggregation.context.integration_contexts)

def _exec_step_build_query(self, org: Organization) -> QuerySet[T]:
    """Build base QuerySet. MUST filter by org."""
    return MyModel.objects.filter(org=org).order_by("id")

def _exec_step_aggregate_value(self, aggregation: AggregationData, query, selectors) -> Any:
    """Execute aggregation based on aggregation.agg_type."""
    # Handle Sum, Mean, List, etc.

def _exec_step_choose_custom_integration_auth_field(self, aggregation: AggregationData) -> str | None:
    """Override if integration field isn't 'integration_auth_id'."""
    return None  # Uses default
```

**Execution order:** pre_execute → ignore_cache → build_query → query_linked_table() → aggregate_value

**Critical:** Don't apply query modifiers manually. `query_linked_table()` applies them automatically in the correct order.

### Related Fragments

Enable cross-filtering and field selection across fragments:

```python
@classmethod
def _get_related_fragments(cls) -> list[RelatedFragment]:
    return [
        RelatedFragment(
            label="Pull request",
            fragment_measure="dora.frequency.pr_merged",
            tag_prefix="pr_",
            db_field="pull_requests",  # Django relationship path
            supported_providers=CODE_SOURCE_PROVIDERS,
        )
    ]
```

**Enables:**
- Filter by related data: `issue.created{@pr_repository:'sleuth-io/pulse'}`
- Select related fields: `issue.created[@id, @pr_title, @pr_merged_at]`

**Gotcha:** `db_field` must be valid Django relationship. If relationship doesn't exist, queries fail with SQL errors.

### Fragment Variations

Share implementation across multiple measure names:

```python
from sleuth.apps.pql.linked.variation import LinkedVariation

class IssueCreatedFragment(LinkedObjectExecutor[...]):
    # Implementation here
    pass

class IssueResolvedFragment(LinkedObjectExecutor[...]):
    @property
    def _date_field(self) -> IssueDateField:
        return IssueDateField.RESOLVED_DATE  # Different date field
    # Everything else inherited
    pass

# Or use variations:
fragments = [
    LinkedVariation(
        IssueCreatedFragment,
        measure_name="issue.created",
        date_field=IssueDateField.CREATED_DATE
    ),
    LinkedVariation(
        IssueCreatedFragment,
        measure_name="issue.resolved",
        date_field=IssueDateField.RESOLVED_DATE
    ),
]
```

### Optimization Patterns

**Automatic prefetch based on selectors:**

```python
def _add_prefetch_related(self, query: QuerySet[T], selectors) -> QuerySet[T]:
    """Called automatically before aggregation. Override for custom optimization."""
    query = super()._add_prefetch_related(query, selectors)

    # Add conditional prefetch based on what fields are selected
    if "pr_title" in selectors:
        query = query.prefetch_related("pull_requests__repository")

    return query
```

**Field-level optimization:**

```python
fields = [
    AttrField("repository", db_name="repository__slug",
        select_related=["repository"]),  # JOIN optimization
    AttrField("assignees", db_name="assignees__user__email",
        prefetch_related=["assignees__user"]),  # Separate query optimization
]
```

## Tag Implementation Patterns

### Custom Tag with Operator Support

```python
class PriorityTag(TagABC):
    def __init__(self):
        super().__init__(name="priority", label="Priority", value_type=int)

    def build_filter_clauses(self, db_prefix, single_filter, context):
        value = self._obtain_raw_value(single_filter, context)
        operator = single_filter.operator

        if operator.is_equals():
            return None, Q(**{f"{db_prefix}priority": value})
        elif operator.is_greater_than():
            return None, Q(**{f"{db_prefix}priority__gt": value})
        elif operator.is_less_than():
            return None, Q(**{f"{db_prefix}priority__lt": value})
        elif operator.is_not_equals():
            return None, ~Q(**{f"{db_prefix}priority": value})

        raise ValueError(f"Unsupported operator: {operator}")
```

### Value Transformation

Override `_refine_raw_value()` to transform values before filtering:

```python
class LeadTimeBucketTag(TagABC):
    def _refine_raw_value(self, raw_value):
        """Convert bucket name to timedelta range."""
        bucket_map = {
            "elite": timedelta(hours=24),
            "high": timedelta(days=7),
            "medium": timedelta(days=30),
            "low": timedelta(days=365),
        }
        return bucket_map[raw_value.lower()]

    def build_filter_clauses(self, db_prefix, single_filter, context):
        max_time = self._obtain_raw_value(single_filter, context)
        return None, Q(**{f"{db_prefix}lead_time__lt": max_time})
```

### Tag Options Patterns

**Custom options with search:**

```python
def custom_options_fn(contexts, *, obj_query, term, **kwargs):
    """Generate options dynamically. Called when UI needs dropdown values."""
    org = contexts[0].org

    query = obj_query.filter(org=org).values_list('repository__slug', flat=True).distinct()

    if term:  # Filter by search term
        query = query.filter(repository__slug__icontains=term)

    repos = list(query[:50])  # Limit results
    return [(repo, repo) for repo in repos if repo]

AttrTag(
    "repository", "Repository", str,
    options_source=OptionsSource.CUSTOM,
    options_config=OptionsCustomConfig(custom_fn=custom_options_fn)
)
```

**Enum options:**

```python
class PriorityChoices(IntegerChoices):
    LOW = 1, "Low"
    MEDIUM = 2, "Medium"
    HIGH = 3, "High"

AttrTag("priority", "Priority", PriorityChoices,
    options_source=OptionsSource.ENUM)
```

### EMPTY Keyword Support

```python
class EpicTag(AttrTag):
    def __init__(self):
        super().__init__("epic", "Epic", str, db_name="epic_id",
            allow_empty_keyword=True)

    def build_filter_clauses(self, db_prefix, single_filter, context):
        value = self._obtain_raw_value(single_filter, context)

        if value == "EMPTY":
            if single_filter.operator.is_equals():
                return None, Q(**{f"{db_prefix}epic_id__isnull": True})
            elif single_filter.operator.is_not_equals():
                return None, Q(**{f"{db_prefix}epic_id__isnull": False})

        # Normal value filtering
        return super().build_filter_clauses(db_prefix, single_filter, context)
```

## Advanced Patterns

### Conditional Fragment Behavior

```python
def _exec_step_build_query(self, org: Organization) -> QuerySet[MyModel]:
    query = MyModel.objects.filter(org=org)

    # Conditional logic based on context
    if self._date_field == MyDateField.RESOLVED_DATE:
        query = query.exclude(resolved_date__isnull=True)

    return query.order_by("id")
```

### Custom Aggregator Implementation

```python
def _exec_step_aggregate_value(self, aggregation: AggregationData, query, selectors):
    if isinstance(aggregation.agg_type, Sum):
        return query.count()

    elif isinstance(aggregation.agg_type, Mean):
        days = get_num_of_days_for_average(aggregation.context.end, aggregation.context.start)
        return query.count() / days

    elif isinstance(aggregation.agg_type, List):
        return self.build_list_result(query, selectors)

    elif isinstance(aggregation.agg_type, Latest):
        latest = query.order_by('-created_date').first()
        if not latest:
            return None
        return self.extract_fields(latest, selectors)

    elif isinstance(aggregation.agg_type, Concat):
        values = query.values_list('title', flat=True)
        return ', '.join(str(v) for v in values if v)
```

### Complex Relationship Filtering

```python
class RepositoryOwnerTag(TagABC):
    """Filter by repository owner, handling multi-level relationships."""

    def build_filter_clauses(self, db_prefix, single_filter, context):
        value = self._obtain_raw_value(single_filter, context)

        # Navigate through relationships: issue → pr → repository → owner
        return None, Q(**{
            f"{db_prefix}pull_requests__repository__owner": value
        })
```

## Testing Patterns

### Factory Setup

```python
# In tests/factories.py
class MyModelFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MyModel

    org = factory.SubFactory(OrganizationFactory)
    gid = factory.Sequence(lambda n: f"mymodel_{n}")
    status = "open"
    created_date = factory.Faker('date_time_this_year')

# In tests
def test_fragment():
    org = OrganizationFactory()
    MyModelFactory.create_batch(5, org=org, status='open')
    MyModelFactory.create_batch(3, org=org, status='closed')

    ctx = ExecutionContext(org=org, start=start, end=end)
    result, _ = execute_query("sum:mymodel.created{@status:'open'}", ctx)

    assert result == 5
```

### Query Count Assertions

```python
def test_list_query_performance():
    """Ensure list queries don't have N+1 problems."""
    MyModelFactory.create_batch(10, org=org)

    with CaptureQueriesContext(connection) as queries:
        result, _ = execute_query(
            "list:mymodel.created[@id, @repository]",
            context
        )

    # Should be ~3 queries: 1 main, 1 prefetch, 1 count
    assert len(queries) < 5, f"Too many queries: {len(queries)}"
```

### VCR for External APIs

```python
@pytest.mark.vcr()
def test_fragment_with_remote_fetch():
    """Test fragment that fetches from external API."""
    context = ExecutionContext(org=org, ignore_cache=True, ...)

    result, _ = execute_query("sum:mymodel.created", context)
    # VCR records first run, replays subsequent runs
```

## File Locations

- LinkedObjectExecutor: `/sleuth/apps/pql/linked/linked_query_executor.py`
- QueryFragmentExecutor: `/sleuth/apps/pql/processor.py`
- Tag base: `/sleuth/apps/pql/filtering/tag.py`
- Common tags: `/sleuth/apps/pql/filtering/common_tags.py`
- Related fragments: `/sleuth/apps/pql/linked/related_fragment.py`
- Variations: `/sleuth/apps/pql/linked/variation.py`
- Tag options: `/sleuth/apps/pql/filtering/tag_options.py`

**Example implementations:**
- Issues: `/sleuth/apps/issue/pql_issue.py`
- DORA PRs: `/sleuth/apps/dora/tracker/pr_merged/pql_merged_pr_fragment.py`
- Incidents: `/sleuth/apps/incident/pql_incident.py`
- Custom tags: `/sleuth/apps/dora/tracker/pr_merged/pql_custom_tags.py`
