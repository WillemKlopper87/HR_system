import { Component, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

/** Catches a lazy-loaded route chunk failing to load or render (a stale
 * chunk hash after a redeploy, a network blip) so one broken route shows
 * a recoverable message instead of taking down the whole app shell. */
export class RouteErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error) {
    // eslint-disable-next-line no-console
    console.error('Route failed to load:', error)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="page">
          <p className="form-error">
            This page failed to load. If the app was just updated, reloading usually fixes it.
          </p>
          <button type="button" className="btn-primary" onClick={() => window.location.reload()}>
            Reload
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
