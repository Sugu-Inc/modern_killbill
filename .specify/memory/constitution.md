# Platform Constitution

This document defines the core principles that govern how we build and maintain code, tests, and user experiences across the platform.

---

## I. Code Quality Principles

### 1. No Code is Best Code

**Rationale**: The most maintainable code is code that doesn't exist. Every line of code is a liability that must be read, understood, maintained, and debugged.

**In Practice**:
- Before writing new code, exhaust all possibilities: Can existing functionality be reused? Can configuration solve this? Can we simplify requirements?
- Prefer declarative solutions over imperative ones
- Delete dead code immediately - commented-out code is technical debt
- Question every abstraction: does this truly reduce complexity, or just move it?

**Anti-patterns**:
- ❌ Creating utility functions used in only one place
- ❌ Premature abstractions "for future flexibility"
- ❌ Wrapper classes that add no value
- ❌ Configuration options for scenarios that will never occur

### 2. Write Succinct and Precise Code

**Rationale**: Code should express intent clearly and directly. Verbosity obscures meaning and increases cognitive load.

**In Practice**:
- Name things precisely - let names carry meaning so comments become unnecessary
- One responsibility per function/component
- Functions should fit on one screen when possible
- Avoid intermediate variables that don't clarify intent
- Use language idioms and features appropriately

**Example**:
```typescript
// ❌ Verbose
function checkIfUserIsAuthorized(user: User, resource: Resource): boolean {
  const userPermissions = user.getPermissions();
  const requiredPermissions = resource.getRequiredPermissions();
  let isAuthorized = false;
  for (const permission of requiredPermissions) {
    if (userPermissions.includes(permission)) {
      isAuthorized = true;
      break;
    }
  }
  return isAuthorized;
}

// ✅ Succinct and precise
function hasPermission(user: User, resource: Resource): boolean {
  return resource.requiredPermissions.some(p => user.permissions.includes(p));
}
```

### 3. No Error Swallowing

**Rationale**: Swallowed errors hide bugs, make debugging impossible, and erode trust in the system. Errors contain critical information about system state and failure modes.

**In Practice**:
- Every error must be either handled meaningfully or propagated to a handler that can
- Empty catch blocks are forbidden
- Log errors with full context before handling or re-throwing
- If you must catch and ignore, document why with an explicit comment
- Use type systems to make error states explicit (Result types, discriminated unions)

**Example**:
```typescript
// ❌ Error swallowing
try {
  await migrateData(source, target);
} catch (e) {
  // ignore - will handle later
}

// ❌ Still bad - logging without action
try {
  await migrateData(source, target);
} catch (e) {
  console.log('Error:', e);
}

// ✅ Proper error handling
try {
  await migrateData(source, target);
} catch (error) {
  logger.error('Data migration failed', {
    source: source.id,
    target: target.id,
    error,
    context: { phase: 'building', attempt: retryCount }
  });
  
  // Take meaningful action
  await rollbackMigration(source, target);
  throw new MigrationError('Failed to migrate data', { cause: error });
}

// ✅ Or return explicit Result type
async function migrateData(source, target): Promise<Result<Migration, MigrationError>> {
  try {
    const result = await performMigration(source, target);
    return Ok(result);
  } catch (error) {
    return Err(new MigrationError('Migration failed', { cause: error }));
  }
}
```

### 4. No Unnecessary Branching

**Rationale**: Excessive conditional logic exponentially increases complexity, creates hidden coupling, and makes code untestable. Every branch is a path that must be understood and tested.

**In Practice**:
- Use early returns to reduce nesting
- Prefer polymorphism over type checking
- Use lookup tables/maps instead of long if-else chains
- Question whether branches reflect true domain complexity or accidental complexity
- Default to fail-fast: validate inputs early and return/throw immediately

