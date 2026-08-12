# ADR-006: Pay-data authority — payroll/SAP masters actuals

**Status:** Proposed (needs payroll/SAP team agreement)

## Context
A `sap-finance-platform` exists in the Sentech landscape. Dual-mastering salary data between HCM and payroll guarantees drift.

## Decision
- Payroll/SAP remains **master for actual pay**.
- HCM masters **pay bands** and **compensation proposals/approvals**.
- Approved comp changes export to payroll as a batch interface per pay cycle; actuals sync back read-only.

## Consequences
- Interface contract to be drafted with the SAP team (Sprint 0 action A10); build in proposed Sprint 12b.
- Comp module dashboards show "band vs. actual" using synced actuals, clearly labelled with sync date.
