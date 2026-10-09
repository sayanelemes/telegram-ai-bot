import React from 'react';
import { Sun, Moon } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';

interface ThemeToggleProps {
  className?: string;
  style?: React.CSSProperties;
}

export const ThemeToggle: React.FC<ThemeToggleProps> = ({ className, style }) => {
  const { effectiveTheme, toggleTheme } = useTheme();

  return (
    <button
      onClick={toggleTheme}
      className={className}
      aria-label="Переключить тему"
      title={effectiveTheme === 'dark' ? 'Включить светлую тему' : 'Включить тёмную тему'}
      style={{
        background: 'var(--color-card-bg)',
        border: '1px solid var(--color-border)',
        borderRadius: '50%',
        width: '36px',
        height: '36px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        color: effectiveTheme === 'dark' ? '#fbbf24' : '#4b5563',
        boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
        transition: 'transform 0.15s ease, background-color 0.2s ease, color 0.2s ease',
        ...style,
      }}
    >
      {effectiveTheme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
};
