import { useEffect, useState } from 'react'
import { fetchAllPages } from '../api/client'
import { useAuth } from '../auth/useAuth'
import { RequirePayrollStepUp } from '../auth/RequirePayrollStepUp'
import type { EEQuestionnaire, EmployerConfig } from '../api/types'
import { EmployerConfigForm } from './ee-configuration/EmployerConfigSection'
import { PlanMeasuresSection } from './ee-configuration/PlanMeasuresSection'
import { PlanSnapshotsSection } from './ee-configuration/PlanSnapshotsSection'
import { QuestionnaireForm } from './ee-configuration/QuestionnaireSection'
import { RemunerationRecordsLoader } from './ee-configuration/RemunerationSection'

const CURRENT_YEAR = new Date().getFullYear()

/** Page shell only -- each statutory/configuration concern (employer
 * identity, the annual questionnaire, EE Plan measures, EE Plan progress
 * snapshots, remuneration records) is a self-contained section component
 * under ./ee-configuration/, matching EmployeeDetailPage's own
 * per-domain-panel split. */
export function EEConfigurationPage() {
  const { hasRole } = useAuth()
  // Raw remuneration is Restricted payroll data: hr_admin (import/read) and
  // auditor (read) only — ee_manager/accounting_officer work from the generated
  // report, never the per-employee rows (RemunerationRecordPermission).
  const canSeeRemuneration = hasRole('hr_admin') || hasRole('auditor')
  // Plan measures / snapshots are the EE manager's operational records
  // (design spec 2026-08-26 §5) — unlike the form data above, ee_manager
  // writes them too.
  const canWriteOperational = hasRole('hr_admin') || hasRole('ee_manager')
  const [config, setConfig] = useState<EmployerConfig | null>(null)
  const [questionnaire, setQuestionnaire] = useState<EEQuestionnaire | null>(null)
  const [error, setError] = useState<string | null>(null)

  function load() {
    setError(null)
    Promise.all([
      fetchAllPages<EmployerConfig>('/employer-config/'),
      fetchAllPages<EEQuestionnaire>(`/ee-questionnaires/?report_year=${CURRENT_YEAR}`),
    ])
      .then(([configs, questionnaires]) => {
        setConfig(configs[0] ?? null)
        setQuestionnaire(questionnaires[0] ?? null)
      })
      .catch(() => setError('Failed to load EE configuration.'))
  }

  useEffect(load, [])

  return (
    <div className="page">
      <div className="page-header">
        <h1>EE Reporting Configuration</h1>
      </div>
      <p className="hint-text">
        Section A (employer identity), the questionnaire sections, and remuneration data all feed into report
        generation on the Reports page. hr_admin can edit here; ee_manager/accounting_officer/auditor can view.
      </p>

      {error && <p className="form-error">{error}</p>}

      <section className="detail-card">
        <h2>Employer Configuration (Section A)</h2>
        {config === undefined ? <p className="empty-state">Loading…</p> : <EmployerConfigForm config={config} onSaved={load} />}
      </section>

      <section className="detail-card">
        <h2>EE Questionnaire — {CURRENT_YEAR}</h2>
        <QuestionnaireForm questionnaire={questionnaire} reportYear={CURRENT_YEAR} onSaved={load} />
      </section>

      <section className="detail-card">
        <h2>EE Plan measures</h2>
        <PlanMeasuresSection canWrite={canWriteOperational} />
      </section>

      <section className="detail-card">
        <h2>EE Plan progress snapshots</h2>
        <PlanSnapshotsSection canWrite={canWriteOperational} />
      </section>

      {canSeeRemuneration && (
        <section className="detail-card">
          <h2>Remuneration Records</h2>
          {/* Restricted-tier (Data-Dictionary.md) — gated separately from
              the rest of this page so a missing step-up grant doesn't break
              employer config/questionnaire loading above, which aren't
              payroll data. */}
          <RequirePayrollStepUp>
            <RemunerationRecordsLoader />
          </RequirePayrollStepUp>
        </section>
      )}
    </div>
  )
}
