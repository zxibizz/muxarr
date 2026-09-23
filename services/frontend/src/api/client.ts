const TOKEN_KEY = 'muxarr.token';

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

/** What to show a user for a failed request; null when the token prompt already covers it. */
export function describeError(error: unknown): string | null {
  if (error === null || error === undefined || isUnauthorised(error)) return null;
  return error instanceof Error ? error.message : String(error);
}

export function getToken(): string {
  return window.localStorage.getItem(TOKEN_KEY) ?? '';
}

export function setToken(token: string): void {
  if (token) {
    window.localStorage.setItem(TOKEN_KEY, token);
  } else {
    window.localStorage.removeItem(TOKEN_KEY);
  }
}

export async function request<T>(path: string, init: RequestInit = {}, body?: unknown): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  if (body !== undefined) {
    headers.set('Content-Type', 'application/json');
  }

  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers,
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  } catch (cause) {
    throw new ApiError(0, `cannot reach the muxarr daemon (${String(cause)})`);
  }

  if (!response.ok) {
    throw new ApiError(response.status, await describe(response));
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
