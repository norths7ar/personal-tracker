# Design Decisions

This file records active product and data-model decisions for personal-tracker.
It is not a changelog.

## Accounting Facts And Future Intent

- A transaction is an actual, confirmed financial event.
- Amortization is metadata on an actual expense. It determines how a confirmed
  payment is attributed across future months; it never creates a future payment.
- Prepaid expenses can be created from the cross-period page or by adding
  amortization to an existing transaction. Both routes converge on one expense
  transaction plus one prepaid management record.
- A future plan is not a transaction. Confirming a planned expense creates one
  actual transaction only when the payment happens.

## Expected And Prepaid Expenses

- The cross-period page has two user-facing concepts: expected expenses and
  prepaid amortization.
- Expected expenses may be one-time or recurring. One-time items may remain
  undated; recurring items require a next payment date.
- Confirming an expected expense creates one transaction. A one-time item then
  closes; a recurring item advances its next payment date.
- Prepaid amortization begins with an actual payment, so creating it immediately
  creates a transaction and adds amortization metadata.
- An existing expense may explicitly become the first payment of a recurring
  item from the ledger editor. The application never infers links from text or
  amount similarity.

## Renewal Rules

Two renewal modes are intentionally distinct:

- `same_day`: renew after N calendar months while retaining an anchor day.
  If the anchor does not exist in the target month, use that month's final day
  without changing the anchor for later months.
- `fixed_days`: renew after N days from the confirmed payment date.

The subscription schema stores `renewal_mode`, `renewal_interval`,
`renewal_anchor_day` for same-day rules, and `next_renewal_date`.

## Budgeting

- Monthly budgets use two separate reference values: amortized cost and actual
  cash outflow.
- They are shown in the monthly analysis view, not as a separate budget page.
- Personal budgeting is monthly; there is no annual or category budget plan.
- Monthly analysis shows active recurring payments as a separate fixed-cost
  reference. It excludes one-time plans and prepaid amortization.

## Interface Principles

- Use constrained fluid layout: a 1280px maximum application content width,
  with narrower local regions for forms and wider regions for tables/charts.
- Tables remain the primary surface for scanning records. The ledger uses a
  compact modal for occasional edits; the short pending-classification list
  expands its confirmation form below the table.
- Cross-period management uses parallel expected-expense and prepaid-
  amortization tabs. Creation, editing, confirmation and deletion use compact
  dialogs rather than persistent forms.
- A primary save action is visually distinct. Refunds and deletion are
  secondary operations because they create a linked record or remove one.
- Daily financial trends use line charts. A large single expense remains a
  visible peak without dominating the chart through bar area.
