# PQL Architecture Reference

System design decisions and their rationale. Load when understanding why PQL behaves a certain way or when debugging unexpected behavior.

## Query Modifier Ordering

Modifiers apply in this exact sequence:

1. **IntegrationsModifier** - Filter to specified integration instances
2. **DateModifier** - Apply date range filtering
3. **ScopingFiltersModifier** - Apply workspace-level scoping rules
4. **TagFiltersModifier** - Apply user-specified tag filters from query
5. **UserQueryModifier** - Apply user/team filters

**Why this order matters:**

- **Integrations first**: Narrow scope immediately before expensive operations
- **Date second**: Leverage database indexes early for high selectivity
- **Scoping before tags**: Security boundary. Scoping limits what users CAN query; tags express what users WANT to query. Scoping must win.
- **Tags fourth**: User intent expressed in query
- **Users last**: Optional personalization, least critical filter

**What breaks if order changes:**

```python
# ❌ SECURITY VULNERABILITY - If tags applied before scoping
# User could do: issue.created{@project:'ADMIN_PROJECT'}
# Even if their scoping only allows @project:'USER_PROJECT'
# Tags would filter first, bypassing scoping restriction

# ✅ CORRECT ORDER - Scoping before tags
# 1. Scoping applies: (integration=A AND project=USER_PROJECT)
# 2. Tags apply: (previous filters) AND (project='ADMIN_PROJECT')
# Result: Empty set. User can't see ADMIN_PROJECT data.
```

**Changing this order breaks security.** If tags apply before scoping, users can bypass workspace restrictions by crafting specific queries.

**Location:** `/sleuth/apps/pql/linked/querying.py` in `query_linked_table()`

**Never manually apply modifiers.** Always use `query_linked_table()` which enforces correct ordering.

## Scoping Logic: Complex OR

Scoping uses OR between integrations, AND within each integration's rules:

```
(int_auth=A AND (project=PS OR epic=CTO))
OR
(int_auth=B AND project=SL)
OR
(int_auth IN (C, D))  # No scoping rules
```

**Rationale:** Each integration has independent scoping rules. Query should return data from ANY integration that passes ITS scoping, not require all integrations to pass the same rule.

**Implementation:** `/sleuth/apps/pql/modifiers/scoping_modifier.py` builds this complex Q object by grouping integrations with same scoping, then ORing groups together.

**Why not simpler logic:** Can't use global scoping like `(project=PS) AND (int_auth IN [A,B,C])` because:
- Integration A might need "project=PS OR epic=CTO"
- Integration B might need "project=SL"
- Integration C might have no scoping
These requirements conflict at global level but work at per-integration level.

## Tag System Design Decision

**Core decision:** Tags represent domain concepts, not database columns.

**Rationale:**
- **Abstraction** - Users don't need to know `repository__slug` vs `repository__name`
- **Provider differences** - Jira "project" and Linear "team" both map to `@project`
- **Complex logic** - `@lead_time:'elite'` converts to time range, can't express as simple column filter
- **Dynamic sources** - LinkedTags come from remote APIs, can't hardcode as columns

**Implementation:** Tags implement `build_filter_clauses(db_prefix, single_filter, context) -> (Alias | None, Q)`. SQL builder combines Q objects.

**Trade-off:** More complex than direct SQL generation, but provides flexibility and consistency across providers.

## Mean Aggregator: Per-Day Not Average

**Decision:** `mean:fragment` divides count by days in date range.

**Rationale:** PQL is time-series focused. "Average issues created" without time context is meaningless. Useful metric is "issues per day on average."

**Implementation:**
```python
days = get_num_of_days_for_average(aggregation.context.end, aggregation.context.start)
return query.count() / days
```

**Why not mathematical average:** If fragments tracked numeric values, `mean` would average those. But most fragments count occurrences. For occurrence data, per-day rate is more useful than mathematical average.

**User confusion:** This trips up users expecting mathematical average. Document prominently.

## Relative Dates: NOW-Relative

**Decision:** `@created_date:>'-30d'` means "30 days before NOW", not "30 days before query start".

**Rationale:**
- Simpler implementation (no context-awareness needed in date parser)
- Matches Jira's relative date behavior (familiar to users)
- Useful for "recent activity" queries that should update as time passes

**Implementation:** Date parser converts '-30d' to `datetime.now() - timedelta(days=30)` during query parsing, before execution context is available.

**Trade-off:** Confusing when query has explicit date range. User thinks "-30d" means "30 days from query start" but actually means "30 days from now".

**Alternative not chosen:** Making relative dates context-aware would require passing full context to parser, complicating architecture.

## EMPTY Keyword

**Decision:** Reserved keyword for null checks, not a string value.

**Rationale:** SQL NULL can't be expressed as string value. `@epic:null` and `@epic:None` are string literals "null"/"None". Need special syntax for absence.

