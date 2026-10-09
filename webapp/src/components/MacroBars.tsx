import React from 'react';
import { MacrosSummary } from '../api/types';

interface MacroBarsProps {
  macros: MacrosSummary;
}

export const MacroBars: React.FC<MacroBarsProps> = ({ macros }) => {
  const items = [
    {
      name: 'Белки',
      color: 'var(--color-protein)',
      data: macros.protein,
    },
    {
      name: 'Жиры',
      color: 'var(--color-fat)',
      data: macros.fat,
    },
    {
      name: 'Углеводы',
      color: 'var(--color-carbs)',
      data: macros.carbs,
    },
  ];

  return (
    <div className="macros-grid">
      {items.map((item) => {
        const percent = Math.min(100, Math.round((item.data.consumed / (item.data.goal || 1)) * 100));
        return (
          <div key={item.name} className="macro-card">
            <div className="macro-name">{item.name}</div>
            <div className="macro-values">
              {Math.round(item.data.consumed)} / {item.data.goal} г
            </div>
            <div className="progress-container">
              <div
                className="progress-bar-fill"
                style={{
                  width: `${percent}%`,
                  backgroundColor: item.color,
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
};
