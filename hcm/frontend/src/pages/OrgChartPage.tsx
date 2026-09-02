import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchAllPages } from '../api/client'
import { useApiQuery } from '../api/hooks'
import { useReferenceData } from '../api/useReferenceData'
import type { Department, OrgChartNodeSummary } from '../api/types'

interface OrgNode {
  employeeId: number
  name: string
  employeeNumber: string
  jobTitle: string
  departmentName: string
  children: OrgNode[]
  /** Set only when this node's link to its real manager had to be cut to
   * break a reporting-chain cycle — see buildForest's cycle scan. Carries
   * the cut-off manager's name so it can be surfaced on the card: a person
   * silently vanishing from the chart would be worse than a visible flag
   * that the underlying manager assignment needs correcting. */
  brokenLoopManagerName?: string
}

/**
 * Builds the reporting forest from the row-scoped, privacy-minimal topology
 * rows. "Root" is deliberately broader than "manager is null": row-scoping
 * (e.g. a line_manager's view) can return a subtree whose top person's own
 * manager exists in the org but isn't present in *this* fetch — treating
 * only `manager === null` as root would make that whole subtree vanish. So
 * a node is a root if its manager is null OR its manager isn't one of the
 * employees we actually have a node for.
 *
 * The topology's manager link originates from EmployeeVersion's nullable FK,
 * `clean()`, or serializer validation against self-reference or a cycle —
 * so "A manages A" or "A manages B manages A" is bad data the backend does
 * not prevent, and this builder has to guarantee an acyclic result itself
 * rather than assume the manager graph already is one (a cycle picked up
 * by a naive "root chain never reaches a natural root" pass would, left
 * unguarded, recurse forever in every consumer that walks `children` —
 * search, depth, and render alike).
 *
 * The fix lives here, once, at construction time: each node has at most
 * one outgoing edge (its manager), so the manager graph is a classic
 * "functional graph" and a single pass of 3-colour DFS finds every cycle
 * in O(n). WHITE = unvisited, GRAY = on the chain currently being walked,
 * BLACK = fully resolved. Walking a chain and landing on a GRAY node means
 * it loops back on itself; that node's edge to its manager is the one cut,
 * turning it into that loop's sole synthetic root with the rest of the
 * (former) cycle hanging off it as an ordinary chain — never two members
 * of the same loop both claiming root status while still listing each
 * other as a report. Every node is visited at most once (BLACK short-
 * circuits immediately), and — because this determines root/child
 * placement itself rather than filtering after the fact — every node still
 * gets placed exactly once, so nobody drops out of the chart.
 */
function buildForest(rows: OrgChartNodeSummary[], departmentName: (id: number) => string) {

  const nodeById = new Map<number, OrgNode>()
  const managerByEmployeeId = new Map(rows.map((row) => [row.employee_id, row.manager_id]))
  rows.forEach((row) => {
    nodeById.set(row.employee_id, {
      employeeId: row.employee_id,
      name: row.display_name,
      employeeNumber: row.employee_number,
      jobTitle: row.job_title,
      departmentName: departmentName(row.department),
      children: [],
    })
  })

  const WHITE = 0
  const GRAY = 1
  const BLACK = 2
  const state = new Map<number, 0 | 1 | 2>()
  const brokenEdge = new Set<number>()

  function resolveChain(startId: number) {
    const chain: number[] = []
    let id: number | undefined = startId
    while (id !== undefined) {
      const st = state.get(id) ?? WHITE
      if (st === BLACK) break // already resolved via some other chain — done
      if (st === GRAY) {
        brokenEdge.add(id) // this chain looped back on `id` — cut its edge to its manager
        break
      }
      state.set(id, GRAY)
      chain.push(id)
      const managerId: number | null = managerByEmployeeId.get(id) ?? null
      id = managerId !== null && nodeById.has(managerId) ? managerId : undefined
    }
    chain.forEach((cid) => state.set(cid, BLACK))
  }
  rows.forEach((row) => resolveChain(row.employee_id))

  const roots: OrgNode[] = []
  rows.forEach((row) => {
    const node = nodeById.get(row.employee_id)!
    const managerId = row.manager_id
    const managerNode = managerId !== null ? nodeById.get(managerId) : undefined
    if (managerNode && !brokenEdge.has(row.employee_id)) {
      managerNode.children.push(node)
    } else {
      if (managerNode) node.brokenLoopManagerName = managerNode.name
      roots.push(node)
    }
  })

  const byName = (a: OrgNode, b: OrgNode) => a.name.localeCompare(b.name)
  const sortTree = (node: OrgNode) => {
    node.children.sort(byName)
    node.children.forEach(sortTree)
  }
  roots.sort(byName)
  roots.forEach(sortTree)

  const brokenLoopCount = rows.filter((row) => nodeById.get(row.employee_id)!.brokenLoopManagerName).length

  return { roots, totalShown: rows.length, brokenLoopCount }
}

