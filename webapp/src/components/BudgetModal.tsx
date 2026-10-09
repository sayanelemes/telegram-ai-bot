import React, { useState } from 'react';
import { X, Check, Loader2, PiggyBank } from 'lucide-react';
import { BudgetSummary } from '../api/types';

interface BudgetModalProps {
  isOpen: boolean;
  budget: BudgetSummary | undefined;
  onClose: () => void;
  onSave: (weekly: number, monthly: number) => Promise<void>;
}

export const BudgetModal: React.FC<BudgetModalProps> = ({
  isOpen,
  budget,
  onClose,
  onSave,
}) => {
  if (!isOpen) return null;

  const [weeklyBudget, setWeeklyBudget] = useState(budget?.weekly_budget || 0);
  const [monthlyBudget, setMonthlyBudget] = useState(budget?.monthly_budget || 0);
  const [isSaving, setIsSaving] = useState(false);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      await onSave(Number(weeklyBudget), Number(monthlyBudget));
      if (window.Telegram?.WebApp?.HapticFeedback) {
        window.Telegram.WebApp.HapticFeedback.notificationOccurred('success');
      }
      onClose();
    } catch (err) {
      alert('Ошибка при сохранении бюджета: ' + err);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <PiggyBank size={20} color="var(--color-primary)" />
            <span>Настройка бюджетов</span>
          </div>
          <button className="modal-close-btn" onClick={onClose} disabled={isSaving}>
            <X size={18} />
          </button>
        </div>

        <p style={{ fontSize: '13px', color: 'var(--color-text-muted)', marginBottom: '18px' }}>
          Задайте лимиты расходов на неделю и месяц. Приложение будет предупреждать о перерасходе.
        </p>

        <form onSubmit={handleSave}>
          <div className="form-group">
            <label className="form-label">Недельный бюджет (₸):</label>
            <input
              className="form-input"
              type="number"
              min="0"
              step="500"
              placeholder="Например: 35000"
              value={weeklyBudget || ''}
              onChange={(e) => setWeeklyBudget(Number(e.target.value))}
            />
            <div style={{ display: 'flex', gap: '6px', marginTop: '6px' }}>
              {[25000, 35000, 50000].map((preset) => (
                <button
                  type="button"
                  key={preset}
                  className="btn btn-secondary"
                  style={{ padding: '4px 8px', fontSize: '11px', flex: 1 }}
                  onClick={() => setWeeklyBudget(preset)}
                >
                  {preset.toLocaleString('ru-RU')} ₸
                </button>
              ))}
            </div>
          </div>

          <div className="form-group" style={{ marginTop: '16px' }}>
            <label className="form-label">Месячный бюджет (₸):</label>
            <input
              className="form-input"
              type="number"
              min="0"
              step="1000"
              placeholder="Например: 150000"
              value={monthlyBudget || ''}
              onChange={(e) => setMonthlyBudget(Number(e.target.value))}
            />
            <div style={{ display: 'flex', gap: '6px', marginTop: '6px' }}>
              {[100000, 150000, 250000].map((preset) => (
                <button
                  type="button"
                  key={preset}
                  className="btn btn-secondary"
                  style={{ padding: '4px 8px', fontSize: '11px', flex: 1 }}
                  onClick={() => setMonthlyBudget(preset)}
                >
                  {preset.toLocaleString('ru-RU')} ₸
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '24px' }}>
            <button className="btn btn-primary" type="submit" disabled={isSaving}>
              {isSaving ? <Loader2 className="animate-spin" size={18} /> : <Check size={18} />}
              <span>Сохранить бюджет</span>
            </button>
            <button className="btn btn-secondary" type="button" onClick={onClose} disabled={isSaving}>
              Отмена
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
