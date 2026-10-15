## ADDED Requirements

### Requirement: A Copilot one-shot call's credits count in the project's credit totals

This requirement extends two requirements of `worker-spend-counts-against-the-budget`: "Every model
call the Hub makes for a project is recorded", and "Usage aggregates by agent and project".

A Copilot one-shot call is any recorded worker call run on a `copilot` runner, whatever its kind: a
checkpoint, a checkpoint probe, a manager job such as distillation, reports, or the spec-vault check,
or a conversation title once titles are recorded. Each such call's `ai_nano_aiu` and
`premium_requests` SHALL be summed:

- into the `workers` line for its kind, and
- into the project's `ai_nano_aiu` and `premium_requests` in `GET /projects/{project_id}/accounting`.

Each figure SHALL be stored and summed in its own unit, and SHALL NOT be converted to tokens or
dollars. A `workers` line or project total SHALL report `null` for a credit figure that none of its
calls reported, not zero.

A call that spawned, reported no tokens, and reported at least one credit figure SHALL be counted as
a credited call. It SHALL NOT be counted as a call that reported no usage.

The credits SHALL NOT count toward the token budget and SHALL NOT join the token total. A Copilot
one-shot call's tokens SHALL remain unknown: they SHALL NOT be estimated from its credits or from any
input-only figure in its output. A Copilot one-shot call therefore never moves the token budget.

The figures of an agent and of a conversation SHALL stay turns-only.

The project's worker credit figures SHALL be the sum of its `workers` lines' figures. The project's
`ai_nano_aiu` SHALL therefore equal the sum of its agents' `ai_nano_aiu` and its `workers` lines'
`ai_nano_aiu`, and likewise for `premium_requests`, so that no figure on the dashboard disagrees with
the figures it is the total of.

A conversation title generated on a Copilot runner SHALL record the credits parsed from that title
call's output on its own row.

#### Scenario: The project's credits equal its agents' plus its workers'

- **WHEN** a project has Copilot turns from two agents and Copilot worker calls of two kinds, each
  reporting credits
- **THEN** the project's `ai_nano_aiu` equals the agents' `ai_nano_aiu` plus the `workers` lines'
  `ai_nano_aiu`
- **AND** the same holds for `premium_requests`

#### Scenario: A Copilot conversation title records its credits

- **WHEN** a conversation title is generated on a Copilot runner, and the title call's output reports
  32 840 000 nano-AIU and 1 premium request
- **THEN** the `conversation_title` line reports 32 840 000 nano-AIU and 1 premium request
- **AND** counts that call as a credited call

#### Scenario: A checkpoint and its probe add their credits to the project's totals

- **WHEN** a project has Copilot turns totalling 154 000 145 000 nano-AIU and 19 premium requests,
  and a Copilot `checkpoint` call reporting 1 102 140 000 nano-AIU and 1 premium request, and a
  Copilot `checkpoint_probe` call reporting 822 390 000 nano-AIU and 1 premium request
- **THEN** the project's accounting reports 155 924 675 000 nano-AIU and 21 premium requests
- **AND** the `checkpoint` line and the `checkpoint_probe` line each report their own call's credits
- **AND** the agents' credit figures still total 154 000 145 000 nano-AIU and 19 premium requests

#### Scenario: A credited call is not reported as one with no usage

- **WHEN** a Copilot checkpoint call completes, reporting credits and no tokens
- **THEN** its `workers` line counts it as a credited call
- **AND** that line's count of calls that reported no usage does not include it

#### Scenario: A call that reported nothing is still unmeasured

- **WHEN** a Copilot checkpoint call spawns and times out having reported neither tokens nor credits
- **THEN** its `workers` line counts it as a call that reported no usage, and not as a credited call
- **AND** it adds nothing to that line's credit figures, which stay null unless another call of the
  same kind reported credits

#### Scenario: A manager job's Copilot call is counted the same way

- **WHEN** a distillation call runs on a Copilot runner and reports credits and no tokens
- **THEN** its kind's `workers` line counts it as a credited call and reports its credits
- **AND** the project's credit totals include them

#### Scenario: Worker credits stay off the token total and the budget

- **WHEN** a project with a token budget has Copilot checkpoint calls that reported credits
- **THEN** the project's token total and the budget's used tokens are what they would be without
  those calls
- **AND** no Copilot one-shot call is assigned an estimated token count

#### Scenario: A project with no Copilot calls is unchanged

- **WHEN** a project's turns and worker calls all ran on Claude or Codex
- **THEN** the project's `ai_nano_aiu` and `premium_requests` are null
- **AND** every `workers` line reports null credit figures and no credited calls

### Requirement: When credits are the only spend a project reports, the preferred display names them

`preferred_display` in `GET /projects/{project_id}/accounting` SHALL choose by which data exists,
not by which runner served the most turns. The order SHALL be:

1. the newest allowance reading
2. an API-equivalent cost, when any turn reported one
3. Copilot credits, when the project's credit totals include either figure
4. tokens
5. unavailable

The credits display SHALL have the kind `credits` and SHALL carry the runner `copilot` and the
project's `ai_nano_aiu` and `premium_requests`. The dashboard SHALL label it as Copilot AI credits,
and SHALL NOT label it as tokens.

A turn with no allowance reading SHALL NOT be taken as an allowance reading, whatever its stored
allowance value is.

#### Scenario: An all-Copilot project with no allowance reading shows credits

- **WHEN** every turn of a project ran on Copilot, none reported an allowance reading or a cost, and
  they reported credits
- **THEN** `preferred_display` has the kind `credits` and the project's credit figures
- **AND** the dashboard's preferred-display label names Copilot AI credits, not tokens

#### Scenario: Worker credits alone show credits

- **WHEN** a project's turns all ran on Codex and reported tokens, no allowance reading and no cost,
  and its checkpoint calls ran on a Copilot runner and reported credits that its credit totals include
- **THEN** `preferred_display` has the kind `credits` and the project's credit figures

#### Scenario: A refused Copilot turn's charge shows credits

- **WHEN** every turn of a project reported no tokens, no allowance reading and no cost, and a
  Copilot turn refused for quota reported credits
- **THEN** `preferred_display` has the kind `credits`, not `unavailable`

#### Scenario: An allowance reading still takes precedence

- **WHEN** a project reports Copilot credits and a turn carries an allowance reading
- **THEN** `preferred_display` is that allowance reading

#### Scenario: An API-equivalent cost still takes precedence

- **WHEN** a project has Copilot turns that reported credits and a Claude turn that reported a cost,
  and no allowance reading exists
- **THEN** `preferred_display` has the kind `api_equivalent`

#### Scenario: A project with no credits still shows tokens

- **WHEN** a project's turns reported tokens, no allowance reading, no cost, and no credits
- **THEN** `preferred_display` has the kind `tokens`

#### Scenario: A turn with no allowance reading is never taken for one

- **WHEN** every turn of a project was recorded without an allowance reading
- **THEN** `preferred_display` is not an allowance display
- **AND** no recent turn reports an allowance
