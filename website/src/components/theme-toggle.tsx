'use client';

import { useTheme } from 'next-themes';
import { useSyncExternalStore } from 'react';
import { SunIcon, MoonIcon } from 'lucide-react';

const subscribeToHydration = () => () => {};
const getClientSnapshot = () => true;
const getServerSnapshot = () => false;

export function ThemeToggle() {
  const mounted = useSyncExternalStore(
    subscribeToHydration,
    getClientSnapshot,
    getServerSnapshot,
  );
  const { resolvedTheme, setTheme } = useTheme();

  const isDark = mounted && resolvedTheme === 'dark';

  return (
    <button
      type="button"
      onClick={() => setTheme(isDark ? 'light' : 'dark')}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      className="group relative inline-flex size-8 items-center justify-center rounded-md text-ink-soft hover:text-ink transition-colors"
    >
      <SunIcon
        className={`size-4 transition-[color,opacity,transform] duration-200 group-hover:rotate-12 group-hover:text-fd-primary ${
          isDark ? 'opacity-0 absolute' : 'opacity-100'
        }`}
      />
      <MoonIcon
        className={`size-4 transition-[color,opacity,transform] duration-200 group-hover:rotate-12 group-hover:text-fd-primary ${
          isDark ? 'opacity-100' : 'opacity-0 absolute'
        }`}
      />
    </button>
  );
}
