## ADDED Requirements

### Requirement: An appearance the operator never chose follows the system's

Where the operator has never chosen light or dark, the application SHALL open in the appearance the operating system reports as preferred, and SHALL NOT default to a fixed appearance.

A fixed default makes an operator who never chose indistinguishable from one whose choice was lost,
and gives a first launch on a dark system a light application.

Once the operator chooses, their choice SHALL govern every later launch. Opening the application
SHALL NOT record a choice on the operator's behalf, so that an operator who never chose keeps
following the system.

#### Scenario: A first launch on a dark system opens dark

- **WHEN** the operator has never chosen an appearance and the system prefers dark
- **THEN** the application opens in dark mode

#### Scenario: A first launch on a light system opens light

- **WHEN** the operator has never chosen an appearance and the system prefers light
- **THEN** the application opens in light mode

#### Scenario: A choice outlasts the system's preference

- **WHEN** the operator has chosen light and the system prefers dark
- **THEN** the application opens in light mode

#### Scenario: Opening the application records no choice

- **WHEN** the operator has never chosen an appearance and opens the application
- **THEN** no appearance choice is recorded