/** Max depth of the forest (roots = depth 0). buildForest already
 * guarantees the tree it hands back is acyclic (see its cycle scan), so
 * this ancestor-path guard should never fire — kept as cheap belt-and-
 * braces against a future bug in that construction, not as the thing
 * standing between a bad manager chain and a hung tab. */
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
  const [viewMode, setViewMode] = useState<'tree' | 'focused'>('tree')
  const [search, setSearch] = useState('')
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set())

  const departmentName = (id: number) => departments.get(id)?.name ?? `#${id}`

  const { data, error } = useApiQuery(
    () => fetchAllPages<OrgChartNodeSummary>('/employees/org-chart/'),
    [],
    { errorMessage: 'Failed to load the org chart.' },
  )

  const forest = useMemo(() => {
    if (!data) return null
    return buildForest(data, departmentName)
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
        {viewMode === 'tree' && (
          <input
            className="search-input"
            placeholder="Search by name, title, or department…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        )}
      </div>

      <div className="tab-row" role="tablist" aria-label="Org chart view">
        <button
          type="button"
          role="tab"
          aria-selected={viewMode === 'tree'}
          className={`tab-button${viewMode === 'tree' ? ' tab-button-active' : ''}`}
          onClick={() => setViewMode('tree')}
        >
          Tree view
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={viewMode === 'focused'}
          className={`tab-button${viewMode === 'focused' ? ' tab-button-active' : ''}`}
          onClick={() => setViewMode('focused')}
        >
          Focused view
        </button>
      </div>

      {error && <p className="form-error">{error}</p>}

      {loading ? (
        <p className="empty-state">Loading…</p>
      ) : viewMode === 'focused' ? (
        data && <FocusedView rows={data} departmentName={departmentName} />
      ) : forest && forest.totalShown === 0 ? (
        <p className="empty-state">No employees with a current record are visible to you.</p>
      ) : forest ? (
        <>
          <p className="hint-text">
            {forest.totalShown} {forest.totalShown === 1 ? 'person' : 'people'} shown · {forest.roots.length}{' '}
            root{forest.roots.length === 1 ? '' : 's'} · max depth {depth}
            {forest.brokenLoopCount > 0 && (
              <>
                {' '}
                · <span className="warning-badge">
                  {forest.brokenLoopCount} reporting loop{forest.brokenLoopCount === 1 ? '' : 's'} detected
                </span>
              </>
            )}
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

/** Per-department, Teams-"reports to"-style drill-down: one focused person
 * at a time (their manager above, their direct reports below) instead of
 * the tree view's whole-company expandable tree. Department is a hard
 * boundary (design choice, not a limitation of the data) -- a manager or
 * report outside the selected department simply doesn't appear, the same
 * way buildForest already treats "manager not in this fetch" as a root. */
function FocusedView({ rows, departmentName }: { rows: OrgChartNodeSummary[]; departmentName: (id: number) => string }) {
  const { departmentList } = useReferenceData()
  const departmentIdsPresent = useMemo(() => new Set(rows.map((r) => r.department)), [rows])
  const availableDepartments = useMemo(
    () =>
      departmentList
        .filter((d) => departmentIdsPresent.has(d.id))
        .sort((a: Department, b: Department) => a.name.localeCompare(b.name)),
    [departmentList, departmentIdsPresent],
  )

  const [departmentId, setDepartmentId] = useState<number | null>(availableDepartments[0]?.id ?? null)
  const [focusedId, setFocusedId] = useState<number | null>(null)
  const [search, setSearch] = useState('')

  const departmentRows = useMemo(
    () => (departmentId === null ? [] : rows.filter((r) => r.department === departmentId)),
    [rows, departmentId],
  )
  const forest = useMemo(() => buildForest(departmentRows, departmentName), [departmentRows, departmentName])
  const nodeById = useMemo(() => flattenNodes(forest.roots), [forest])
  const parentOf = useMemo(() => flattenParents(forest.roots), [forest])

  function selectDepartment(id: number) {
    setDepartmentId(id)
    setFocusedId(null)
    setSearch('')
  }

  const searchMatches = useMemo(() => {
    const trimmed = search.trim().toLowerCase()
    if (!trimmed) return []
    return [...nodeById.values()].filter((n) => matchesQuery(n, trimmed)).slice(0, 8)
  }, [nodeById, search])

  const focused = focusedId !== null ? nodeById.get(focusedId) ?? null : null
  const manager = focused ? parentOf.get(focused.employeeId) ?? null : null

  // Breadcrumb: department name, then the chain of managers down to the
  // focused person — clicking any crumb (including the department name,
  // which clears focus back to "all top-level people") jumps straight there.
  const breadcrumb = useMemo(() => {
    const chain: OrgNode[] = []
    let cursor = focused
    while (cursor) {
      chain.unshift(cursor)
      cursor = parentOf.get(cursor.employeeId) ?? null
    }
    return chain
  }, [focused, parentOf])

  return (
    <div>
      <div className="detail-card" style={{ marginBottom: 16 }}>
        <label>
          Department
          <select
            value={departmentId ?? ''}
            onChange={(e) => selectDepartment(Number(e.target.value))}
          >
            {availableDepartments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {departmentId === null || availableDepartments.length === 0 ? (
        <p className="empty-state">No employees with a current record are visible to you.</p>
      ) : forest.totalShown === 0 ? (
        <p className="empty-state">No employees in this department are visible to you.</p>
      ) : (
        <>
          <div className="page-header" style={{ marginBottom: 8 }}>
            <input
              className="search-input"
              placeholder="Jump to someone…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          {search.trim() && (
            <ul className="org-search-results">
              {searchMatches.length === 0 ? (
                <li className="hint-text">No matches for &ldquo;{search.trim()}&rdquo;.</li>
              ) : (
                searchMatches.map((n) => (
                  <li key={n.employeeId}>
                    <button
                      type="button"
                      className="btn-link"
                      onClick={() => {
                        setFocusedId(n.employeeId)
                        setSearch('')
                      }}
                    >
                      {n.name} <span className="hint-text">· {n.jobTitle}</span>
                    </button>
                  </li>
                ))
              )}
            </ul>
          )}

          <nav className="breadcrumb-trail" aria-label="Reporting line">
            <button type="button" className="btn-link" onClick={() => setFocusedId(null)}>
              {departmentName(departmentId)}
            </button>
            {breadcrumb.map((n) => (
              <span key={n.employeeId}>
                {' '}
                &rsaquo;{' '}
                <button type="button" className="btn-link" onClick={() => setFocusedId(n.employeeId)}>
                  {n.name}
                </button>
              </span>
            ))}
          </nav>

          {focused === null ? (
            <>
              <p className="hint-text">{forest.roots.length} at the top level of this department.</p>
              <OrgCardGrid nodes={forest.roots} onSelect={setFocusedId} />
            </>
          ) : (
            <>
              {manager && (
                <div style={{ marginBottom: 8 }}>
                  <p className="hint-text" style={{ marginBottom: 4 }}>
                    Reports to
                  </p>
                  <OrgCardGrid nodes={[manager]} onSelect={setFocusedId} />
                </div>
              )}
              <OrgFocusCard node={focused} />
              <p className="hint-text" style={{ margin: '16px 0 4px' }}>
                {focused.children.length === 0
                  ? 'No direct reports.'
                  : `${focused.children.length} direct report${focused.children.length === 1 ? '' : 's'}`}
              </p>
              <OrgCardGrid nodes={focused.children} onSelect={setFocusedId} />
            </>
          )}
        </>
      )}
    </div>
  )
}

function OrgFocusCard({ node }: { node: OrgNode }) {
  return (
    <div className="detail-card org-focus-card">
      <div className="org-node-name" style={{ fontSize: 18 }}>
        {node.name} <span className="hint-text">#{node.employeeNumber}</span>
      </div>
      <div className="hint-text">
        {node.jobTitle} · {node.departmentName}
      </div>
      {node.brokenLoopManagerName && (
        <span className="warning-badge">
          Reporting loop detected — link to manager &ldquo;{node.brokenLoopManagerName}&rdquo; was cut to show this
          person
        </span>
      )}
    </div>
  )
}

function OrgCardGrid({ nodes, onSelect }: { nodes: OrgNode[]; onSelect: (id: number) => void }) {
  if (nodes.length === 0) return null
  return (
    <div className="org-card-grid">
      {nodes.map((n) => (
        <button key={n.employeeId} type="button" className="org-card" onClick={() => onSelect(n.employeeId)}>
          <div className="org-node-name">{n.name}</div>
          <div className="hint-text">{n.jobTitle}</div>
          <div className="hint-text">
            {n.children.length} direct report{n.children.length === 1 ? '' : 's'}
          </div>
        </button>
      ))}
    </div>
  )
}

function flattenNodes(roots: OrgNode[]): Map<number, OrgNode> {
  const byId = new Map<number, OrgNode>()
  const walk = (node: OrgNode) => {
    byId.set(node.employeeId, node)
    node.children.forEach(walk)
  }
  roots.forEach(walk)
  return byId
}

function flattenParents(roots: OrgNode[]): Map<number, OrgNode | null> {
  const parentOf = new Map<number, OrgNode | null>()
  const walk = (node: OrgNode, parent: OrgNode | null) => {
    parentOf.set(node.employeeId, parent)
    node.children.forEach((child) => walk(child, node))
  }
  roots.forEach((root) => walk(root, null))
  return parentOf
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
          {node.brokenLoopManagerName && (
            <span className="warning-badge">
              Reporting loop detected — link to manager &ldquo;{node.brokenLoopManagerName}&rdquo; was cut to show this person
            </span>
          )}
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
