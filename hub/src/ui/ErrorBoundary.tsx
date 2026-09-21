import { Component, type ErrorInfo, type ReactNode } from "react";
import { ApiError } from "../api/errors";
import { env } from "../config/env";
import { track } from "../telemetry";

interface Props {
  children: ReactNode;
  fallback?: (error: Error, reset: () => void) => ReactNode;
}
interface State {
  error: Error | null;
}

/**
 * Last line of defence: a rendering error shows a recoverable page instead of
 * a blank screen, records the failure, and offers a way back.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    track("ui.error", { message: error.message, stack: info.componentStack ?? undefined });
  }

  reset = () => this.setState({ error: null });

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    if (this.props.fallback) return this.props.fallback(error, this.reset);
    const support = error instanceof ApiError ? error.supportLine : undefined;
    // A full document load, on purpose: the boundary sits outside the routes, and the path depends on the router.
    const discoverHref = env.VITE_ROUTER === "hash" ? "#/discover" : "/discover";
    return (
      <div className="hub" style={{ minHeight: 400 }}>
        <div className="hwrap">
          <div className="banner crit" role="alert">
            <div className="col" style={{ gap: 6 }}>
              <b>Something went wrong on this page.</b>
              <span>{error.message}</span>
              {support && (
                <span className="mono" style={{ fontSize: 11.5 }}>
                  {support}
                </span>
              )}
              <div className="row" style={{ marginTop: 6 }}>
                <button type="button" className="btn s" onClick={this.reset}>
                  Try again
                </button>
                <a className="btn g s" href={discoverHref}>
                  Back to Discover
                </a>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }
}
