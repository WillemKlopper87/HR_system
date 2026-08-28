import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { api, type Paginated } from '../api/client'
import type { EmployeeSearchSummary } from '../api/contracts'

interface Props {
  value: number | null
  onChange: (value: number | null) => void
  label?: string
  required?: boolean
}

export function EmployeeAsyncSelect({ value, onChange, label = 'Employee', required = false }: Props) {
  const id = useId()
  const [query, setQuery] = useState('')
  const [options, setOptions] = useState<EmployeeSearchSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const selected = useRef<EmployeeSearchSummary | null>(null)

  useEffect(() => {
    const term = query.trim()
    if (selected.current && query === `${selected.current.employee_number} — ${selected.current.display_name}`) return
    onChange(null)
    if (term.length < 2) {
      setOptions([])
      setOpen(false)
      setError(null)
      return
    }
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      setLoading(true)
      setError(null)
      try {
        const page = await api.get<Paginated<EmployeeSearchSummary>>(
          `/employees/search-summary/?q=${encodeURIComponent(term)}`,
          { signal: controller.signal },
        )
        setOptions(page.results)
        setOpen(true)
        setActiveIndex(page.results.length ? 0 : -1)
      } catch {
        if (!controller.signal.aborted) setError('Employee search failed. Please try again.')
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }, 250)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [query, onChange])

  function choose(option: EmployeeSearchSummary) {
    selected.current = option
    setQuery(`${option.employee_number} — ${option.display_name}`)
    setOpen(false)
    onChange(option.id)
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!open || options.length === 0) return
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const direction = event.key === 'ArrowDown' ? 1 : -1
      setActiveIndex((current) => (current + direction + options.length) % options.length)
    } else if (event.key === 'Enter' && activeIndex >= 0) {
      event.preventDefault()
      choose(options[activeIndex])
    } else if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <label className="employee-search">
      {label}
      <input
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={`${id}-results`}
        aria-activedescendant={activeIndex >= 0 ? `${id}-option-${activeIndex}` : undefined}
        value={query}
        onChange={(event) => { selected.current = null; setQuery(event.target.value) }}
        onFocus={() => { if (options.length) setOpen(true) }}
        onKeyDown={handleKeyDown}
        placeholder="Type a name or employee number"
        autoComplete="off"
        required={required && value === null}
      />
      {loading && <span className="field-status">Searching…</span>}
      {error && <span className="form-error" role="alert">{error}</span>}
      {open && (
        <ul id={`${id}-results`} className="employee-search-results" role="listbox">
          {options.length === 0 ? <li className="employee-search-empty">No matching employees.</li> : options.map((option, index) => (
            <li
              id={`${id}-option-${index}`}
              key={option.id}
              role="option"
              aria-selected={index === activeIndex}
              className={index === activeIndex ? 'active' : undefined}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => choose(option)}
            >
              <strong>{option.employee_number}</strong> — {option.display_name}
            </li>
          ))}
        </ul>
      )}
    </label>
  )
}
