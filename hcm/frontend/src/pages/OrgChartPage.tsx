import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchAllPages } from '../api/client'
import { useApiQuery } from '../api/hooks'
import { useReferenceData } from '../api/ReferenceDataContext'
import type { Employee, EmployeeVersion } from '../api/types'

interface OrgNode {
  employeeId: number
  name: string
  employeeNumber: string
  jobTitle: string
  departmentName: string
  children: OrgNode[]
}

/**
 * Builds the reporting forest from the row-scoped employees/current-versions
 * pair. "Root" is deliberately broader than "manager is null": row-scoping
 * (e.g. a line_manager's view) can return a subtree whose top person's own
 * manager exists in the org but isn't present in *this* fetch — treating
 * only `manager === null` as root would make that whole subtree vanish. So
 * a node is a root if its manager is null OR its manager isn't one of the
 * employees we actually have a node for.
 *
 * A defensive reachability pass then covers the pathological case of a
 * manager cycle entirely disconnected from any natural root (A manages B
 * manages A, neither of whose managers is null or missing) — without it
 * such a pair would silently vanish from the tree instead of just being an
 * unusual pair of roots.
 */
function buildForest(employees: Employee[], versions: EmployeeVersion[], departmentName: (id: number) => string) {
  const versionByEmployee = new Map<number, EmployeeVersion>()
  versions.forEach((v) => versionByEmployee.set(v.employee, v))

  const nodeById = new Map<number, OrgNode>()
  const joined: { employee: Employee; version: EmployeeVersion }[] = []
  employees.forEach((employee) => {
    const version = versionByEmployee.get(employee.id)
    if (!version) return // no current version for this employee — nothing to place in the tree
    joined.push({ employee, version })
    nodeById.set(employee.id, {
      employeeId: employee.id,
      name: `${employee.first_name} ${employee.last_name}`,
      employeeNumber: employee.employee_number,
      jobTitle: version.job_title,
      departmentName: departmentName(version.department),
      children: [],
    })
  })

  const roots: OrgNode[] = []
  joined.forEach(({ employee, version }) => {
    const node = nodeById.get(employee.id)!
    const managerId = version.manager
    const managerNode = managerId !== null ? nodeById.get(managerId) : undefined
    if (managerNode) {
      managerNode.children.push(node)
    } else {
      roots.push(node)
    }
  })

  // Reachability pass: pick up any node whose manager chain never reaches
  // a natural root (i.e. a pure cycle among managers we do have).
  const reached = new Set<number>()
  const stack = [...roots]
  while (stack.length > 0) {
    const node = stack.pop()!
    if (reached.has(node.employeeId)) continue
    reached.add(node.employeeId)
    stack.push(...node.children)
  }
  nodeById.forEach((node) => {
    if (!reached.has(node.employeeId)) roots.push(node)
  })

  const byName = (a: OrgNode, b: OrgNode) => a.name.localeCompare(b.name)
  const sortTree = (node: OrgNode) => {
    node.children.sort(byName)
    node.children.forEach(sortTree)
  }
  roots.sort(byName)
  roots.forEach(sortTree)

  return { roots, totalShown: joined.length }
}

/** Max depth of the forest (roots = depth 0). Guards against a node
 * appearing in its own ancestor chain (a manager cycle) so a pathological
 * data shape can't recurse forever. */
function maxDepth(roots: OrgNode[]): number {
  let deepest = 0
  const walk = (node: OrgNode, depth: number, ancestors: Set<number>) => {
    deepest = Math.max(deepest, depth)
    if (ancestors.has(node.employeeId)) return
    const nextAncestors = new Set(ancestors)
    nextAncestors.add(node.employeeId)
    node.children.forEach((child) => walk(child, depth + 1, nextAncestors))
  }
  roots.forEach((root) => walk(root, 0, new Set()))
  return deepest
}

function matchesQuery(node: OrgNode, query: string): boolean {
  const haystack = `${node.name} ${node.employeeNumber} ${node.jobTitle} ${node.departmentName}`.toLowerCase()
  return haystack.includes(query)
}

/** Ids of nodes that should be visible while searching: every match, plus
 * every ancestor of a match (so a hit inside a collapsed branch is actually
 * reachable). Returns null when there's no active query (meaning: normal,
 * unfiltered tree). */
function computeSearchVisibility(roots: OrgNode[], query: string): { visible: Set<number>; matches: Set<number> } | null {
  const trimmed = query.trim().toLowerCase()
  if (!trimmed) return null
  const visible = new Set<number>()
  const matches = new Set<number>()

  // Returns true if this node or any descendant matched, in which case it
  // (and its ancestors, via the caller's recursion) must stay visible.
  const walk = (node: OrgNode, ancestors: number[]): boolean => {
    const isMatch = matchesQuery(node, trimmed)
    if (isMatch) matches.add(node.employeeId)
    let anyDescendantMatch = false
    node.children.forEach((child) => {
      if (walk(child, [...ancestors, node.employeeId])) anyDescendantMatch = true
    })
    if (isMatch || anyDescendantMatch) {
      visible.add(node.employeeId)
      ancestors.forEach((id) => visible.add(id))
      return true
    }
    return false
  }
  roots.forEach((root) => walk(root, []))
  return { visible, matches }
}

