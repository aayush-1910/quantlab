/** Helpers for reading Next.js search params, which may be absent or repeated. */

export type SearchParams = Record<string, string | string[] | undefined>;

export function single(params: SearchParams, key: string): string | undefined {
  const value = params[key];
  const first = Array.isArray(value) ? value[0] : value;
  return first === undefined || first.trim() === "" ? undefined : first.trim();
}

/** Builds "/path?a=1&b=2", leaving out undefined and empty values. */
export function href(path: string, query: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== "") search.set(key, value);
  }
  const text = search.toString();
  return text ? `${path}?${text}` : path;
}
