import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';
import { createElement } from 'react';

const STORAGE_KEY = 'nanobot-theme';

interface ThemeContextValue {
  isDark: boolean;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  isDark: true,
  toggleTheme: () => {},
});

export function useTheme() {
  return useContext(ThemeContext);
}

function getInitialTheme(): boolean {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored !== 'light';
  } catch {
    return true;
  }
}

function applyTheme(isDark: boolean) {
  if (isDark) {
    document.documentElement.classList.remove('light');
  } else {
    document.documentElement.classList.add('light');
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [isDark, setIsDark] = useState(getInitialTheme);

  useEffect(() => {
    applyTheme(isDark);
  }, [isDark]);

  const toggleTheme = useCallback(() => {
    setIsDark(prev => {
      const next = !prev;
      try {
        localStorage.setItem(STORAGE_KEY, next ? 'dark' : 'light');
      } catch { /* localStorage unavailable */ }
      return next;
    });
  }, []);

  return createElement(ThemeContext.Provider, { value: { isDark, toggleTheme } }, children);
}

// 初始化主题（在 React 渲染前调用，防止闪烁）
export function initTheme() {
  applyTheme(getInitialTheme());
}
