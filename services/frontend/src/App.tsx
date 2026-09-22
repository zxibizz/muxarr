import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { AuthGateProvider } from './auth';
import { AppLayout } from './components/AppLayout';
import { HistoryPage } from './pages/HistoryPage';
import { SettingsPage } from './pages/SettingsPage';

export function App() {
  return (
    <BrowserRouter>
      <AuthGateProvider>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<HistoryPage />} />
            <Route path="settings" element={<SettingsPage />} />
            {/* nginx serves index.html for every path, so a stale link lands here. */}
            <Route path="*" element={<HistoryPage />} />
          </Route>
        </Routes>
      </AuthGateProvider>
    </BrowserRouter>
  );
}
