import React, { useState, useRef } from 'react';
import { X, Camera, Image as ImageIcon, Edit3, Loader2 } from 'lucide-react';
import { api } from '../api/client';
import { ReceiptAnalysisResult, ExpenseParsedResult } from '../api/types';

interface AddExpenseModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAnalysisComplete: (result: ReceiptAnalysisResult | ExpenseParsedResult) => void;
}

export const AddExpenseModal: React.FC<AddExpenseModalProps> = ({
  isOpen,
  onClose,
  onAnalysisComplete,
}) => {
  const [mode, setMode] = useState<'options' | 'text'>('options');
  const [textInput, setTextInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  if (!isOpen) return null;

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsLoading(true);
    setError(null);
    try {
      const result = await api.analyzeReceiptPhoto(file);
      onAnalysisComplete(result);
      handleClose();
    } catch (err: any) {
      setError(err.message || 'Ошибка распознавания чека');
    } finally {
      setIsLoading(false);
    }
  };

  const handleTextSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!textInput.trim()) return;

    setIsLoading(true);
    setError(null);
    try {
      const result = await api.analyzeExpenseText(textInput);
      onAnalysisComplete(result);
      handleClose();
    } catch (err: any) {
      setError(err.message || 'Ошибка распознавания текста');
    } finally {
      setIsLoading(false);
    }
  };

  const handleClose = () => {
    setMode('options');
    setTextInput('');
    setError(null);
    setIsLoading(false);
    onClose();
  };

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title">Добавить расход</div>
          <button className="modal-close-btn" onClick={handleClose} disabled={isLoading}>
            <X size={18} />
          </button>
        </div>

        {error && (
          <div
            style={{
              background: '#fee2e2',
              color: '#b91c1c',
              padding: '10px 14px',
              borderRadius: 'var(--radius-sm)',
              marginBottom: '14px',
              fontSize: '13px',
            }}
          >
            {error}
          </div>
        )}

        {isLoading ? (
          <div style={{ textAlign: 'center', padding: '36px 16px' }}>
            <Loader2 className="animate-spin" size={36} color="var(--color-primary)" style={{ margin: '0 auto 16px auto', display: 'block' }} />
            <div style={{ fontWeight: 700, fontSize: '16px', marginBottom: '6px' }}>
              Gemini AI анализирует расход...
            </div>
            <div style={{ fontSize: '13px', color: 'var(--color-text-muted)' }}>
              Извлекаем сумму, заведение, категорию и позиции
            </div>
          </div>
        ) : mode === 'options' ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <input
              type="file"
              accept="image/*"
              capture="environment"
              ref={cameraInputRef}
              style={{ display: 'none' }}
              onChange={handleFileChange}
            />
            <input
              type="file"
              accept="image/*"
              ref={fileInputRef}
              style={{ display: 'none' }}
              onChange={handleFileChange}
            />

            <button
              className="btn btn-secondary"
              onClick={() => cameraInputRef.current?.click()}
            >
              <Camera size={20} color="var(--color-primary)" />
              <span>📷 Сфотографировать чек</span>
            </button>

            <button
              className="btn btn-secondary"
              onClick={() => fileInputRef.current?.click()}
            >
              <ImageIcon size={20} color="var(--color-primary)" />
              <span>🖼 Выбрать фото чека</span>
            </button>

            <button
              className="btn btn-secondary"
              onClick={() => setMode('text')}
            >
              <Edit3 size={20} color="var(--color-primary)" />
              <span>✏️ Ввести текстом (расход или доход)</span>
            </button>

            <button
              className="btn btn-secondary"
              onClick={() => {
                onAnalysisComplete({
                  merchant: '',
                  amount: 0,
                  currency: '₸',
                  category: 'food',
                  entry_type: 'expense',
                  is_impulsive: false,
                  items: [],
                });
                handleClose();
              }}
            >
              <span>➕ Ввести сумму вручную</span>
            </button>
          </div>
        ) : (
          <form onSubmit={handleTextSubmit}>
            <div className="form-group">
              <label className="form-label">Опишите операцию (расход или доход):</label>
              <textarea
                className="form-textarea"
                rows={3}
                placeholder="Например: кофе и десерт 2800 тг или зарплата 450000 тг"
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
                autoFocus
              />
              <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '4px' }}>
                AI сам распознает сумму, категорию, является ли покупка импульсивной или это доход
              </div>
            </div>
            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                type="button"
                className="btn btn-secondary"
                style={{ flex: 1 }}
                onClick={() => setMode('options')}
              >
                Назад
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                style={{ flex: 1 }}
                disabled={!textInput.trim()}
              >
                Распознать
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