**Why not different syntax:** Could use `@epic:IS_NULL` or `@epic:__null__` but `EMPTY` is clearer and matches business language ("empty epic field").

**Implementation:** Tags check `if value == "EMPTY"` and return `Q(field__isnull=True)`.

**Gotcha:** Must be unquoted: `@epic:EMPTY` not `@epic:'EMPTY'`. Parser recognizes unquoted EMPTY as keyword.

## LinkedObjectExecutor Pattern

**Decision:** Separate base class for linked objects instead of making QueryFragmentExecutor handle everything.

**Rationale:**
- **90% of fragments** query linked objects (GitHub PRs, Jira issues, incidents)
- **Common patterns**: All need tag auto-discovery, related fragments, remote API fetching
- **Without it**: Each fragment reimplements same infrastructure, bugs appear in multiple places

**Trade-off:** More complex class hierarchy, but fragments become trivial to implement (just override 3-4 methods).

**When to use LinkedObjectExecutor (99% of cases):**
```python
# ✅ Use LinkedObjectExecutor for:
- Data synced from external providers (GitHub, Jira, PagerDuty)
- Objects with provider-specific tags (labels, components, milestones)
- Objects needing related fragments (PRs with issues, issues with PRs)
- Objects fetched via integration APIs

# Examples: LinkedIssue, MergedPR, Incident, LinkedReview
```

**When to use QueryFragmentExecutor (1% of cases):**
```python
# ✅ Use QueryFragmentExecutor only for:
- Pure Sleuth internal data (not from providers)
- Simple aggregations without tags or field selection
- Custom queries that don't fit linked object pattern

# Examples: Internal metrics, configuration counts
# NOTE: Even for internal data, LinkedObjectExecutor often works better
```

**Why QueryFragmentExecutor exists:** Historical reasons. Before LinkedObjectExecutor existed, all fragments extended QueryFragmentExecutor directly. LinkedObjectExecutor was extracted to eliminate code duplication across 90% of fragments. QueryFragmentExecutor remains as the base interface, but direct usage is rare.

**If you're implementing a fragment and unsure which to use: Choose LinkedObjectExecutor.** It's almost always the right choice.

## Fragment Auto-Discovery

**Decision:** Registry auto-discovers via `load_modules("pql", "fragments")` instead of manual registration.

**Rationale:**
- **Scaling**: As fragments grow, manual registration becomes error-prone
- **Convention**: Standardizes location (`/sleuth/apps/{app}/pql.py`)
- **Discoverability**: Easy to find all fragments by searching for `pql.py` files

**How it works:**
1. Registry calls `load_modules("pql", "fragments")`
2. Imports every `/sleuth/apps/*/pql.py` module
3. Collects `fragments` list from each
4. Builds measure_name → fragment executor mapping

**Trade-off:** Import errors in one pql.py break all fragment discovery. But this forces fixing issues immediately rather than hiding them.

## Variables: Unquoted Syntax

**Decision:** Variables use `@field:$var` syntax (unquoted), not `@field:'$var'` (quoted).

**Rationale:**
- **Type flexibility**: Variable could be string, int, or list. Quoting implies string.
- **Clear intent**: Unquoted signals "this is a placeholder" not "literal value"
- **Consistency**: Matches other template systems (Jinja, Handlebars use unquoted variables)

**Implementation:** Parser recognizes unquoted `$identifier` as variable token. Tag system calls `_obtain_raw_value()` which substitutes from `context.variables` before type conversion.

**Gotcha:** Users often quote variables by accident. Validation should catch this.

## Query Result Type Safety

**Decision:** Query results are type-specific (int for Sum, float for Mean, list[dict] for List), not generic "Any".

**Rationale:**
- **UI expectations**: Frontend needs to know result shape
- **Error catching**: Type errors caught at fragment level, not in UI
- **Documentation**: Result type is self-documenting

**Implementation:** `_exec_step_aggregate_value()` returns type matching aggregator:
- Sum → int
- Mean → float
- List → list[dict]
- Latest → dict | None
- Concat → str

**Trade-off:** Fragments must handle all declared aggregators. Can't partially implement.

## Multi-Tenant Isolation: Mandatory Org Filter

**Decision:** Every fragment MUST filter by org in `_exec_step_build_query()`. No exceptions.

**Rationale:** Sleuth is multi-tenant SaaS. Without org filtering, queries leak data across organizations. This is a security vulnerability, not a performance issue.

**Enforcement:** Code review and testing. Automated check would be ideal but doesn't exist yet.

**Why not enforced at framework level:** QueryFragmentExecutor is abstract base for flexibility. Enforcing at framework level would require making assumptions about model structure that don't always hold.

**Best practice:** First line of `_exec_step_build_query()` should always be `.filter(org=org)`.

## Field Selection: Explicit is Better

