import React, { useState } from 'react';
import { X, Check, Edit2, Sparkles, Loader2 } from 'lucide-react';
import { FoodAnalysisResult } from '../api/types';

interface ConfirmFoodModalProps {
  data: FoodAnalysisResult | null;
  onClose: () => void;
  onSave: (data: any) => Promise<void>;
}

export const ConfirmFoodModal: React.FC<ConfirmFoodModalProps> = ({
  data,
  onClose,
  onSave,
}) => {
  if (!data) return null;

  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  // Editable fields
  const [mealName, setMealName] = useState(data.meal_name);
  const [calories, setCalories] = useState(data.total_calories);
  const [protein, setProtein] = useState(data.total_protein);
  const [fat, setFat] = useState(data.total_fat);
  const [carbs, setCarbs] = useState(data.total_carbs);

  const totalWeight = data.items.reduce((acc, curr) => acc + (curr.portion_g || 0), 0);

  const handleConfirm = async () => {
    setIsSaving(true);
    try {
      await onSave({
        meal_name: mealName,
        total_calories: Number(calories),
        total_protein: Number(protein),
        total_fat: Number(fat),
        total_carbs: Number(carbs),
        advice: data.advice,
        items: data.items,
      });
      if (window.Telegram?.WebApp?.HapticFeedback) {
        window.Telegram.WebApp.HapticFeedback.notificationOccurred('success');
      }
      onClose();
    } catch (err) {
      alert('Ошибка при сохранении: ' + err);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title">Подтверждение блюда</div>
          <button className="modal-close-btn" onClick={onClose} disabled={isSaving}>
            <X size={18} />
          </button>
        </div>

        {!isEditing ? (
          <div>
            <div style={{ textAlign: 'center', marginBottom: '16px' }}>
              <div style={{ fontSize: '20px', fontWeight: 800, marginBottom: '6px' }}>{mealName}</div>
              <div style={{ fontSize: '36px', fontWeight: 800, color: 'var(--color-primary)' }}>
                {calories} ккал
              </div>
              <div style={{ fontSize: '13px', color: 'var(--color-text-muted)', marginTop: '4px' }}>
                Б {protein} г • Ж {fat} г • У {carbs} г
              </div>
            </div>

            <div
              style={{
                background: 'var(--color-card-bg)',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-md)',
                padding: '12px 14px',
                marginBottom: '16px',
                fontSize: '13px',
              }}
            >
              <div style={{ fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: '2px' }}>
                AI считает:
              </div>
              <div>примерная порция <b>~{Math.round(totalWeight)} г</b></div>
            </div>

            {/* Ingredients */}
            <div style={{ marginBottom: '18px' }}>
              <div style={{ fontSize: '13px', fontWeight: 700, marginBottom: '8px' }}>Ингредиенты:</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {data.items.map((it, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      fontSize: '13px',
                      padding: '6px 0',
                      borderBottom: '1px solid var(--color-border)',
                    }}
                  >
                    <span>{it.name} (~{Math.round(it.portion_g)} г)</span>
                    <span style={{ fontWeight: 600 }}>{it.calories} ккал</span>
                  </div>
                ))}
              </div>
            </div>

            {data.advice && (
              <div
                style={{
                  background: 'rgba(37, 99, 235, 0.08)',
                  border: '1px solid rgba(37, 99, 235, 0.2)',
                  borderRadius: 'var(--radius-md)',
                  padding: '12px 14px',
                  marginBottom: '18px',
                  fontSize: '13px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 700, color: 'var(--color-primary)', marginBottom: '2px' }}>
                  <Sparkles size={16} />
                  <span>Совет AI:</span>
                </div>
                <div>{data.advice}</div>
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <button className="btn btn-primary" onClick={handleConfirm} disabled={isSaving}>
                {isSaving ? <Loader2 className="animate-spin" size={18} /> : <Check size={18} />}
                <span>✓ Сохранить</span>
              </button>

              <div style={{ display: 'flex', gap: '10px' }}>
                <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => setIsEditing(true)}>
                  <Edit2 size={16} />
                  <span>Изменить</span>
                </button>
                <button className="btn btn-secondary" style={{ flex: 1 }} onClick={onClose}>
                  Отмена
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div>
            <div className="form-group">
              <label className="form-label">Название блюда:</label>
              <input
                className="form-input"
                type="text"
                value={mealName}
                onChange={(e) => setMealName(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Калории (ккал):</label>
              <input
                className="form-input"
                type="number"
                value={calories}
                onChange={(e) => setCalories(Number(e.target.value))}
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px', marginBottom: '16px' }}>
              <div>
                <label className="form-label">Белки (г):</label>
                <input
                  className="form-input"
                  type="number"
                  value={protein}
                  onChange={(e) => setProtein(Number(e.target.value))}
                />
              </div>
              <div>
                <label className="form-label">Жиры (г):</label>
                <input
                  className="form-input"
                  type="number"
                  value={fat}
                  onChange={(e) => setFat(Number(e.target.value))}
                />
              </div>
              <div>
                <label className="form-label">Угли (г):</label>
                <input
                  className="form-input"
                  type="number"
                  value={carbs}
                  onChange={(e) => setCarbs(Number(e.target.value))}
                />
              </div>
            </div>

            <button className="btn btn-primary" style={{ marginBottom: '10px' }} onClick={() => setIsEditing(false)}>
              Готово
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
