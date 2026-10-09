import React, { useState } from 'react';
import { X, Check, Loader2, Sparkles, AlertTriangle, CheckCircle, ArrowDownLeft, ArrowUpRight } from 'lucide-react';
import { ReceiptAnalysisResult, ExpenseParsedResult } from '../api/types';

interface ConfirmExpenseModalProps {
  data: (ReceiptAnalysisResult | ExpenseParsedResult) | null;
  onClose: () => void;
  onSave: (data: any) => Promise<void>;
}

export const ConfirmExpenseModal: React.FC<ConfirmExpenseModalProps> = ({
  data,
  onClose,
  onSave,
}) => {
  if (!data) return null;

  const isReceipt = 'total_amount' in data;
  const initialAmount = isReceipt ? data.total_amount : (data as ExpenseParsedResult).amount;

  const [entryType, setEntryType] = useState<'expense' | 'income'>(
    (data as any).entry_type || 'expense'
  );
  const [merchant, setMerchant] = useState(data.merchant || (entryType === 'income' ? 'Доход' : 'Покупка'));
  const [amount, setAmount] = useState(initialAmount || 0);
  const [currency, setCurrency] = useState(data.currency || '₸');
  const [category, setCategory] = useState(data.category || (entryType === 'income' ? 'salary' : 'food'));
  const [description, setDescription] = useState((data as any).description || '');
  const [isImpulsive, setIsImpulsive] = useState<boolean>((data as any).is_impulsive || false);
  const [aiAnalysis, setAiAnalysis] = useState<string>((data as any).ai_analysis || '');
  const [isSaving, setIsSaving] = useState(false);

  const expenseCategories = [
    { id: 'food', label: '🍔 Еда и продукты' },
    { id: 'transport', label: '🚕 Транспорт и бензин' },
    { id: 'shopping', label: '🛒 Покупки и одежда' },
    { id: 'entertainment', label: '🎮 Развлечения и кафе' },
    { id: 'utilities', label: '💡 Счета и коммуналка' },
    { id: 'other', label: '📦 Другое' },
  ];

  const incomeCategories = [
    { id: 'salary', label: '💰 Зарплата' },
    { id: 'business', label: '💼 Бизнес / Фриланс' },
    { id: 'gift', label: '🎁 Подарок' },
    { id: 'investments', label: '📈 Инвестиции' },
    { id: 'other_income', label: '💵 Другой доход' },
  ];

  const handleConfirm = async () => {
    setIsSaving(true);
    try {
      await onSave({
        merchant,
        amount: Number(amount),
        currency,
        category,
        entry_type: entryType,
        is_impulsive: isImpulsive,
        ai_analysis: aiAnalysis,
        description,
        items: data.items || [],
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
          <div className="modal-title">
            {entryType === 'income' ? 'Подтверждение дохода' : 'Подтверждение расхода'}
          </div>
          <button className="modal-close-btn" onClick={onClose} disabled={isSaving}>
            <X size={18} />
          </button>
        </div>

        {/* Toggle Expense vs Income */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
          <button
            type="button"
            className="btn"
            style={{
              flex: 1,
              padding: '8px',
              fontSize: '13px',
              fontWeight: 700,
              background: entryType === 'expense' ? 'var(--color-danger)' : 'rgba(239, 68, 68, 0.1)',
              color: entryType === 'expense' ? '#ffffff' : 'var(--color-danger)',
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
            }}
            onClick={() => {
              setEntryType('expense');
              if (category === 'salary') setCategory('food');
            }}
          >
            <ArrowDownLeft size={16} />
            <span>Расход</span>
          </button>
          <button
            type="button"
            className="btn"
            style={{
              flex: 1,
              padding: '8px',
              fontSize: '13px',
              fontWeight: 700,
              background: entryType === 'income' ? '#10b981' : 'rgba(16, 185, 129, 0.1)',
              color: entryType === 'income' ? '#ffffff' : '#10b981',
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
            }}
            onClick={() => {
              setEntryType('income');
              setIsImpulsive(false);
              setCategory('salary');
            }}
          >
            <ArrowUpRight size={16} />
            <span>Доход</span>
          </button>
        </div>

        {/* AI Analysis Verdict Banner */}
        {entryType === 'expense' && (
          <div
            style={{
              background: isImpulsive ? 'rgba(239, 68, 68, 0.1)' : 'rgba(16, 185, 129, 0.1)',
              border: `1px solid ${isImpulsive ? 'rgba(239, 68, 68, 0.3)' : 'rgba(16, 185, 129, 0.3)'}`,
              borderRadius: 'var(--radius-md)',
              padding: '12px 14px',
              marginBottom: '16px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
              {isImpulsive ? (
                <>
                  <AlertTriangle size={18} color="var(--color-danger)" />
                  <span style={{ fontWeight: 800, fontSize: '13px', color: 'var(--color-danger)' }}>
                    ⚠️ Импульсивная покупка! Не рекомендуется
                  </span>
                </>
              ) : (
                <>
                  <CheckCircle size={18} color="#10b981" />
                  <span style={{ fontWeight: 800, fontSize: '13px', color: '#10b981' }}>
                    ✅ Базовый необходимый расход
                  </span>
                </>
              )}
            </div>
            {aiAnalysis ? (
              <div style={{ fontSize: '12px', color: 'var(--color-text)', lineHeight: 1.4 }}>
                {aiAnalysis}
              </div>
            ) : (
              <div style={{ fontSize: '12px', color: 'var(--color-text-muted)' }}>
                {isImpulsive
                  ? 'Спонтанные покупки сладостей, снеков или развлечений могут нарушить недельный бюджет.'
                  : 'Трата соответствует категории плановых регулярных расходов.'}
              </div>
            )}
          </div>
        )}

        <div style={{ textAlign: 'center', marginBottom: '16px' }}>
          <div
            style={{
              fontSize: '32px',
              fontWeight: 800,
              color: entryType === 'income' ? '#10b981' : 'var(--color-primary)',
            }}
          >
            {entryType === 'income' ? '+' : '-'} {Number(amount).toLocaleString('ru-RU')} {currency}
          </div>
          <div style={{ fontSize: '15px', fontWeight: 600, color: 'var(--color-text-muted)' }}>
            {merchant}
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">
            {entryType === 'income' ? 'Источник дохода:' : 'Заведение / Магазин:'}
          </label>
          <input
            className="form-input"
            type="text"
            value={merchant}
            onChange={(e) => setMerchant(e.target.value)}
          />
        </div>

        <div className="form-group">
          <label className="form-label">Сумма:</label>
          <input
            className="form-input"
            type="number"
            value={amount}
            onChange={(e) => setAmount(Number(e.target.value))}
          />
        </div>

        <div className="form-group">
          <label className="form-label">Категория:</label>
          <select
            className="form-select"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            {(entryType === 'income' ? incomeCategories : expenseCategories).map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </div>

        {entryType === 'expense' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', margin: '14px 0' }}>
            <input
              type="checkbox"
              id="is_impulsive_check"
              checked={isImpulsive}
              onChange={(e) => setIsImpulsive(e.target.checked)}
              style={{ width: '18px', height: '18px' }}
            />
            <label htmlFor="is_impulsive_check" style={{ fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}>
              Отметить как импульсивную / спонтанную покупку
            </label>
          </div>
        )}

        {data.items && data.items.length > 0 && (
          <div style={{ marginBottom: '16px' }}>
            <div style={{ fontSize: '13px', fontWeight: 700, marginBottom: '6px' }}>Позиции в чеке:</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', maxHeight: '110px', overflowY: 'auto' }}>
              {data.items.map((it, idx) => (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    fontSize: '12px',
                    padding: '4px 0',
                    borderBottom: '1px solid var(--color-border)',
                  }}
                >
                  <span>{it.name}</span>
                  <span style={{ fontWeight: 600 }}>{it.price} {currency}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '16px' }}>
          <button className="btn btn-primary" onClick={handleConfirm} disabled={isSaving}>
            {isSaving ? <Loader2 className="animate-spin" size={18} /> : <Check size={18} />}
            <span>✓ Сохранить {entryType === 'income' ? 'доход' : 'расход'}</span>
          </button>
          <button className="btn btn-secondary" onClick={onClose} disabled={isSaving}>
            Отмена
          </button>
        </div>
      </div>
    </div>
  );
};
