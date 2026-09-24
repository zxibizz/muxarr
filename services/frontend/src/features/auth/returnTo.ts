/** Only same-app paths: a crafted `returnTo=//evil.example` must not become an open redirect. */
export function safeReturnTo(value: string | null): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.startsWith('/\\')) {
    return '/';
  }
  return value;
}

export function loginPath(returnTo: string): string {
  return returnTo === '/' ? '/login' : `/login?returnTo=${encodeURIComponent(returnTo)}`;
}