export function OrgChartPage() {
  const { departments, loading: refLoading } = useReferenceData()
  const [search, setSearch] = useState('')
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set())

  const departmentName = (id: number) => departments.get(id)?.name ?? `#${id}`

  const { data, error } = useApiQuery(
    () =>
      Promise.all([
        fetchAllPages<Employee>('/employees/'),
        fetchAllPages<EmployeeVersion>('/employee-versions/?current=true'),
      ]).then(([employees, versions]) => ({ employees, versions })),
    [],
    { errorMessage: 'Failed to load the org chart.' },
  )

  const forest = useMemo(() => {
    if (!data) return null
    return buildForest(data.employees, data.versions, departmentName)
    // departments map identity changes each ReferenceDataContext load; that's fine, this is cheap to recompute.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, departments])

  const depth = useMemo(() => (forest ? maxDepth(forest.roots) : 0), [forest])
  const searchState = useMemo(() => (forest ? computeSearchVisibility(forest.roots, search) : null), [forest, search])

  // Default: roots expanded, everything deeper collapsed — but seeded once
  // into real state (rather than hard-coding "depth 0 is always expanded"
  // in the render), so a root's own toggle button actually works instead
  // of being permanently forced open.
  const initialized = useRef(false)
  useEffect(() => {
    if (forest && !initialized.current) {
      initialized.current = true
      setExpandedIds(new Set(forest.roots.map((r) => r.employeeId)))
    }
  }, [forest])

  function toggle(employeeId: number) {
    setExpandedIds((current) => {
      const next = new Set(current)
      if (next.has(employeeId)) next.delete(employeeId)
      else next.add(employeeId)
      return next
    })
  }

  const loading = data === null || refLoading

  return (
    <div className="page">
      <div className="page-header">
        <h1>Org Chart</h1>
        <input
          className="search-input"
          placeholder="Search by name, title, or department…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {error && <p className="form-error">{error}</p>}

      {loading ? (
        <p className="empty-state">Loading…</p>
      ) : forest && forest.totalShown === 0 ? (
        <p className="empty-state">No employees with a current record are visible to you.</p>
      ) : forest ? (
        <>
          <p className="hint-text">
            {forest.totalShown} {forest.totalShown === 1 ? 'person' : 'people'} shown · {forest.roots.length}{' '}
            root{forest.roots.length === 1 ? '' : 's'} · max depth {depth}
          </p>

          {searchState && searchState.matches.size === 0 ? (
            <p className="empty-state">No matches for &ldquo;{search.trim()}&rdquo;.</p>
          ) : (
            <ul className="org-chart-tree">
              {forest.roots
                .filter((root) => !searchState || searchState.visible.has(root.employeeId))
                .map((root) => (
                  <OrgNodeItem
                    key={root.employeeId}
                    node={root}
                    depth={0}
                    expandedIds={expandedIds}
                    onToggle={toggle}
                    searchState={searchState}
                  />
                ))}
            </ul>
          )}
        </>
      ) : null}
    </div>
  )
}

function OrgNodeItem({
  node, depth, expandedIds, onToggle, searchState,
}: {
  node: OrgNode
  depth: number
  expandedIds: Set<number>
  onToggle: (employeeId: number) => void
  searchState: { visible: Set<number>; matches: Set<number> } | null
}) {
  const hasChildren = node.children.length > 0
  const visibleChildren = searchState
    ? node.children.filter((child) => searchState.visible.has(child.employeeId))
    : node.children
  // While searching, every visible branch is forced open so the match is
  // actually on screen; otherwise fall back to the user's manual expand
  // state (seeded with roots expanded, deeper levels collapsed — see the
  // page-level effect that initializes expandedIds from the roots).
  const expanded = searchState ? visibleChildren.length > 0 : expandedIds.has(node.employeeId)
  const isMatch = searchState?.matches.has(node.employeeId) ?? false

  return (
    <li className="org-node">
      <div className={`org-node-card${isMatch ? ' org-node-match' : ''}`}>
        {hasChildren ? (
          <button
            type="button"
            className="org-node-toggle"
            aria-expanded={expanded}
            aria-label={`${expanded ? 'Collapse' : 'Expand'} ${node.name}'s direct reports`}
            onClick={() => onToggle(node.employeeId)}
            disabled={!!searchState}
          >
            {expanded ? '−' : '+'}
          </button>
        ) : (
          <span className="org-node-toggle-spacer" aria-hidden="true" />
        )}
        <div className="org-node-info">
          <div className="org-node-name">
            {node.name} <span className="hint-text">#{node.employeeNumber}</span>
          </div>
          <div className="hint-text">
            {node.jobTitle} · {node.departmentName}
          </div>
          <div className="hint-text">
            {node.children.length} direct report{node.children.length === 1 ? '' : 's'}
          </div>
        </div>
      </div>
      {hasChildren && expanded && (
        <ul className="org-node-children">
          {visibleChildren.map((child) => (
            <OrgNodeItem
              key={child.employeeId}
              node={child}
              depth={depth + 1}
              expandedIds={expandedIds}
              onToggle={onToggle}
              searchState={searchState}
            />
          ))}
        </ul>
      )}
    </li>
  )
}
