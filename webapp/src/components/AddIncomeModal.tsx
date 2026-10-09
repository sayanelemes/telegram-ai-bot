import React, { useState } from 'react';
import { X, Check, Loader2, PlusCircle, ArrowUpRight } from 'lucide-react';
import { api } from '../api/client';

interface AddIncomeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onIncomeSaved: () => void;
}

export const AddIncomeModal: React.FC<AddIncomeModalProps> = ({
  isOpen,
  onClose,
  onIncomeSaved,
}) => {
  if (!isOpen) return null;

  const [merchant, setMerchant] = useState('');
  const [amount, setAmount] = useState<number | ''>('');
  const [currency] = useState('₸');
  const [category, setCategory] = useState('salary');
  const [description, setDescription] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  const incomeCategories = [
    { id: 'salary', label: '💰 Зарплата' },
    { id: 'business', label: '💼 Бизнес / Фриланс' },
    { id: 'gift', label: '🎁 Подарок' },
    { id: 'investments', label: '📈 Инвестиции / Дивиденды' },
    { id: 'other_income', label: '💵 Другой доход' },
  ];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!amount || Number(amount) <= 0) {
      alert('Укажите корректную сумму дохода');
      return;
    }

    setIsSaving(true);
    try {
      await api.saveExpense({
        merchant: merchant.trim() || 'Доход',
        amount: Number(amount),
        currency,
        category,
        entry_type: 'income',
        is_impulsive: false,
        ai_analysis: '💰 Зачислен доход',
        description: description.trim() || undefined,
        items: [],
      });

      if (window.Telegram?.WebApp?.HapticFeedback) {
        window.Telegram.WebApp.HapticFeedback.notificationOccurred('success');
      }

      onIncomeSaved();
      onClose();
    } catch (err) {
      alert('Ошибка при сохранении дохода: ' + err);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title" style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#10b981' }}>
            <ArrowUpRight size={22} color="#10b981" />
            <span>Добавить доход</span>
          </div>
          <button className="modal-close-btn" onClick={onClose} disabled={isSaving}>
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Сумма дохода (₸):</label>
            <input
              className="form-input"
              type="number"
              min="1"
              step="100"
              placeholder="Например: 250000"
              value={amount}
              onChange={(e) => setAmount(e.target.value === '' ? '' : Number(e.target.value))}
              autoFocus
              required
            />
            <div style={{ display: 'flex', gap: '6px', marginTop: '6px' }}>
              {[50000, 150000, 300000, 500000].map((preset) => (
                <button
                  type="button"
                  key={preset}
                  className="btn btn-secondary"
                  style={{ padding: '4px 6px', fontSize: '11px', flex: 1 }}
                  onClick={() => setAmount(preset)}
                >
                  +{preset.toLocaleString('ru-RU')}
                </button>
              ))}
            </div>
          </div>

          <div className="form-group" style={{ marginTop: '14px' }}>
            <label className="form-label">Источник дохода / Категория:</label>
            <select
              className="form-select"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              {incomeCategories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>

          <div className="form-group" style={{ marginTop: '14px' }}>
            <label className="form-label">От кого / Название (необязательно):</label>
            <input
              className="form-input"
              type="text"
              placeholder="Например: Основная работа, Аванс, Клиент"
              value={merchant}
              onChange={(e) => setMerchant(e.target.value)}
            />
          </div>

          <div className="form-group" style={{ marginTop: '14px' }}>
            <label className="form-label">Комментарий:</label>
            <input
              className="form-input"
              type="text"
              placeholder="Например: Выплата за проект"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '22px' }}>
            <button
              type="submit"
              className="btn btn-primary"
              style={{ background: '#10b981', borderColor: '#10b981' }}
              disabled={isSaving || !amount}
            >
              {isSaving ? <Loader2 className="animate-spin" size={18} /> : <Check size={18} />}
              <span>✓ Сохранить доход</span>
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onClose}
              disabled={isSaving}
            >
              Отмена
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
