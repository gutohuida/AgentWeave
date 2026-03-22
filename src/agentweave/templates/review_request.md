# Review Request

**Task:** {{ task_title }}  
**Task ID:** {{ task_id }}  
**Submitted By:** {{ author }}  
**Date:** {{ date }}  
**Requested Reviewer:** {{ reviewer }}

## Review Scope

- [ ] Full review (correctness, security, style, performance)
- [ ] Security-focused
- [ ] Performance-focused
- [ ] Style / conventions only
- [ ] Specific concern: [describe]

---

## Summary

{{ summary }}

## Changes

{% for change in changes %}
- **{{ change.file }}**: {{ change.description }}
{% endfor %}

## Testing

{% if tests %}
- [x] Tests written and passing
- Coverage: {{ coverage }}%
{% else %}
- [ ] Tests pending
{% endif %}

## Verification Steps for Reviewer

Before approving, run:
```bash
# {{ test_command }}
# {{ lint_command }}
```
Expected: all tests pass, no lint errors.

Security checklist:
- [ ] No hardcoded secrets or credentials
- [ ] External input is validated at system boundaries
- [ ] No injection vectors (SQL, shell, path traversal)
- [ ] No new dependencies with known CVEs

## Specific Areas for Review

Please focus on:

{% for area in focus_areas %}
- [ ] {{ area }}
{% endfor %}

---

## Review Response Template

**Reviewer:** {{ reviewer }}  
**Date:** {{ review_date }}

### Overall Assessment
- [ ] **APPROVED** - Ready to merge
- [ ] **NEEDS_REVISION** - Changes required
- [ ] **DISCUSSION_NEEDED** - Need to discuss

### Feedback

**What's Good:**
{% for good in feedback_good %}
- {{ good }}
{% endfor %}

**Suggestions:**
{% for suggestion in feedback_suggestions %}
- {{ suggestion }}
{% endfor %}

**Required Changes (if any):**
{% for change in required_changes %}
- [ ] {{ change }}
{% endfor %}

### Next Steps
{{ next_steps }}
