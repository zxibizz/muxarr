import { withBase } from '../lib/base';

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }

  get unauthorised(): boolean {
    return this.status === 401;
  }
}

export function isUnauthorised(error: unknown): boolean {
  return error instanceof ApiError && error.unauthorised;
}

/** What to show a user for a failed request; null when the login redirect already covers it. */
export function describeError(error: unknown): string | null {
  if (error === null || error === undefined || isUnauthorised(error)) return null;
  return error instanceof Error ? error.message : String(error);
}

export async function request<T>(path: string, init: RequestInit = {}, body?: unknown): Promise<T> {
  const headers = new Headers(init.headers);
  // The daemon refuses cookie-authenticated writes without it: its CSRF guard.
  headers.set('X-Requested-With', 'XMLHttpRequest');
  if (body !== undefined) {
    headers.set('Content-Type', 'application/json');
  }

  let response: Response;
  try {
    response = await fetch(withBase(path), {
      ...init,
      headers,
      credentials: 'same-origin',
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  } catch (cause) {
    throw new ApiError(0, `cannot reach the Muxarr daemon (${String(cause)})`);
  }

  if (!response.ok) {
    throw new ApiError(response.status, await describe(response));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

async function describe(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === 'string') {
      return body.detail;
    }
    // FastAPI's own validation errors are a list of objects, not a string.
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((item) => (item as { msg?: string }).msg ?? String(item))
        .join('; ');
    }
  } catch {
    // Not JSON; fall through to the status text.
  }
  return `${response.status} ${response.statusText}`;
}
