## ADDED Requirements

### Requirement: A run's registered value is removed even when its events split it
The Hub SHALL remove a value registered for a run from that run's recorded model text when the value runs across two or more of the run's `text` and `thinking` events, as well as when it lies inside one.

The run's `text` and `thinking` events are joined in the order they are recorded, and other events
between them, such as tool calls and their results, errors, and status cards, do not break the join, and neither does
whitespace at the end of one event or the start of the next. Where a registered value
crosses an event boundary, the part of it inside each event recorded after the value began SHALL be
replaced with `<redacted>`, in the stored row and in its broadcast alike. An event that ends with the
first characters of a registered value SHALL have them replaced with `<redacted>` when it is
recorded, without waiting for the next event, once they number at least half the value's length
(rounded down) or eight, whichever is fewer. A shorter dangling start MAY be recorded as written.
A registered value that itself contains whitespace MAY be recorded unredacted where an event
boundary falls on that whitespace. Whitespace at the start or end of a registered value is not
part of it: the value SHALL be removed both as registered and without that whitespace.

No event SHALL be delayed, held back or reordered to achieve this, and an event of a run with no
registered value SHALL be recorded exactly as it was emitted. A recording retried after a locked
database SHALL produce the same row as one that succeeded first time.

#### Scenario: A value split between a thought and the reply
- **WHEN** a run with the registered value `plainproxykey123` records a thinking event ending in `plainproxy` and then a text event beginning with `key123`, in the order its runner emits them
- **THEN** the thinking row ends in `<redacted>` and the text row begins with `<redacted>`
- **AND** no stored row, no broadcast, and no two adjacent rows read together contain `plainproxykey123`

#### Scenario: A value split around a tool call
- **WHEN** a run with the registered value `plainproxykey123` records a text event ending in `plainproxy`, then a tool call, then a text event beginning with `key123`
- **THEN** both text rows carry `<redacted>` where their part of the value was
- **AND** the tool call is recorded between them, in its original position, unchanged

#### Scenario: A value split around an error card
- **WHEN** a run with the registered value `plainproxykey123` records a text event ending in `plainpro`, then an error event its runner reported between the two, then a text event beginning with `xykey123`
- **THEN** both text rows carry `<redacted>` where their part of the value was
- **AND** the error row is recorded between them, unchanged

#### Scenario: A value split where one event ends in whitespace
- **WHEN** a run with the registered value `plainproxykey123` records a thinking event ending in `plainproxy` followed by a blank line, and then a text event beginning with `key123`
- **THEN** the thinking row carries `<redacted>` in place of `plainproxy` and the text row begins with `<redacted>`

#### Scenario: A short dangling start
- **WHEN** a run with the registered value `plainproxykey123` records a text event ending in `plain` and then a thinking event beginning with `proxykey123`
- **THEN** the text row still ends in `plain`
- **AND** the thinking row begins with `<redacted>` and does not contain `proxykey123`

#### Scenario: The start of a value at the end of a run
- **WHEN** a run with the registered value `plainproxykey123` records, as its last text, an event ending in `plainproxyk`
- **THEN** that row ends in `<redacted>` and does not contain `plainproxyk`

#### Scenario: A value split across three events
- **WHEN** a run with the registered value `plainproxykey123` records events whose texts are `x plain`, `proxy` and `key123 y`, in that order
- **THEN** the rows read `x plain`, `<redacted>` and `<redacted> y`

#### Scenario: Prose that only resembles the start of a value
- **WHEN** a run with the registered value `plainproxykey123` records a thinking event ending in `Let me explai` and then a text event `n this.`
- **THEN** both rows are recorded exactly as emitted

#### Scenario: A value split shorter than the dangling-start threshold
- **WHEN** a run with the registered value `plainproxykey123` records a text event ending in `plainpr`, then a tool call, then a text event beginning with `oxykey123`
- **THEN** the first text row still ends in `plainpr` and the second text row begins with `<redacted>`
- **AND** the two text rows read together do not contain `plainproxykey123`

#### Scenario: A value registered with surrounding whitespace
- **WHEN** a run registers the value `plainproxykey123` followed by a newline, and records a text event `use plainproxykey123 now`
- **THEN** the row reads `use <redacted> now`

#### Scenario: A run with nothing registered
- **WHEN** a run that registered no value records text and thinking events
- **THEN** every row's content and payload are exactly as emitted

#### Scenario: A retried write does not change what is stored
- **WHEN** the write of a split value's second event meets a locked database once and is retried
- **THEN** the stored row is the same as when the write succeeds first time
