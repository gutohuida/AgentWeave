## ADDED Requirements

### Requirement: The operator can browse for a project directory

The project dialog SHALL let the operator locate a directory by browsing, in addition to typing or
pasting a path. Browsing SHALL be served by the Hub process, because a browser does not disclose an
absolute filesystem path to a web page.

Browsing SHALL list directories only. It MUST NOT return file names or file contents.

The operator SHALL be able to move into a listed directory and back toward its parent, and SHALL be
able to choose the directory currently being viewed.

#### Scenario: A directory is chosen by browsing

- **WHEN** the operator browses to a directory and chooses it
- **THEN** that directory's absolute path becomes the dialog's path value

#### Scenario: Only directories are listed

- **WHEN** a directory containing both files and subdirectories is listed
- **THEN** only its subdirectories are returned

#### Scenario: Typing a path remains available

- **WHEN** the operator knows the path already
- **THEN** it can be typed or pasted without browsing

#### Scenario: An unreadable directory does not end browsing

- **WHEN** a directory cannot be read
- **THEN** the operator is told why
- **AND** browsing continues from where it was

### Requirement: Directory listing is authenticated and bounded

The directory-listing endpoint SHALL require the same authentication as every other Hub endpoint.

The endpoint SHALL NOT follow a symbolic link out of the directory being listed.

Where a workspace root is configured, listings SHALL remain within it and a request outside it SHALL
be refused with a stated reason. Where no workspace root is configured, any directory the Hub
process can read MAY be listed.

#### Scenario: An unauthenticated listing is refused

- **WHEN** a directory listing is requested without valid authentication
- **THEN** the request is refused and no directory contents are returned

#### Scenario: A symlink does not escape the listing

- **WHEN** a listed directory contains a symbolic link pointing outside it
- **THEN** the listing does not traverse that link

#### Scenario: A configured workspace root bounds browsing

- **WHEN** a workspace root is configured and a directory outside it is requested
- **THEN** the request is refused with a stated reason
