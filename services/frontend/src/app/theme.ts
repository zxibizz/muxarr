import {
  Badge,
  Card,
  Drawer,
  Modal,
  NavLink,
  Paper,
  Table,
  Tooltip,
  createTheme,
} from '@mantine/core';
import type { MantineColorsTuple } from '@mantine/core';

// Violet sets muxarr apart from the *arr family's yellow, blue and green.
const brand: MantineColorsTuple = [
  '#f3f0ff',
  '#e4dcff',
  '#c5b5fb',
  '#a58bf8',
  '#8967f5',
  '#7751f3',
  '#6d45f3',
  '#5c37d9',
  '#512fc2',
  '#4426ab',
];

// A cooler, deeper dark scale than Mantine's default grey; [7] is the page, [6] a surface.
const dark: MantineColorsTuple = [
  '#c9ccd6',
  '#a4a8b7',
  '#7d8295',
  '#5a5f72',
  '#3a3e4e',
  '#2b2e3b',
  '#1e2029',
  '#16181f',
  '#111218',
  '#0b0c10',
];

export const theme = createTheme({
  primaryColor: 'brand',
  primaryShade: 6,
  colors: { brand, dark },
  defaultRadius: 'md',
  cursorType: 'pointer',
  fontFamily:
    "Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif",
  fontFamilyMonospace:
    "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace",
  headings: {
    fontWeight: '650',
    sizes: {
      h1: { fontSize: '1.625rem', lineHeight: '1.25' },
      h2: { fontSize: '1.25rem', lineHeight: '1.3' },
      h3: { fontSize: '1.0625rem', lineHeight: '1.35' },
    },
  },
  components: {
    Card: Card.extend({ defaultProps: { withBorder: true, padding: 'lg', radius: 'lg' } }),
    Paper: Paper.extend({ defaultProps: { radius: 'lg' } }),
    Badge: Badge.extend({ defaultProps: { radius: 'sm', variant: 'light' } }),
    Tooltip: Tooltip.extend({ defaultProps: { withArrow: true, openDelay: 200 } }),
    Table: Table.extend({ defaultProps: { verticalSpacing: 'sm', horizontalSpacing: 'md' } }),
    NavLink: NavLink.extend({ defaultProps: { variant: 'light' } }),
    Drawer: Drawer.extend({
      defaultProps: { position: 'right', overlayProps: { backgroundOpacity: 0.5, blur: 3 } },
    }),
    Modal: Modal.extend({
      defaultProps: { centered: true, overlayProps: { backgroundOpacity: 0.55, blur: 3 } },
    }),
  },
});
