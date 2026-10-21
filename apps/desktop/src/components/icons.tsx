import type { ReactNode } from "react";

const ICON_SIZE = 18;
const ICON_STROKE = 1.2;

function Icon({ children, size = ICON_SIZE }: { children: ReactNode; size?: number }) {
  return (
    <svg
      viewBox="0 0 16 16"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={ICON_STROKE}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export function FolderIcon({ size }: { size?: number } = {}) {
  return (
    <Icon size={size}>
      <path d="M2.25 4.35c0-.6.5-1.1 1.1-1.1h2.8l1.05 1.4h5.45c.6 0 1.1.5 1.1 1.1V12c0 .6-.5 1.1-1.1 1.1H3.35c-.6 0-1.1-.5-1.1-1.1V4.35Z" />
    </Icon>
  );
}

export function NewChatIcon({ size }: { size?: number } = {}) {
  return (
    <Icon size={size}>
      <path d="M2.35 3.25h8.9c.6 0 1.1.5 1.1 1.1v5.05c0 .6-.5 1.1-1.1 1.1H6.85L4.55 13V10.5H2.35c-.6 0-1.1-.5-1.1-1.1V4.35c0-.6.5-1.1 1.1-1.1Z" />
      <path d="M6.8 5.7v2.4M5.6 6.9h2.4" />
    </Icon>
  );
}

export function SkillsIcon() {
  return (
    <Icon>
      <path d="M8 2.35 13.55 5.1 8 7.85 2.45 5.1 8 2.35Z" />
      <path d="M2.45 8.2 8 10.95 13.55 8.2" />
      <path d="M2.45 11.2 8 13.95 13.55 11.2" />
    </Icon>
  );
}

export function SettingsIcon() {
  return (
    <Icon>
      <path d="M6.8 2.05h2.4l.28 1.4c.36.12.7.3.98.54l1.28-.74 1.2 1.2-.74 1.28c.24.28.42.62.54.98l1.4.28v2.4l-1.4.28a3.2 3.2 0 0 1-.54.98l.74 1.28-1.2 1.2-1.28-.74a3.2 3.2 0 0 1-.98.54l-.28 1.4H6.8l-.28-1.4a3.2 3.2 0 0 1-.98-.54l-1.28.74-1.2-1.2.74-1.28a3.2 3.2 0 0 1-.54-.98l-1.4-.28v-2.4l1.4-.28c.12-.36.3-.7.54-.98l-.74-1.28 1.2-1.2 1.28.74c.28-.24.62-.42.98-.54l.28-1.4Z" />
      <circle cx="8" cy="8" r="1.7" />
    </Icon>
  );
}
