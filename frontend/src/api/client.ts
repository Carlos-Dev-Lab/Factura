const CSRF_COOKIE = 'factura_csrf';
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

function readCookie(name: string): string {
  const match = document.cookie.split('; ').find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : '';
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail) && body.detail[0]?.msg) return String(body.detail[0].msg);
  } catch {
    /* respuesta sin JSON */
  }
  return `Error ${res.status}`;
}

type Body = FormData | object | undefined;

export async function request<T>(path: string, method = 'GET', body?: Body): Promise<T> {
  const headers: Record<string, string> = {};
  if (!SAFE_METHODS.has(method)) headers['X-CSRF-Token'] = readCookie(CSRF_COOKIE);
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }
  const res = await fetch(`/api/v1${path}`, { method, headers, body: payload, credentials: 'same-origin' });
  if (!res.ok) throw new ApiError(await errorMessage(res), res.status);
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export function query(params: Record<string, string | number | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : '';
}
