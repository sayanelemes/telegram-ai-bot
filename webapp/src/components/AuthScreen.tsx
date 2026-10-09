import React, { useState } from 'react';
import { KeyRound, ArrowRight, Send, Loader2, AlertCircle, RefreshCw } from 'lucide-react';
import { api } from '../api/client';

interface AuthScreenProps {
  onSuccess: () => void;
  errorMessage?: string | null;
}

export const AuthScreen: React.FC<AuthScreenProps> = ({ onSuccess, errorMessage }) => {
  const [code, setCode] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(errorMessage || null);

  const formatCodeInput = (val: string) => {
    const digits = val.replace(/\D/g, '').slice(0, 6);
    if (digits.length > 3) {
      return `${digits.slice(0, 3)} ${digits.slice(3)}`;
    }
    return digits;
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const formatted = formatCodeInput(e.target.value);
    setCode(formatted);
    if (error) setError(null);
  };

  const handleLogin = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const cleanDigits = code.replace(/\D/g, '');
    if (cleanDigits.length < 6) {
      setError('Введите 6 цифр кода');
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      await api.loginWithCode(cleanDigits);
      onSuccess();
    } catch (err: any) {
      setError(err.message || 'Неверный код. Запросите новый код в боте.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleOpenBot = () => {
    try {
      window.location.href = 'tg://resolve';
    } catch {
      window.open('https://t.me', '_blank');
    }
  };

  return (
    <div
      style={{
        minHeight: '85vh',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        padding: '24px 20px',
        textAlign: 'center',
      }}
    >
      {/* App Icon */}
      <img
        src="/apple-touch-icon.png"
        alt="App Icon"
        style={{
          width: '72px',
          height: '72px',
          borderRadius: '18px',
          boxShadow: '0 8px 24px rgba(0, 0, 0, 0.25)',
          marginBottom: '20px',
        }}
      />

      <h1 style={{ fontSize: '22px', fontWeight: 800, marginBottom: '6px' }}>
        Вход в НутриТрекер
      </h1>
      <p style={{ fontSize: '13px', color: 'var(--color-text-muted)', marginBottom: '24px', maxWidth: '300px' }}>
        Синхронизируйте приложение на iPhone с вашим Telegram-аккаунтом
      </p>

      {/* Code Input Form */}
      <form
        onSubmit={handleLogin}
        style={{
          width: '100%',
          maxWidth: '340px',
          background: 'var(--color-card-bg)',
          padding: '20px',
          borderRadius: '20px',
          border: '1px solid var(--color-border)',
          marginBottom: '20px',
          boxShadow: '0 4px 16px rgba(0,0,0,0.06)',
        }}
      >
        <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-text)', marginBottom: '10px' }}>
          Введите 6-значный код из бота:
        </div>

        <div style={{ position: 'relative', marginBottom: '14px' }}>
          <input
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            value={code}
            onChange={handleInputChange}
            placeholder="000 000"
            style={{
              width: '100%',
              fontSize: '28px',
              fontWeight: 800,
              letterSpacing: '6px',
              textAlign: 'center',
              padding: '12px 14px',
              borderRadius: '12px',
              border: '2px solid var(--color-primary)',
              background: 'var(--color-bg)',
              color: 'var(--color-text)',
              outline: 'none',
            }}
          />
        </div>

        {error && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              color: 'var(--color-danger)',
              fontSize: '12px',
              marginBottom: '12px',
              textAlign: 'left',
              justifyContent: 'center',
            }}
          >
            <AlertCircle size={15} style={{ flexShrink: 0 }} />
            <span>{error}</span>
          </div>
        )}

        <button
          type="submit"
          className="btn btn-primary"
          disabled={isLoading || code.replace(/\D/g, '').length < 6}
          style={{ width: '100%', padding: '14px', fontSize: '15px', fontWeight: 700 }}
        >
          {isLoading ? (
            <>
              <Loader2 className="animate-spin" size={18} />
              <span>Проверка кода...</span>
            </>
          ) : (
            <>
              <span>Войти в аккаунт</span>
              <ArrowRight size={18} />
            </>
          )}
        </button>
      </form>

      {/* Bot Instructions & Link */}
      <div
        style={{
          width: '100%',
          maxWidth: '340px',
          background: 'var(--color-bg)',
          padding: '16px',
          borderRadius: '16px',
          border: '1px solid var(--color-border)',
          fontSize: '12px',
          color: 'var(--color-text-muted)',
          lineHeight: 1.5,
          marginBottom: '16px',
        }}
      >
        <div style={{ fontWeight: 700, color: 'var(--color-text)', marginBottom: '6px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}>
          <KeyRound size={16} color="var(--color-primary)" />
          <span>Где взять код?</span>
        </div>
        <div>
          Откройте бота в Telegram и отправьте команду <b>/code</b> или <b>/login</b>. Бот мгновенно пришлёт ваш код.
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', width: '100%', maxWidth: '340px' }}>
        <button
          className="btn btn-secondary"
          onClick={handleOpenBot}
          style={{ width: '100%', gap: '8px', color: '#2563eb' }}
        >
          <Send size={16} />
          <span>Получить код в Telegram-боте</span>
        </button>

        <button
          onClick={onSuccess}
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--color-text-muted)',
            fontSize: '12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '6px',
            cursor: 'pointer',
            padding: '8px',
          }}
        >
          <RefreshCw size={13} />
          <span>Обновить страницу</span>
        </button>
      </div>
    </div>
  );
};
