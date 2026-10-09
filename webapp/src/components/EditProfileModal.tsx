import React, { useState } from 'react';
import { X, Check, Loader2 } from 'lucide-react';
import { ProfileData } from '../api/types';

interface EditProfileModalProps {
  profile: ProfileData;
  isOpen: boolean;
  onClose: () => void;
  onSave: (data: any) => Promise<void>;
}

export const EditProfileModal: React.FC<EditProfileModalProps> = ({
  profile,
  isOpen,
  onClose,
  onSave,
}) => {
  if (!isOpen) return null;

  const [gender, setGender] = useState(profile.gender || 'male');
  const [age, setAge] = useState(profile.age || 25);
  const [heightCm, setHeightCm] = useState(profile.height_cm || 178);
  const [weightKg, setWeightKg] = useState(profile.weight_kg || 70);
  const [activity, setActivity] = useState(profile.activity_level || 'moderate');
  const [goal, setGoal] = useState(profile.goal || 'maintain');
  const [isSaving, setIsSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      await onSave({
        gender,
        age: Number(age),
        height_cm: Number(heightCm),
        weight_kg: Number(weightKg),
        activity_level: activity,
        goal,
      });
      if (window.Telegram?.WebApp?.HapticFeedback) {
        window.Telegram.WebApp.HapticFeedback.notificationOccurred('success');
      }
      onClose();
    } catch (err: any) {
      alert('Ошибка при обновлении профиля: ' + err.message);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title">Редактировать параметры</div>
          <button className="modal-close-btn" onClick={onClose} disabled={isSaving}>
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Пол:</label>
            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                type="button"
                className={`btn ${gender === 'male' ? 'btn-primary' : 'btn-secondary'}`}
                style={{ flex: 1 }}
                onClick={() => setGender('male')}
              >
                👨 Мужской
              </button>
              <button
                type="button"
                className={`btn ${gender === 'female' ? 'btn-primary' : 'btn-secondary'}`}
                style={{ flex: 1 }}
                onClick={() => setGender('female')}
              >
                👩 Женский
              </button>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px' }}>
            <div className="form-group">
              <label className="form-label">Возраст:</label>
              <input
                className="form-input"
                type="number"
                value={age}
                onChange={(e) => setAge(Number(e.target.value))}
                min={14}
                max={100}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Рост (см):</label>
              <input
                className="form-input"
                type="number"
                value={heightCm}
                onChange={(e) => setHeightCm(Number(e.target.value))}
                min={100}
                max={250}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Вес (кг):</label>
              <input
                className="form-input"
                type="number"
                step="0.5"
                value={weightKg}
                onChange={(e) => setWeightKg(Number(e.target.value))}
                min={30}
                max={300}
                required
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Уровень активности:</label>
            <select
              className="form-select"
              value={activity}
              onChange={(e) => setActivity(e.target.value)}
            >
              <option value="sedentary">🛋 Минимальная (сидячий образ)</option>
              <option value="light">🚶 Лёгкая (1-3 тренировки/нед)</option>
              <option value="moderate">🏃 Средняя (3-5 тренировок/нед)</option>
              <option value="high">🏋️ Высокая (6-7 тренировок/нед)</option>
              <option value="very_high">🔥 Очень высокая (тяжелый спорт/труд)</option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Основная цель:</label>
            <select
              className="form-select"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
            >
              <option value="loss">📉 Похудение (-20% калорий)</option>
              <option value="maintain">⚖️ Поддержание веса</option>
              <option value="gain">📈 Набор мышечной массы (+15%)</option>
            </select>
          </div>

          <button type="submit" className="btn btn-primary" style={{ marginTop: '16px' }} disabled={isSaving}>
            {isSaving ? <Loader2 className="animate-spin" size={18} /> : <Check size={18} />}
            <span>Пересчитать и сохранить</span>
          </button>
        </form>
      </div>
    </div>
  );
};
