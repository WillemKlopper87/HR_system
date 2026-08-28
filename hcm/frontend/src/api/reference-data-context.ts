import { createContext } from 'react'
import type { Department, JobGrade, Location, OccupationalLevel } from './types'

export interface ReferenceDataValue {
  departments: Map<number, Department>
  occupationalLevels: Map<number, OccupationalLevel>
  jobGrades: Map<number, JobGrade>
  locations: Map<number, Location>
  departmentList: Department[]
  occupationalLevelList: OccupationalLevel[]
  jobGradeList: JobGrade[]
  locationList: Location[]
  loading: boolean
  refresh: () => void
}

export const ReferenceDataContext = createContext<ReferenceDataValue | null>(null)
