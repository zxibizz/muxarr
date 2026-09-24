import { Center, Loader } from '@mantine/core';
import { Navigate, Outlet, useLocation } from 'react-router';
import { useAuthStatus } from '../../api/queries';
import { loginPath } from './returnTo';

/** Nothing behind this renders until the daemon says the browser may see it. */
export function AuthGate() {
  const status = useAuthStatus();
  const { pathname, search } = useLocation();

  if (status.isPending) {
    return (
      <Center h="100vh">
        <Loader />
      </Center>
    );
  }
  // Unreachable daemon: let the pages render their own errors instead of a blank screen.
  if (status.data?.setup_required) return <Navigate to="/setup" replace />;
  if (status.data && !status.data.authenticated) {
    return <Navigate to={loginPath(pathname + search)} replace />;
  }
  return <Outlet />;
}