**Example**:
```typescript
// ❌ Unnecessary branching
function getApprovalStatus(item: Item): ApprovalStatus {
  if (item.type === 'critical') {
    if (item.reviewed) {
      if (item.approvedBy) {
        return 'approved';
      } else {
        return 'pending';
      }
    } else {
      return 'needs_review';
    }
  } else if (item.type === 'fyi') {
    return 'informational';
  } else {
    return 'low_risk';
  }
}

// ✅ Reduced branching with early returns
function getApprovalStatus(item: Item): ApprovalStatus {
  if (item.type === 'fyi') return 'informational';
  if (item.type === 'low_risk') return 'low_risk';
  
  if (!item.reviewed) return 'needs_review';
  return item.approvedBy ? 'approved' : 'pending';
}

// ✅✅ Even better - use data structure
const APPROVAL_RULES: Record<ItemType, (item: Item) => ApprovalStatus> = {
  critical: (item) => {
    if (!item.reviewed) return 'needs_review';
    return item.approvedBy ? 'approved' : 'pending';
  },
  fyi: () => 'informational',
  low_risk: () => 'low_risk'
};

function getApprovalStatus(item: Item): ApprovalStatus {
  return APPROVAL_RULES[item.type](item);
}
```

### 5. Organize Code in Appropriate Folders

**Rationale**: Well-organized code is discoverable, scalable, and signals intent. File structure should reflect domain concepts, not technical layers.

**In Practice**:
- Group by feature/domain, not by technical role (no giant `utils/` or `helpers/` folders)
- Co-locate related files - tests, styles, and components belong together
- File names should make the contents obvious
- Shared code should live at the lowest common parent, not at the root "just in case"
- Make dependencies explicit through folder boundaries

**Structure**:
```
src/
  features/
    migration-planning/          # Feature-based organization
      components/
        UserStoryList.tsx
        UserStoryList.test.tsx
        ArchitectureComparison.tsx
        ArchitectureComparison.test.tsx
      hooks/
        useMigrationPlan.ts
        useMigrationPlan.test.ts
      types.ts                    # Domain types for this feature
      api.ts                      # API interactions for this feature
      
    traffic-rollout/
      components/
        RolloutDashboard.tsx
        MetricsChart.tsx
      hooks/
        useRolloutMetrics.ts
      types.ts
      
  shared/                         # Only truly shared code
    components/
      Button/                     # Component with its tests and styles
        Button.tsx
        Button.test.tsx
        Button.module.css
    types/
      common.ts                   # Core domain types used everywhere
    
  core/                           # Infrastructure concerns
    api/
      client.ts
    auth/
      provider.tsx
```

**Anti-patterns**:
- ❌ `utils/helpers.ts` with 50 unrelated functions
- ❌ All tests in a separate `__tests__/` tree
- ❌ `components/` folder with 200+ components
- ❌ Importing from unrelated features (creates hidden coupling)

---

## II. Testing Standards

### 6. No Fluff Tests

**Rationale**: Tests that mock everything and only verify that mocks were called provide false confidence. They pass when the code breaks and fail when you refactor. They're worse than no tests because they create maintenance burden without catching bugs.

**In Practice**:
- If a test has more mock setup than actual assertions, it's probably a fluff test
- Mocks should be used sparingly - only for external boundaries (network, file system, time)
- Tests should verify behavior, not implementation details
- A good test should fail when the feature breaks and pass when it works

**Example**:
```typescript
// ❌ Fluff test - tests nothing real
describe('MigrationService', () => {
  it('should call repository to save migration', async () => {
    const mockRepo = {
      save: jest.fn().mockResolvedValue({ id: '123' })
    };
    const service = new MigrationService(mockRepo);
    
    await service.createMigration({ name: 'test' });
    
    expect(mockRepo.save).toHaveBeenCalledWith({ name: 'test' });
  });
});
// This test verifies the mock was called. So what? It tells us nothing about whether the feature works.

// ✅ Better - integration test with real behavior
describe('Migration Creation', () => {
  it('should persist migration and return with generated ID', async () => {
    const db = createTestDatabase();
    const service = new MigrationService(new MigrationRepository(db));
    
    const migration = await service.createMigration({
      name: 'AWS to Azure Migration',
      sourceRepo: 'github.com/acme/legacy'
    });
    
    expect(migration.id).toBeDefined();
    expect(migration.name).toBe('AWS to Azure Migration');
    
    // Verify persistence by reading back
    const retrieved = await service.getMigration(migration.id);
    expect(retrieved).toEqual(migration);
  });
});
```

