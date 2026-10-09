import React from 'react';
import { Trash2 } from 'lucide-react';
import { FoodEntry } from '../api/types';

interface MealCardProps {
  meal: FoodEntry;
  onClick: () => void;
  onDelete?: (id: number) => void;
}

export const MealCard: React.FC<MealCardProps> = ({ meal, onClick, onDelete }) => {
  const getMealEmoji = (type: string) => {
    const lower = type.toLowerCase();
    if (lower.includes('завтрак')) return '🍳';
    if (lower.includes('обед')) return '🍗';
    if (lower.includes('ужин')) return '🍽️';
    return '🍌';
  };

  const ingredientsList = meal.items.map((i) => i.name).join(', ') || 'Блюдо';

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onDelete && confirm(`Удалить "${meal.meal_type}" (${meal.total_calories} ккал) из дневника?`)) {
      onDelete(meal.id);
    }
  };

  return (
    <div className="meal-item" onClick={onClick}>
      <div className="meal-info">
        <div className="meal-type-title">
          <span>{getMealEmoji(meal.meal_type)}</span>
          <span>{meal.meal_type}</span>
          <span style={{ fontSize: '12px', color: 'var(--color-text-muted)', fontWeight: 400 }}>
            {meal.entry_time}
          </span>
        </div>
        <div className="meal-desc">{ingredientsList}</div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <div className="meal-cals">{meal.total_calories} ккал</div>
        {onDelete && (
          <button
            title="Удалить приём пищи"
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--color-text-muted)',
              cursor: 'pointer',
              padding: '4px',
              display: 'flex',
              alignItems: 'center',
            }}
            onClick={handleDelete}
          >
            <Trash2 size={16} />
          </button>
        )}
      </div>
    </div>
  );
};
