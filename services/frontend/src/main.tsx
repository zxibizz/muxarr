import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';

import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './app/App';
import { AppProviders } from './app/AppProviders';
import { theme } from './app/theme';

const root = document.getElementById('root');
if (!root) {
  throw new Error('#root is missing from index.html');
}

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <MantineProvider theme={theme} forceColorScheme="dark">
      <Notifications position="top-right" />
      <AppProviders>
        <App />
      </AppProviders>
    </MantineProvider>
  </React.StrictMode>,
);
