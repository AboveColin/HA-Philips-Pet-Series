# Copilot instructions

Read by Copilot code review, which runs automatically on every pull request to
`main`. Also a fair summary of what a human reviewer here looks for.

This is a Home Assistant custom integration for Philips Pet Series pet feeders,
talking to Philips' cloud and to the device's Tuya datapoints. It ships Lovelace
cards inside the integration.

Review against what this project actually cares about, in this order.

## Correctness against a real device

The interesting bugs here are not type errors, they are wrong assumptions about
hardware and about Home Assistant.

- **Unique IDs are load-bearing.** Changing an entity's `unique_id` silently
  orphans a user's history and renames their entity. A change to one needs a
  migration in `_async_migrate_unique_ids`.
- **Datapoint numbers are not interchangeable.** DP 101 and DP 201 both dispense
  food, on different models. Flag any code that hardcodes one where the model is
  not already known.
- **Anything that dispenses food is a physical action.** Flag paths that could
  fire it without a deliberate user action, or fire it more than once per action.
- **Cloud data is often missing rather than wrong.** Prefer code that treats an
  absent value as absent over code that substitutes a default that looks real.

## Honest failure

- A budget, cap or timeout that a user can hit must name the budget, the limit
  and the ask when it is hit. Silent truncation and silent fallbacks are bugs.
- Empty output is not a success state. A card that renders blank, a sensor that
  reports `unknown` where the API actually returned something, or a registration
  step that skips itself without logging are all worth a comment.
- If a code path cannot do what was asked, it should say so in the log, with the
  concrete thing the user would need to do.

## Comments earn their place

Comments here explain *why*, not *what*. A comment restating the code is noise;
one recording a measurement, an API quirk or a rejected alternative is the point.
Do not ask for docstrings on self-evident code, and do not ask for comments to be
removed just because they are long, if they carry a reason.

## Frontend (`frontend/philips-pet-series-cards.js`)

- No build step by design. It borrows Lit from the page and must stay loadable as
  a plain ES module. Flag anything needing bundling or a package manager.
- Cards must not guess entity IDs. They resolve entities through the
  `philips_pet_series/devices` websocket command, because users rename entities.
- Cards must survive a device that lacks an entity: a feeder with no camera, no
  filter, no MCU. Flag unguarded access to an optional role.
- Colours come from the `--pps-*` custom properties or the user's theme. Flag
  hardcoded colours that will break one of light or dark mode.
- Anything animated must be gated on both the `animations` option and
  `prefers-reduced-motion`.

## Not worth a comment

- Formatting, import order, and line length. There is no formatter in CI.
- British vs American spelling. Both appear; it is not worth churn.
- Suggestions to add a test framework, type annotations or a linter wholesale.
  Propose those as an issue, not as a review comment on unrelated work.
- Praise. A summary of what changed is useful; a paragraph on how good it is is
  not.

## Severity

Reserve HIGH and CRITICAL for: something that can dispense food unintentionally,
something that loses or orphans user data, a credential or token leak, or a
change that breaks an existing user's entities or dashboards.
