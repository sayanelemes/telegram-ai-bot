import React from 'react';
import { CalorieSummary } from '../api/types';

interface CalorieHeroProps {
  calories: CalorieSummary;
}

export const CalorieHero: React.FC<CalorieHeroProps> = ({ calories }) => {
  const isExceeded = calories.exceeded > 0;
  const percentage = Math.max(0, Math.min(100, calories.percentage));

  // Circular gauge dimensions
  const size = 210;
  const strokeWidth = 13;
  const center = size / 2;
  const radius = center - strokeWidth;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (percentage / 100) * circumference;

  const strokeColor = isExceeded
    ? 'var(--color-danger)'
    : 'url(#calorie-gradient)';

  return (
    <div className="calorie-hero circular-hero">
      <div className="circular-progress-wrapper">
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          className="circular-progress-svg"
        >
          <defs>
            <linearGradient id="calorie-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#3b82f6" />
              <stop offset="100%" stopColor="#10b981" />
            </linearGradient>
            <linearGradient id="calorie-exceeded-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#f59e0b" />
              <stop offset="100%" stopColor="#ef4444" />
            </linearGradient>
          </defs>

          {/* Background track circle */}
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke="var(--color-progress-track, rgba(120, 120, 128, 0.16))"
            strokeWidth={strokeWidth}
          />

          {/* Foreground progress circle */}
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke={isExceeded ? 'url(#calorie-exceeded-gradient)' : strokeColor}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            className="circular-progress-circle"
            transform={`rotate(-90 ${center} ${center})`}
          />
        </svg>

        {/* Center content inside circular ring */}
        <div className="circular-inner-content">
          <div className="calorie-status-label">
            {isExceeded ? 'Лимит превышен' : 'Осталось'}
          </div>

          <div className={`calorie-main-number ${isExceeded ? 'exceeded' : 'remaining'}`}>
            {isExceeded
              ? calories.exceeded.toLocaleString('ru-RU')
              : calories.remaining.toLocaleString('ru-RU')}
          </div>
          <div className="calorie-unit">ккал</div>

          <div className="calorie-sub-stats">
            {calories.consumed.toLocaleString('ru-RU')} / {calories.goal.toLocaleString('ru-RU')} ккал
          </div>
        </div>
      </div>

      <div className="calorie-percentage-badge">
        {isExceeded ? (
          <span className="badge-exceeded">⚠️ Превышение на {calories.exceeded} ккал</span>
        ) : (
          <span className="badge-normal">🔥 {calories.percentage}% от дневной нормы</span>
        )}
      </div>
    </div>
  );
};
