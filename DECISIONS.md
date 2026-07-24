# Design Decisions

This file records active product and data-model decisions for personal-tracker.
It is not a changelog. Items marked as proposed are not implemented yet.

## Accounting Facts And Future Intent

- A transaction is an actual, confirmed financial event.
- Amortization is metadata on an actual expense. It determines how a confirmed
  payment is attributed across future months; it never creates a future payment.
- Prepaid expenses can be created from the cross-period page or by adding
  amortization to an existing transaction. Both routes converge on one expense
  transaction plus one prepaid management record.
- A future plan must not be stored as a transaction. Planned expenses will be
  confirmed into transactions only when the payment actually happens.

## Subscription And Planned Expenses

Status: proposed.

- A subscription is a renewal rule, not proof that a payment happened.
- A planned expense may have a due date or remain undated as a long-term plan.
- Confirming a planned expense opens a form with the final amount, category and
  date; the default date is the current day. Confirmation creates a transaction.
- Subscriptions may manually create a planned renewal item. The application
  must not silently create transactions or planned items on page load.
- Subscription setup has two routes: manual rule creation, or marking a
  confirmed ledger transaction as the first payment of a subscription.

## Renewal Rules

Status: proposed.

Two renewal modes are intentionally distinct:

- `same_day`: renew after N calendar months while retaining an anchor day.
  If the anchor does not exist in the target month, use that month's final day
  without changing the anchor for later months.
- `fixed_days`: renew after N days from the confirmed payment date.

The subscription schema should store `renewal_mode`, `renewal_interval`,
`renewal_anchor_day` for same-day rules, and `next_renewal_date`.

## Budgeting

- Monthly budgets use two separate reference values: amortized cost and actual
  cash outflow.
- They are shown in the monthly analysis view, not as a separate budget page.
- Personal budgeting is monthly; there is no annual or category budget plan.

## Interface Principles

- Use constrained fluid layout: a 1280px maximum application content width,
  with narrower local regions for forms and wider regions for tables/charts.
- List pages use a list-and-inspector layout. Selecting a row reveals its
  editor beside the table rather than opening a full-width editor below it.
- A primary save action is visually distinct. Refunds and deletion are
  secondary operations because they create a linked record or remove one.
- Daily financial trends use line charts. A large single expense remains a
  visible peak without dominating the chart through bar area.
