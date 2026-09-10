## ADDED Requirements

### Requirement: One dismissal keystroke dismisses one thing
A dismissal keystroke SHALL be answered by exactly one control — the innermost one that owns it — and a surface that dismisses on that keystroke SHALL NOT do so when a control nearer the operator has already handled it.

A control that handles a dismissal keystroke SHALL mark the keystroke as handled, so that the
surfaces containing it can tell. A surface cannot know what is nested inside it, and a nested
control cannot know what contains it; the keystroke itself is the only thing both can see.

Nesting is the ordinary case, not an exotic one. A panel holds a menu; a panel holds an input that
cancels; a panel holds a browser that closes. In every one of those the operator pressing Escape is
dismissing the thing they are looking at, and the surface behind it is the context they expect to
come back to. A surface that leaves with the control being dismissed takes the operator's place with
it, and there is nothing on screen afterwards to say what happened.

The cost is worse than an extra click, and it is why this is stated once here rather than repaired
per screen. A nested control that owns the key **cannot be observed to work at all** while the
surface around it also acts: the code runs, does exactly what it was written to do, and is unmounted
by the same keystroke. That failure is invisible to anything except operating the product.

This requirement is about who answers, not about where a listener is bound or which mechanism marks
the keystroke. A surface may listen wherever it needs to.

#### Scenario: Dismissing a menu inside a panel leaves the panel open

- **WHEN** the operator opens a menu belonging to a control inside a panel that itself dismisses on
  Escape, and presses Escape
- **THEN** the menu closes
- **AND** the panel is still open

#### Scenario: Cancelling an input inside a panel leaves the panel open

- **WHEN** a panel that dismisses on Escape is showing a control that cancels itself on Escape, and
  the operator presses Escape while that control has focus
- **THEN** that control is cancelled
- **AND** the panel is still open, showing what it showed before the control appeared

#### Scenario: A panel opened over another panel dismisses only itself

- **WHEN** a secondary panel is open over the panel that opened it, and both dismiss on Escape, and
  the operator presses Escape
- **THEN** the secondary panel closes
- **AND** the panel that opened it is still open

#### Scenario: With nothing nearer, the panel still dismisses

- **WHEN** the operator presses Escape while a panel is open and nothing inside it has claimed the
  keystroke
- **THEN** the panel dismisses, exactly as it did before

### Requirement: An action that asks for something leaves the keyboard in what it asked with
A menu action whose effect is to present a control expecting the operator's input SHALL leave keyboard focus in that control once the menu has closed, and SHALL NOT return focus to the control that opened the menu.

A menu returning focus to its trigger is right for an action that leaves nothing on screen: it is
where the operator was, and it is where they can act next. It is wrong for an action whose whole
purpose is to ask a question, because the field holding the answer is then the one place the
keyboard is not.

**The failure is silent, which is what makes it worth a requirement rather than a fix.** The
operator types and nothing appears; the control they are actually typing into is a button, so their
keystrokes activate it; and the action they were completing sits waiting on input the product will
not accept from them. Nothing is written wrongly and no error is shown, so there is no moment at
which the product says anything is wrong.

This applies to the action, not to the menu. A menu that offers both kinds of action SHALL
distinguish them: an action that presents nothing keeps returning focus to the trigger, and only the
action that asks stands the restoration down.

#### Scenario: Choosing an action that asks a question puts the keyboard in the answer

- **WHEN** the operator chooses a menu action that presents a control expecting their input
- **THEN** keyboard focus is in that control once the menu has closed
- **AND** what they type next appears in it

#### Scenario: An action that asks nothing returns the keyboard where it was

- **WHEN** the operator chooses a menu action that presents no control expecting input
- **THEN** keyboard focus returns to the control that opened the menu

#### Scenario: Typing an answer does not operate the menu that asked for it

- **WHEN** the operator types an answer containing spaces into the control a menu action presented
- **THEN** the menu does not re-open
- **AND** the surface behind that control does not stop answering the pointer because a menu re-opened
  over it