### 7. Prefer Integration Tests

**Rationale**: Integration tests verify that components work together correctly. They catch the bugs that unit tests miss - interface mismatches, incorrect assumptions, integration issues.

**In Practice**:
- Test features end-to-end within a bounded context
- Use real implementations for everything except external boundaries
- Set up realistic test data that resembles production
- Test the happy path and the most important error paths
- Use in-memory databases or test containers, not mocks

**Example**:
```typescript
// ✅ Integration test for migration approval workflow
describe('Migration Approval Workflow', () => {
  let testDb: TestDatabase;
  let app: Application;
  
  beforeEach(async () => {
    testDb = await createTestDatabase();
    app = createApp(testDb);
  });
  
  it('should transition through approval gates correctly', async () => {
    // Create a migration
    const migration = await app.migrations.create({
      name: 'Test Migration',
      sourceRepo: 'github.com/acme/legacy'
    });
    
    // Platform generates plan (simulated)
    await app.migrations.generatePlan(migration.id);
    
    const plan = await app.migrations.getPlan(migration.id);
    expect(plan.status).toBe('pending_approval');
    expect(plan.items.filter(i => i.category === 'needs_approval')).toHaveLength(5);
    
    // FDE reviews items
    const itemsNeedingApproval = plan.items.filter(i => i.category === 'needs_approval');
    for (const item of itemsNeedingApproval) {
      await app.migrations.reviewItem(item.id, {
        status: 'approved',
        reviewedBy: 'fde@acme.com',
        comment: 'LGTM'
      });
    }
    
    // Verify plan can now proceed
    const updatedPlan = await app.migrations.getPlan(migration.id);
    expect(updatedPlan.status).toBe('approved');
    expect(updatedPlan.canProceed).toBe(true);
  });
});
```

### 8. Use Record/Replay Tests with Real Data

**Rationale**: Record/replay tests capture real production scenarios and verify that system behavior doesn't regress. They catch subtle bugs that synthesized test data misses.

**In Practice**:
- Record real API requests/responses, database queries, and user interactions
- Store recordings as fixtures alongside tests
- Replay recordings to verify system behavior is consistent
- Update recordings when intentional behavior changes
- Use real data shapes, not simplified test data

**Example**:
```typescript
// ✅ Record/replay test for log replay verification
describe('Log Replay Verification', () => {
  // Recordings stored in __fixtures__/production-logs/
  const productionLogs = loadFixture('production-logs/2025-11-16.json');
  
  it('should replay production traffic and match responses', async () => {
    const oldSystem = await startOldSystemSimulator();
    const newSystem = await startNewSystem();
    
    const replayResults = await replayLogs({
      logs: productionLogs,
      targets: [oldSystem, newSystem]
    });
    
    // Verify responses match for critical endpoints
    const criticalEndpoints = ['/api/auth', '/api/migrations', '/api/approve'];
    const discrepancies = replayResults
      .filter(r => criticalEndpoints.includes(r.endpoint))
      .filter(r => !responsesMatch(r.oldResponse, r.newResponse));
    
    expect(discrepancies).toEqual([]);
    
    // Verify performance is acceptable
    const newSystemLatency = replayResults.map(r => r.newResponse.latency);
    const p95Latency = percentile(newSystemLatency, 0.95);
    expect(p95Latency).toBeLessThan(200); // ms
  });
  
  it('should detect breaking changes in API contract', async () => {
    const recordedRequests = loadFixture('api-requests/migration-api.json');
    
    for (const request of recordedRequests) {
      const response = await fetch(request.url, {
        method: request.method,
        headers: request.headers,
        body: request.body
      });
      
      // Verify recorded response schema still matches
      expect(validateSchema(response.data, request.responseSchema)).toBe(true);
    }
  });
});
```

### 9. Test What Matters

**Rationale**: Not all code needs the same level of testing. Focus testing effort on business logic, data transformations, and user-facing behavior. Don't test framework code or trivial mappings.