**Decision:** Without field selection, `list:` queries return ALL fields. With selection, return only specified fields.

**Rationale:**
- **Default convenience**: For quick queries, getting everything is useful
- **Production optimization**: Dashboards should specify fields to reduce payload
- **Progressive disclosure**: Simple queries are simple; complex queries are explicit

**Implementation:** `build_list_result()` checks if selectors provided. If yes, extract only those fields. If no, extract all fields from `fields` list.

**Trade-off:** Default behavior is slow for large datasets. But making field selection required would complicate simple queries.

**Gotcha:** Forgetting field selection in production queries causes performance issues.

## Related Fragments: Cross-Reference Pattern

**Decision:** Related fragments defined statically in `_get_related_fragments()`, not discovered dynamically.

**Rationale:**
- **Explicit relationships**: Clear which fragments can cross-reference
- **Type safety**: Related fragment knows expected model types
- **Performance**: No runtime discovery overhead
- **Debugging**: Easy to trace which fragments are related

**Implementation:** Fragment declares relationships, tag system checks for prefixed tags (`pr_repository`), queries through Django relationship (`db_field`).

**Limitation:** Can only relate fragments with Django model relationships. Can't relate arbitrary fragments.

## File Organization Philosophy

**Convention:** PQL code lives in dedicated modules to avoid circular imports and clarify ownership.

- Grammar/Parser: `/sleuth/apps/pql/parsing/`
- Fragments: `/sleuth/apps/{app}/pql*.py`
- Tags: Fragment-specific or `/sleuth/apps/pql/filtering/common_tags.py`
- Modifiers: `/sleuth/apps/pql/modifiers/`

**Rationale:**
- **Circular imports**: PQL references models, models shouldn't reference PQL
- **Cohesion**: Related PQL code stays together
- **Discovery**: Easy to find all PQL code with pattern matching

**Trade-off:** More files, but clearer separation of concerns.

## Common Architectural Violations

Understanding these violations helps prevent bugs and security issues:

### Violation 1: Manually Applying Modifiers

```python
# ❌ ARCHITECTURAL VIOLATION
def execute(self, aggregation):
    query = MyModel.objects.filter(org=aggregation.org)
    query = apply_date_filter(query, aggregation.context.start, aggregation.context.end)
    query = apply_scoping(query, aggregation.context.scoping)
    query = apply_tags(query, aggregation.tag_filters)
    return query.count()

# ✅ CORRECT ARCHITECTURE
def _exec_step_build_query(self, org):
    return MyModel.objects.filter(org=org).order_by("id")
# Let query_linked_table() handle all modifier application
```

**What breaks:** Security. Manual application can apply modifiers in wrong order, allowing users to bypass scoping.

### Violation 2: Treating Tags as Database Columns

```python
# ❌ ARCHITECTURAL VIOLATION
def apply_status_filter(query, status_value):
    return query.filter(status=status_value)  # Assumes status is column

# ✅ CORRECT ARCHITECTURE
class StatusTag(AttrTag):
    def build_filter_clauses(self, db_prefix, single_filter, context):
        value = self._obtain_raw_value(single_filter, context)
        return None, Q(**{f"{db_prefix}status": value})
```

**What breaks:** Flexibility. Can't handle provider differences, complex logic, or dynamic tag sources.

### Violation 3: Using Mathematical Average for Mean

```python
# ❌ ARCHITECTURAL VIOLATION
values = [query.filter(date=d).count() for d in date_range]
return sum(values) / len(values)  # Mathematical average

# ✅ CORRECT ARCHITECTURE
days = get_num_of_days_for_average(aggregation.context.end, aggregation.context.start)
return query.count() / days  # Per-day average
```

**What breaks:** Conceptual model. PQL is time-series. "Average" without time dimension is meaningless.

### Violation 4: Forgetting Org Filter

```python
# ❌ SECURITY VULNERABILITY
def _exec_step_build_query(self, org):
    return MyModel.objects.all()  # Missing org filter

# ✅ CORRECT ARCHITECTURE
def _exec_step_build_query(self, org):
    return MyModel.objects.filter(org=org).order_by("id")  # ✅ org filter first line
```

**What breaks:** Multi-tenant isolation. Queries return data from ALL organizations, leaking sensitive customer data.

## Key Files

- Query execution: `/sleuth/apps/pql/api.py`
- Grammar: `/sleuth/apps/pql/parsing/grammar.py`
- Parser: `/sleuth/apps/pql/parsing/parsing.py`
- Registry: `/sleuth/apps/pql/registry.py`
- SQL builder: `/sleuth/apps/pql/filtering/sql_builder.py`
- Linked querying: `/sleuth/apps/pql/linked/querying.py` (modifier application happens here)
- Scoping modifier: `/sleuth/apps/pql/modifiers/scoping_modifier.py`
