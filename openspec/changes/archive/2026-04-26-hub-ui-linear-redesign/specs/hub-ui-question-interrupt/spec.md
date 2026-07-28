## ADDED Requirements

### Requirement: QuestionInterruptCard component exists and accepts compact and full variants
A new component `hub/ui/src/components/questions/QuestionInterruptCard.tsx` SHALL be created. It SHALL accept a `questions: Question[]` prop and an optional `compact?: boolean` prop. When `compact={true}` it renders a narrower inline card (for use in the agent list panel). When `compact={false}` or omitted it renders a full-width card (for use on the Overview page).

#### Scenario: Component file exists at correct path
- **WHEN** a developer searches for QuestionInterruptCard
- **THEN** the file `hub/ui/src/components/questions/QuestionInterruptCard.tsx` exists and exports a named `QuestionInterruptCard` component

#### Scenario: Compact variant renders in a narrower layout
- **WHEN** `compact={true}` is passed
- **THEN** the card renders with reduced padding and without the secondary "dismiss" option shown in full variant

#### Scenario: Full variant renders with full detail and actions
- **WHEN** `compact` is false or omitted
- **THEN** the card renders with full padding, agent name, elapsed time, truncated question text, an "Answer" primary button, and a "Dismiss" secondary button

### Requirement: QuestionInterruptCard has amber visual treatment to signal urgency
The card SHALL use an amber color scheme: border `rgba(245,158,11,0.25)`, background `rgba(245,158,11,0.06)`, with amber-colored label text. It SHALL NOT use the same neutral styling as regular content cards.

#### Scenario: Amber border is applied
- **WHEN** the card renders
- **THEN** the card border color is `rgba(245,158,11,0.25)`

#### Scenario: Amber background tint is applied
- **WHEN** the card renders
- **THEN** the card background is `rgba(245,158,11,0.06)` (not transparent, not neutral surface)

### Requirement: Card shows the asking agent's name, elapsed time, and truncated question text
The card SHALL display:
- An eyebrow label (e.g., "⚠ claude is waiting") in amber
- The elapsed time since the question was asked (e.g., "4 min ago")
- The question text, truncated to 2 lines in compact mode, full in full mode

#### Scenario: Agent name appears in eyebrow label
- **WHEN** the card renders with a question from agent "claude"
- **THEN** the eyebrow label includes the text "claude"

#### Scenario: Elapsed time is displayed
- **WHEN** a question was asked 4 minutes ago
- **THEN** the card shows approximately "4 min ago" or equivalent relative time string

#### Scenario: Question text is truncated in compact mode
- **WHEN** `compact={true}` and question text exceeds 2 lines
- **THEN** the text is clipped with ellipsis after line 2

### Requirement: The "Answer" button navigates to the Questions page
Clicking "Answer" SHALL navigate the app to the Questions page (setting `page` to `'questions'` in App.tsx state).

#### Scenario: Answer button triggers navigation
- **WHEN** a user clicks "Answer" on the QuestionInterruptCard
- **THEN** the active page changes to "questions"

### Requirement: The "Dismiss" button hides the card until the next data poll
Clicking "Dismiss" SHALL hide the card for the current browser session. It SHALL reappear if the page is refreshed or if a new question arrives that was not previously dismissed. Dismissed question IDs SHALL be tracked in local component state (not persisted to localStorage).

#### Scenario: Dismiss hides the card
- **WHEN** a user clicks "Dismiss"
- **THEN** the QuestionInterruptCard is no longer rendered

#### Scenario: Card reappears after refresh
- **WHEN** the user dismissed the card and then refreshes the page
- **THEN** the card is visible again (dismiss state is not persisted)

#### Scenario: Card reappears when a new question arrives
- **WHEN** the user dismissed one question and a new question arrives via SSE/polling
- **THEN** the card reappears for the new question
