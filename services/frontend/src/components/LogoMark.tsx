import { useId } from 'react';

interface Props {
  size?: number;
}

/** The mark from the favicon: sidecar tracks converging into one container. */
export function LogoMark({ size = 32 }: Props) {
  const gradient = useId();
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="64" y2="64" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#8967f5" />
          <stop offset="1" stopColor="#4426ab" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="16" fill={`url(#${gradient})`} />
      <g fill="none" stroke="#fff" strokeWidth="5" strokeLinecap="round">
        <path d="M13 19 C26 19 28 32 38 32" strokeOpacity=".55" />
        <path d="M13 32 H38" strokeOpacity=".85" />
        <path d="M13 45 C26 45 28 32 38 32" strokeOpacity=".55" />
      </g>
      <path d="M38 32 H51" stroke="#fff" strokeWidth="8" strokeLinecap="round" />
    </svg>
  );
}