**What to test**:
- ✅ Business logic and domain rules
- ✅ Data transformations and calculations
- ✅ Edge cases and error handling
- ✅ User workflows end-to-end
- ✅ Integration points with external systems

**What not to test**:
- ❌ Framework features (React knows how to render components)
- ❌ Trivial getters/setters
- ❌ Pure UI styling without behavior
- ❌ Third-party library functionality
- ❌ Type definitions (TypeScript checks these)

---

## III. User Experience Consistency

### 10. Consistent Mental Models

**Rationale**: Users should learn patterns once and apply them everywhere. Inconsistency forces users to relearn, increases cognitive load, and erodes trust.

**In Practice**:
- Use the same patterns for the same concepts throughout the UI
- Categorization system ("Needs Approval", "FYI", "Low-risk") should work identically in planning, building, and rollout phases
- Navigation patterns should be consistent - don't surprise users
- Color coding, iconography, and visual hierarchies should be predictable
- Error messages should follow the same tone and structure

**Example**:
```typescript
// ✅ Consistent categorization across all features
type ItemCategory = 'needs_approval' | 'fyi' | 'low_risk';

interface CategorizedItem {
  id: string;
  category: ItemCategory;
  auditReasoning: string;  // Always present to explain categorization
  canOverride: boolean;     // Consistent override capability
}

// All features use the same badge component with same colors
function CategoryBadge({ category }: { category: ItemCategory }) {
  const config = {
    needs_approval: { color: 'red', icon: AlertIcon, label: 'Needs Approval' },
    fyi: { color: 'blue', icon: InfoIcon, label: 'FYI' },
    low_risk: { color: 'green', icon: CheckIcon, label: 'Low Risk' }
  };
  
  const { color, icon: Icon, label } = config[category];
  return <Badge color={color} icon={Icon}>{label}</Badge>;
}
```

### 11. Surface Intent, Hide Complexity

**Rationale**: Users care about what they want to accomplish, not how the system does it. Show outcomes and actions, hide implementation details.

**In Practice**:
- Buttons and actions should describe user intent ("Approve Plan", not "Submit Form")
- Status messages should be outcome-focused ("Ready for Deployment", not "State: PENDING_DEPLOY")
- Progressive disclosure - show essential information first, details on demand
- Audit reasoning should be expandable, not cluttering the main view
- Technical details go in tooltips or expandable sections

**Example**:
```typescript
// ❌ Implementation-focused UI
<Button onClick={handleSubmit}>Submit Review Data</Button>
<Status>STATE: PENDING_FDE_INPUT</Status>

// ✅ Intent-focused UI  
<Button onClick={approveItem}>Approve This Item</Button>
<Status>Waiting for Your Review</Status>

// ✅ Progressive disclosure
<UserStoryCard story={story}>
  <CategoryBadge category={story.category} />
  <Title>{story.title}</Title>
  <Description>{story.summary}</Description>
  
  {/* Details hidden until clicked */}
  <ExpandableSection title="Why does this need approval?">
    <AuditReasoning>{story.auditReasoning}</AuditReasoning>
  </ExpandableSection>
</UserStoryCard>
```

### 12. Make State Visible

**Rationale**: Users need to know what's happening at all times. Invisible state changes cause confusion and anxiety. Every action should have visible feedback.

**In Practice**:
- Show loading states for all async operations
- Provide progress indicators for long-running platform operations
- Confirm all critical actions ("Plan Approved", "Rollback Complete")
- Make current phase/location obvious at all times
- Show who is doing what (when multiple team members are active)

**Example**:
```typescript
// ✅ Visible state throughout
function MigrationPlanView() {
  const { plan, isLoading, approving } = useMigrationPlan();
  
  if (isLoading) {
    return <LoadingState message="Loading migration plan..." />;
  }
  
  return (
    <div>
      {/* Current phase always visible */}
      <PhaseIndicator current="planning" />
      
      {/* Platform operation progress */}
      {plan.generatingTasks && (
        <ProgressBanner
          message="Platform is generating migration tasks..."
          progress={plan.generationProgress}
        />
      )}
      
      {/* Action feedback */}
      <Button 
        onClick={handleApprove}
        loading={approving}
        loadingText="Approving plan..."
      >
        Approve Plan
      </Button>
      
      {/* Confirmation after action */}
      {plan.approved && (
        <ConfirmationMessage>
          Plan approved by {plan.approvedBy} at {plan.approvedAt}
        </ConfirmationMessage>
      )}
    </div>
  );
}
```

