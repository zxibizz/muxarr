import { BrowserRouter, Route, Routes } from 'react-router';
import { HistoryPage } from '../features/history/HistoryPage';
import { SettingsPage } from '../features/settings/SettingsPage';
import { SystemPage } from '../features/system/SystemPage';
import { AppLayout } from './AppLayout';

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<HistoryPage />} />
        <Route path="system" element={<SystemPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<HistoryPage />} />
      </Route>
    </Routes>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
