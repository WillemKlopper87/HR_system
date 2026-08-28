import { useContext } from 'react'
import { ReferenceDataContext, type ReferenceDataValue } from './reference-data-context'

export function useReferenceData(): ReferenceDataValue {
  const context = useContext(ReferenceDataContext)
  if (!context) throw new Error('useReferenceData must be used within ReferenceDataProvider')
  return context
}