### 13. Optimize for the Primary Flow

**Rationale**: Most users follow the happy path most of the time. Optimize the UI for speed and clarity on the primary workflow, not for edge cases.

**In Practice**:
- Put primary actions in prominent positions
- Minimize clicks for common operations
- Default to the most likely choice
- Make the critical path obvious visually
- Secondary and destructive actions should be less prominent but still accessible

**Example**:
```typescript
// ✅ Optimized for primary flow (approval)
function ReviewItem({ item }: { item: Item }) {
  return (
    <Card>
      <ItemSummary item={item} />
      
      {/* Primary action - prominent */}
      <PrimaryButton onClick={handleApprove}>
        Approve
      </PrimaryButton>
      
      {/* Secondary actions - accessible but less prominent */}
      <SecondaryButton onClick={handleRequestRevision}>
        Request Changes
      </SecondaryButton>
      
      {/* Destructive action - least prominent */}
      <TextButton onClick={handleReject}>
        Reject
      </TextButton>
      
      {/* Details available but not blocking primary action */}
      <ExpandableSection title="Audit Details">
        <AuditReasoning>{item.auditReasoning}</AuditReasoning>
      </ExpandableSection>
    </Card>
  );
}
```

### 14. Error Messages Are User-Facing

**Rationale**: Users don't care about stack traces or technical errors. Error messages should help users understand what went wrong and what to do next.

**In Practice**:
- Explain what happened in plain language
- Provide actionable next steps
- Show technical details in expandable section for debugging
- Categorize errors by severity (Critical, Warning, Info)
- Offer recovery actions when possible ("Retry", "Rollback")

**Example**:
```typescript
// ❌ Technical error message
<ErrorMessage>
  Error: ECONNREFUSED 127.0.0.1:5432
  at Connection.connect
  at PostgresAdapter.query
</ErrorMessage>

// ✅ User-facing error with actionable guidance
<ErrorMessage severity="critical">
  <Title>Unable to Load Migration Data</Title>
  <Description>
    We couldn't connect to the database to load your migration plan.
    This might be a temporary network issue.
  </Description>
  
  <Actions>
    <Button onClick={handleRetry}>Try Again</Button>
    <Button onClick={handleViewCached}>View Cached Version</Button>
  </Actions>
  
  {/* Technical details hidden but available */}
  <ExpandableSection title="Technical Details">
    <Code>
      Error: ECONNREFUSED 127.0.0.1:5432
      at Connection.connect
      at PostgresAdapter.query
    </Code>
  </ExpandableSection>
</ErrorMessage>
```

---

## IV. Enforcement

These principles are not suggestions - they are requirements. Every code review should verify adherence to these principles.

### Code Review Checklist

Before approving any PR, verify:

- [ ] No unnecessary code was added - could this be simpler?
- [ ] No errors are swallowed without proper handling and logging
- [ ] No deep nesting or unnecessary branching
- [ ] Code is organized in appropriate feature folders
- [ ] Tests verify real behavior, not mock interactions
- [ ] Integration tests cover the critical paths
- [ ] UX patterns are consistent with existing features
- [ ] Error messages are user-facing and actionable
- [ ] All async operations show loading/progress states
- [ ] Primary user flows are optimized for speed

### When to Deviate

These principles should guide 95% of decisions. The remaining 5%:

- Document why the principle doesn't apply in this case
- Discuss with the team before merging
- Add a TODO to revisit if it's a temporary exception
- Never deviate to save time - only when the principle genuinely doesn't fit

---

## V. Living Document

This constitution evolves as we learn. Propose changes via PR with:

1. The principle you want to change and why
2. Examples showing the current principle causing problems
3. The improved principle with updated examples
4. Team discussion and consensus

Last Updated: November 16, 2025
