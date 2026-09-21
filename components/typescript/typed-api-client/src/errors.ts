/**
 * Typed API errors.
 *
 * The server is expected to answer failures with RFC 9457 `application/problem+json`
 * bodies. Every error carries the parsed problem (when present), the HTTP status
 * and the request id, so a support ticket can quote one line and the server team
 * can find the request in their logs.
 */
export interface Problem {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  instance?: string;
  /** Field-level errors for 422 responses: `{ "field.path": ["message", ...] }`. */
  errors?: Record<string, string[]>;
  /** Platform deny code, e.g. `ladder.above`, when the platform refused an action. */
  code?: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly problem: Problem | undefined;
  readonly requestId: string | undefined;

  constructor(message: string, status: number, problem?: Problem, requestId?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.problem = problem;
    this.requestId = requestId;
  }

  /** A short line a person can paste into a support request. */
  get supportLine(): string {
    const parts = [`HTTP ${this.status}`, this.problem?.code, this.requestId && `request ${this.requestId}`];
    return parts.filter(Boolean).join(" · ");
  }
}

export class NetworkError extends Error {
  constructor(cause: unknown) {
    super("The server could not be reached.");
    this.name = "NetworkError";
    this.cause = cause;
  }
}

/** The client refused to send the request: its URL is on another origin than the API, and the bearer never goes there. */
export class CrossOriginError extends Error {
  readonly url: string;
  readonly expectedOrigin: string;
  constructor(url: string, expectedOrigin: string) {
    super(`Refused to call ${url}: the API client only talks to ${expectedOrigin}.`);
    this.name = "CrossOriginError";
    this.url = url;
    this.expectedOrigin = expectedOrigin;
  }
}

export class UnauthorizedError extends ApiError {
  constructor(problem?: Problem, requestId?: string) {
    super("Your session has ended. Sign in again to continue.", 401, problem, requestId);
    this.name = "UnauthorizedError";
  }
}

export class ForbiddenError extends ApiError {
  constructor(problem?: Problem, requestId?: string) {
    super(problem?.detail ?? "Your role does not allow this.", 403, problem, requestId);
    this.name = "ForbiddenError";
  }
}

export class NotFoundError extends ApiError {
  constructor(problem?: Problem, requestId?: string) {
    super(problem?.detail ?? "That item does not exist or you cannot see it.", 404, problem, requestId);
    this.name = "NotFoundError";
  }
}

export class ConflictError extends ApiError {
  constructor(problem?: Problem, requestId?: string) {
    super(problem?.detail ?? "This was changed by someone else. Reload and try again.", 409, problem, requestId);
    this.name = "ConflictError";
  }
}

export class ValidationError extends ApiError {
  readonly fieldErrors: Record<string, string[]>;
  constructor(problem?: Problem, requestId?: string) {
    super(problem?.detail ?? "Some answers need attention.", 422, problem, requestId);
    this.name = "ValidationError";
    this.fieldErrors = problem?.errors ?? {};
  }
}

export class ServerError extends ApiError {
  constructor(status: number, problem?: Problem, requestId?: string) {
    super(problem?.detail ?? "The platform hit a problem. It has been recorded; try again in a moment.", status, problem, requestId);
    this.name = "ServerError";
  }
}

export function errorFromResponse(status: number, problem: Problem | undefined, requestId: string | undefined): ApiError {
  switch (status) {
    case 401:
      return new UnauthorizedError(problem, requestId);
    case 403:
      return new ForbiddenError(problem, requestId);
    case 404:
      return new NotFoundError(problem, requestId);
    case 409:
      return new ConflictError(problem, requestId);
    case 422:
      return new ValidationError(problem, requestId);
    default:
      return status >= 500
        ? new ServerError(status, problem, requestId)
        : new ApiError(problem?.detail ?? `Request failed (${status}).`, status, problem, requestId);
  }
}

/** True when the failure is worth retrying automatically (idempotent requests only). */
export function isTransient(error: unknown): boolean {
  return error instanceof NetworkError || (error instanceof ServerError && (error.status === 502 || error.status === 503 || error.status === 504));
}
