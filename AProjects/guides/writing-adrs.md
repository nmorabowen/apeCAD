# Writing ADRs

- Next number = last index row + 1, zero-padded to four digits.
- Filename: `NNNN-kebab-title.md`.
- Add a row to [`../adrs/README.md`](../adrs/README.md) in the same change.
- One decision per ADR. If you need two, write two.
- Status starts as `Proposed` unless the owner accepted it in the same
  session (founding ADRs 0001–0007 were accepted at repo creation).
- Do not edit the Decision section of an accepted ADR. Write a successor
  that says what it amends or supersedes.
