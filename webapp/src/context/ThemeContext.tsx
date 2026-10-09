import React, { createContext, useContext, useState, useEffect } from 'react';

export type ThemeMode = 'light' | 'dark' | 'auto';

interface ThemeContextType {
  theme: ThemeMode;
  effectiveTheme: 'light' | 'dark';
  setTheme: (mode: ThemeMode) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextType>({
  theme: 'auto',
  effectiveTheme: 'light',
  setTheme: () => {},
  toggleTheme: () => {},
});

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [theme, setThemeState] = useState<ThemeMode>(() => {
    try {
      const saved = localStorage.getItem('app_theme');
      if (saved === 'light' || saved === 'dark' || saved === 'auto') {
        return saved;
      }
    } catch {}
    return 'auto';
  });

  const getSystemTheme = (): 'light' | 'dark' => {
    // 1. Check Telegram WebApp color scheme if inside Telegram
    const tgScheme = (window as any).Telegram?.WebApp?.colorScheme;
    if (tgScheme === 'dark' || tgScheme === 'light') {
      return tgScheme;
    }
    // 2. Check browser prefers-color-scheme
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    }
    return 'light';
  };

  const [effectiveTheme, setEffectiveTheme] = useState<'light' | 'dark'>(() => {
    return theme === 'auto' ? getSystemTheme() : theme;
  });

  const applyToDOM = (resolved: 'light' | 'dark') => {
    setEffectiveTheme(resolved);
    const root = document.documentElement;
    root.setAttribute('data-theme', resolved);
    root.classList.remove('theme-light', 'theme-dark');
    root.classList.add(`theme-${resolved}`);

    // Update meta theme-color for iOS status bar
    const metaThemeColor = document.querySelector('meta[name="theme-color"]');
    if (metaThemeColor) {
      metaThemeColor.setAttribute('content', resolved === 'dark' ? '#121214' : '#ffffff');
    }

    // Update Telegram WebApp header/background color if available
    try {
      const tg = (window as any).Telegram?.WebApp;
      if (tg) {
        if (typeof tg.setHeaderColor === 'function') {
          tg.setHeaderColor(resolved === 'dark' ? '#121214' : '#ffffff');
        }
        if (typeof tg.setBackgroundColor === 'function') {
          tg.setBackgroundColor(resolved === 'dark' ? '#121214' : '#ffffff');
        }
      }
    } catch {}
  };

  useEffect(() => {
    const resolved = theme === 'auto' ? getSystemTheme() : theme;
    applyToDOM(resolved);

    // If auto mode, listen for system theme changes
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = () => {
      if (theme === 'auto') {
        applyToDOM(getSystemTheme());
      }
    };

    if (mediaQuery.addEventListener) {
      mediaQuery.addEventListener('change', handleChange);
      return () => mediaQuery.removeEventListener('change', handleChange);
    }
  }, [theme]);

  const setTheme = (mode: ThemeMode) => {
    setThemeState(mode);
    try {
      localStorage.setItem('app_theme', mode);
    } catch {}
    try {
      (window as any).Telegram?.WebApp?.HapticFeedback?.selectionChanged?.();
    } catch {}
  };

  const toggleTheme = () => {
    const next: ThemeMode = effectiveTheme === 'dark' ? 'light' : 'dark';
    setTheme(next);
  };

  return (
    <ThemeContext.Provider value={{ theme, effectiveTheme, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = () => useContext(ThemeContext);
