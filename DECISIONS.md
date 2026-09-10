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

## Analysis

- Standalone reimbursements and unlinked refunds remain income. Only refunds explicitly linked to an expense reduce net expense, using the original expense category; they are not also counted as income.
- Current-period actual totals and charts end today, and daily averages use elapsed days including today. Past periods use their full length. Period-over-period change messages are not displayed.
- Category drilldowns use the same signed contributions as the summaries, including linked refunds and monthly amortization shares. Amortization is allocated in cents with remainder cents in the first months; it is monthly attribution, not daily proration.

## Budgeting

- Monthly budgets use two separate reference values: amortized cost and actual
  cash outflow.
- They are shown in the monthly analysis view, not as a separate budget page.
- Personal budgeting is monthly; there is no annual or category budget plan.
- Monthly analysis shows active recurring payments and prepaid amortization as
  a separate fixed-cost reference. It excludes one-time plans.

## Interface Principles

- Desktop is the primary interface. Pages share one application content container, consistent margins and alignment; local forms may constrain fields without changing the page width.
- Ledger and diet tables share selection and editing behavior: a row click selects one record, checkboxes enable multiple selection and current-page selection, and a double click or the edit action opens a centered dialog. Bulk editing changes only explicitly enabled fields; the ledger retains transaction-type restrictions, while diet bulk edits allow date, time, meal label and notes without replacing descriptions, foods or ingredients. Bulk deletion requires confirmation.
- The short pending-classification list expands its confirmation form below the table.
- Cross-period management uses parallel expected-expense and prepaid-
  amortization tabs. Creation, editing, confirmation and deletion use compact
  dialogs rather than persistent forms.
- A primary save action is visually distinct. Refunds and deletion are
  secondary operations because they create a linked record or remove one.
- Daily financial trends use line charts. A large single expense remains a
  visible peak without dominating the chart through bar area.
- The record page shows a compact reminder only when action is needed. Reminders
  never create transactions; linked subscription plans are deduplicated against
  the recurring payment shown for the same action.

## Meal Time And Labels

- Meal time is a factual field and is required for new diet records in `HH:MM`
  form. Existing records without a time remain valid until edited.
- Meal labels are optional metadata rather than required categories. Explicit
  labels such as breakfast, brunch or late-night snack are preserved.
- When no label is supplied, the application infers breakfast, lunch or dinner
  only inside conservative conventional time windows. Ambiguous times remain
  unlabeled.
- Diet analysis counts eating records, not inferred meals. Current-month averages use elapsed calendar days including today; historical months use the full month. Unrecorded days are gaps rather than evidence of no eating. Time charts run from early at the top to late at the bottom.
- Food frequency groups exact food names. Ingredient frequency is separate and counts each ingredient at most once per record, with ingredient-data coverage shown. Meal labels remain editable metadata but have no distribution chart.
- A meal description preserves the user's original wording. Each extracted food
  is a dish or standalone food, and may have separately stored major ingredients.
  Ingredients are editable facts used for later aggregation, not nutritional
  categories or inferred nutrient claims.
