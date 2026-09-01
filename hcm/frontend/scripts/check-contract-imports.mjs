#!/usr/bin/env node
// Guards against a migrated page silently regressing back to a handwritten
// transport type after api/types.ts has already dropped it in favour of the
// generated-contract facade (api/contracts.ts). See
// docs/frontend/generated-api-contracts.md for the migration pattern this
// enforces; add a new entry below whenever another module migrates.
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const srcDir = path.join(scriptDir, '..', 'src')

// module (relative to src/) -> handwritten type/const names it must no
// longer import from '../api/types', because api/contracts.ts (and
// api/contract-labels.ts for presentation labels) now supersede them.
const MIGRATED_MODULES = {
  'pages/ProbationPage.tsx': [
    'ProbationStatus',
    'ProbationRecommendation',
    'ProbationReview',
    'ProbationPeriod',
    'PROBATION_STATUS_LABELS',
    'PROBATION_RECOMMENDATION_LABELS',
  ],
  'pages/ExitInterviewsPage.tsx': ['ExitInterviewReason', 'ExitInterview', 'EXIT_INTERVIEW_REASON_LABELS'],
  'pages/CompProposalsPage.tsx': [
    'CompProposal',
    'CompProposalStatus',
    'CompProposalType',
    'COMP_PROPOSAL_STATUS_LABELS',
    'COMP_PROPOSAL_TYPE_LABELS',
  ],
  'pages/WorkforceIntegrityPage.tsx': ['LivenessCheck', 'LivenessOutcome', 'LIVENESS_OUTCOME_LABELS'],
}

const IMPORT_FROM_TYPES = /import\s+(?:type\s+)?\{([^}]+)\}\s+from\s+['"]\.\.\/api\/types['"]/g

let failed = false

for (const [relativePath, forbiddenNames] of Object.entries(MIGRATED_MODULES)) {
  const filePath = path.join(srcDir, relativePath)
  const source = readFileSync(filePath, 'utf8')
  for (const match of source.matchAll(IMPORT_FROM_TYPES)) {
    const importedNames = match[1].split(',').map((name) => name.trim().split(/\s+as\s+/)[0].trim())
    for (const name of importedNames) {
      if (forbiddenNames.includes(name)) {
        console.error(
          `${relativePath}: imports "${name}" from '../api/types', but this module was migrated to the ` +
            `generated-contract facade. Use api/contracts.ts (transport types) or api/contract-labels.ts ` +
            `(presentation labels) instead. See docs/frontend/generated-api-contracts.md.`,
        )
        failed = true
      }
    }
  }
}

if (failed) {
  process.exit(1)
}

console.log(`check-contract-imports: ${Object.keys(MIGRATED_MODULES).length} migrated module(s) clean.`)
