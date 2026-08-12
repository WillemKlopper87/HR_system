import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { fetchAllPages } from './client'
import type { Department, JobGrade, Location, OccupationalLevel } from './types'

interface ReferenceDataState {
  departments: Map<number, Department>
  occupationalLevels: Map<number, OccupationalLevel>
  jobGrades: Map<number, JobGrade>
  locations: Map<number, Location>
  departmentList: Department[]
  occupationalLevelList: OccupationalLevel[]
  jobGradeList: JobGrade[]
  locationList: Location[]
  loading: boolean
}

interface ReferenceDataValue extends ReferenceDataState {
  refresh: () => void
}

const empty: ReferenceDataState = {
  departments: new Map(),
  occupationalLevels: new Map(),
  jobGrades: new Map(),
  locations: new Map(),
  departmentList: [],
  occupationalLevelList: [],
  jobGradeList: [],
  locationList: [],
  loading: true,
}

const ReferenceDataContext = createContext<ReferenceDataValue | null>(null)

export function ReferenceDataProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ReferenceDataState>(empty)
  const [version, setVersion] = useState(0)

  useEffect(() => {
    let cancelled = false
    setState((prev) => ({ ...prev, loading: true }))
    Promise.all([
      fetchAllPages<Department>('/departments/'),
      fetchAllPages<OccupationalLevel>('/occupational-levels/'),
      fetchAllPages<JobGrade>('/job-grades/'),
      fetchAllPages<Location>('/locations/'),
    ]).then(([departments, occupationalLevels, jobGrades, locations]) => {
      if (cancelled) return
      setState({
        departments: new Map(departments.map((d) => [d.id, d])),
        occupationalLevels: new Map(occupationalLevels.map((l) => [l.id, l])),
        jobGrades: new Map(jobGrades.map((g) => [g.id, g])),
        locations: new Map(locations.map((l) => [l.id, l])),
        departmentList: departments,
        occupationalLevelList: occupationalLevels,
        jobGradeList: jobGrades,
        locationList: locations,
        loading: false,
      })
    })
    return () => {
      cancelled = true
    }
  }, [version])

  return (
    <ReferenceDataContext.Provider value={{ ...state, refresh: () => setVersion((v) => v + 1) }}>
      {children}
    </ReferenceDataContext.Provider>
  )
}

export function useReferenceData(): ReferenceDataValue {
  const ctx = useContext(ReferenceDataContext)
  if (!ctx) throw new Error('useReferenceData must be used within ReferenceDataProvider')
  return ctx
}
