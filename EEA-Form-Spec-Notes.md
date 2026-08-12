# EEA2 / EEA4 Form Specification Notes

**Source:** `EEA2 Form.docx` and `EEA4 Form.docx` in this folder (amended EEA forms, 2025–2030 sector-target period). Extracted and analysed 2026-08-12. These notes drive the `ee_reporting` module design; the form layouts themselves are versioned configuration (gap C3).

## Submission facts

- EEA2 (s21 report) + EEA4 (s27 income differential statement) are submitted **together** to the Department of Employment and Labour: online window **1 September – 15 January**; hand-delivered only 1 Sep – first working day of October. No fax/email/registered mail.
- **Sentech is an organ of state / State-Owned Enterprise → designated employer regardless of headcount** (confirmed A1). Business type on the form: "State Owned Enterprise".
- Sign-off: **Accounting Officer** (PFMA employer) — the approval chain for generated reports must end at CEO/Accounting Officer, not just the EE manager.
- No blank cells, "N/A" or dashes allowed — zeros must be captured as `0`. The validation engine must enforce complete matrices.

## Reporting dimensions (both forms)

- **Occupational levels (6, per EEA9):** Top management · Senior management · Professionally qualified & experienced specialists and mid-management · Skilled technical, academically qualified & junior management · Semi-skilled & discretionary decision making · Unskilled & defined decision making. Plus rows for **Total permanent**, **Temporary employees**, **Grand total**.
- **Population groups:** African, Coloured, Indian, White — **citizens only**, split Male/Female. **Foreign Nationals** are separate Male/Female columns (not raced).
- **Temporary employee** = employed to work **less than 3 months** (over 12 months, per EEA4 wording).
- Designated groups definition references SA citizenship by birth/descent, or naturalisation before 27 Apr 1994 (or would-have-been). → data model needs citizenship/nationality, not just a race field.
- Most tables capture **value and %** rows per level.

## EEA2 section map → where the data comes from

| Section | Content | Source module |
|---|---|---|
| A | Employer identity: trade name, DTI reg name/number, PAYE/SARS, UIF ref, EE ref, National/Provincial EAP choice, Industry/Sector, SETA classification, Bargaining council, addresses, CEO/Accounting Officer + EE Senior Manager details, business type, organ-of-state flag, headcount, group/holding, report year, reporting period, EE Plan period | `ee_reporting` employer-config (mostly static, entered once) |
| B | Workforce profile matrix + current-year targets, per level; separate disabilities-only matrix + disability target % | `core_hr` (as-at snapshot) + `ee_plan` targets |
| B (cont.) | Achieved-targets Y/N + justifiable-reasons grid (7 fixed reason categories × levels) | `ee_reporting` questionnaire |
| C | Workforce movements: **recruitment**, **promotion**, **termination** matrices (totals per level/group — no reason breakdown on the form, but keep internal reason codes) | `employment_event` |
| D | Skills development: employees trained per level/group (Male A/C/I/W, Female A/C/I/W — no FN columns here) | `learning` training records |
| E | 5-year sector targets (%) for top 4 levels + employer numerical goals for semi/unskilled, by gender; disability 5-yr target; full annual-target matrix for next year | `ee_plan` |
| F | Consultation (3 stakeholder types Y/N); barriers & AA measures grid — **24 fixed categories** × barriers Y/N, measures Y/N, start/end dates | `ee_reporting` questionnaire |
| G | Monitoring frequency; annual objectives achieved Y/N + explanation | `ee_reporting` questionnaire |
| H | CEO/Accounting Officer declaration + signature | approval chain |

## EEA4 section map

| Section | Content | Source |
|---|---|---|
| C | Per level × group × gender (+FN M/F): **number of employees + total annual remuneration** | payroll import (see below) |
| D1 / D2 | **Highest-paid** employee's fixed/variable/total per level×group; **lowest-paid** (lowest level) equivalents; tie-break = higher (D1) / lower (D2) variable | payroll import |
| E | Top-5% and bottom-5% headcount, total, and range; **median remuneration**; vertical gap multiple (e.g. 15x); remuneration policy Y/N; measures in EE Plan Y/N; key differential reason (8 fixed options) | computed + questionnaire |

### Remuneration rules (EEA4)

- Remuneration = total cost to company: **fixed/guaranteed** (salary, housing, travel allowance, employer medical/pension contributions, guaranteed 13th cheque…) + **variable** (STI/LTI, commission, overtime, back pay, retention bonuses, taxable bursaries…). Excludes tools-of-trade allowances, tips/gifts, severance.
- **Annualised** for partial-year employees: `(earned / months worked) × 12`.
- Captured as whole Rands, **no separators or decimals** (R7 345 567.60 → `7345568`).
- EEA4 workforce counts **must exactly match** EEA2 Section B counts per level/group — a cross-form validation rule.

## Consequences for the build (feed into sprint scope)

1. **Payroll remuneration import is a hard dependency of EE reporting** (Sprints 13–14), not only of the comp module. EEA4 needs per-employee annualised fixed + variable remuneration for the reporting period. Practical path per ADR-006: an annual (or per-cycle) SAP payroll extract imported into a `remuneration_record` table. Raises priority of action A10.
2. `employee_version` needs **citizenship / foreign-national status** and the disability flag; race applies to citizens only in the matrices.
3. `employment_event` totals per level/group are exactly what Section C consumes — reason codes stay internal.
4. New entities: `ee_plan` (plan period, 5-yr sector targets, annual targets per level×group×gender, disability targets), `ee_questionnaire` (justifiable reasons, consultation, 24-category barriers/AA grid, monitoring answers, differential reasons), `remuneration_record`.
5. **Employer-config** record for Section A identity fields (DTI/PAYE/UIF/EE ref etc.) — entered once, reused every year.
6. Approval chain for reports: HR → EE Senior Manager → **CEO/Accounting Officer** (PFMA).
7. Validation engine rules confirmed: complete matrices (zeros not blanks), integer remuneration, EEA2↔EEA4 count consistency, annualisation, % row computation, temporary = <3 months.
