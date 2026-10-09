import React from 'react';
import { X, Trash2, Sparkles } from 'lucide-react';
import { FoodEntry } from '../api/types';

interface MealDetailModalProps {
  meal: FoodEntry | null;
  onClose: () => void;
  onDelete: (id: number) => void;
}

export const MealDetailModal: React.FC<MealDetailModalProps> = ({ meal, onClose, onDelete }) => {
  if (!meal) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title">
            {meal.meal_type} ({meal.entry_time})
          </div>
          <button className="modal-close-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div style={{ textAlign: 'center', marginBottom: '20px' }}>
          <div style={{ fontSize: '32px', fontWeight: 800 }}>{meal.total_calories} ккал</div>
          <div style={{ fontSize: '13px', color: 'var(--color-text-muted)' }}>
            Б: {meal.total_protein}г • Ж: {meal.total_fat}г • У: {meal.total_carbs}г
          </div>
        </div>

        <div style={{ marginBottom: '20px' }}>
          <div style={{ fontSize: '14px', fontWeight: 700, marginBottom: '10px' }}>Продукты и ингредиенты:</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {meal.items.map((item, idx) => (
              <div
                key={idx}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  background: 'var(--color-card-bg)',
                  padding: '10px 14px',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--color-border)',
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: '14px' }}>{item.name}</div>
                  <div style={{ fontSize: '12px', color: 'var(--color-text-muted)' }}>
                    ~{Math.round(item.portion_g)} г • Б:{item.protein_g} Ж:{item.fat_g} У:{item.carbs_g}
                  </div>
                </div>
                <div style={{ fontWeight: 700, fontSize: '14px' }}>{item.calories} ккал</div>
              </div>
            ))}
          </div>
        </div>

        {meal.advice && (
          <div
            style={{
              background: 'rgba(37, 99, 235, 0.08)',
              border: '1px solid rgba(37, 99, 235, 0.2)',
              borderRadius: 'var(--radius-md)',
              padding: '12px 14px',
              marginBottom: '20px',
              fontSize: '13px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 700, color: 'var(--color-primary)', marginBottom: '4px' }}>
              <Sparkles size={16} />
              <span>Совет AI:</span>
            </div>
            <div>{meal.advice}</div>
          </div>
        )}

        <button
          className="btn btn-danger"
          style={{ marginTop: '10px' }}
          onClick={() => {
            if (confirm('Удалить этот приём пищи из дневника?')) {
              onDelete(meal.id);
              onClose();
            }
          }}
        >
          <Trash2 size={16} />
          <span>Удалить запись</span>
        </button>
      </div>
    </div>
  );
};
