import '@mantine/core/styles.css';

import { MantineProvider, createTheme } from '@mantine/core';
import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';

const theme = createTheme({
  primaryColor: 'indigo',
  defaultRadius: 'md',
});

const root = document.getElementById('root');
if (!root) {
  throw new Error('#root is missing from index.html');
}

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="dark">
      <App />
    </MantineProvider>
  </React.StrictMode>,
);
