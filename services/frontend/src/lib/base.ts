// The container rewrites <base href> to MUXARR_URL_BASE at start-up, so the UI can
// sit under a sub-path (like the *arr apps' URL Base) without a rebuild.
export const BASE_PATH = new URL(document.baseURI).pathname.replace(/\/+$/, '');

export function withBase(path: string): string {
  return `${BASE_PATH}${path}`;
}
