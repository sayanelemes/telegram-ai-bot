import React, { useState } from 'react';
import { X, Share2, PlusSquare, Check, Copy, ExternalLink, Smartphone, Sparkles, Compass } from 'lucide-react';

interface AddToHomeScreenModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const AddToHomeScreenModal: React.FC<AddToHomeScreenModalProps> = ({ isOpen, onClose }) => {
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState<'safari' | 'telegram'>('safari');
  const webAppUrl = window.location.href;

  if (!isOpen) return null;

  const isTelegram = !!(window as any).Telegram?.WebApp?.initData;
  const hasTelegramA2HS = typeof (window as any).Telegram?.WebApp?.addToHomeScreen === 'function';

  const handleTelegramAdd = () => {
    try {
      (window as any).Telegram?.WebApp?.addToHomeScreen();
    } catch (e) {
      console.error(e);
    }
  };

  const handleOpenInSafari = () => {
    try {
      if ((window as any).Telegram?.WebApp?.openLink) {
        (window as any).Telegram.WebApp.openLink(webAppUrl);
      } else {
        window.open(webAppUrl, '_blank');
      }
    } catch {
      window.location.href = webAppUrl;
    }
  };

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(webAppUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      // fallback
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content"
        onClick={(e) => e.stopPropagation()}
        style={{
          maxHeight: '90vh',
          overflowY: 'auto',
          borderRadius: '24px 24px 0 0',
          paddingBottom: 'calc(24px + env(safe-area-inset-bottom, 16px))',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '38px',
                height: '38px',
                borderRadius: '12px',
                background: 'rgba(59, 130, 246, 0.15)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#3b82f6',
              }}
            >
              <Smartphone size={22} />
            </div>
            <div>
              <div style={{ fontSize: '17px', fontWeight: 700 }}>Установка на рабочий стол iPhone</div>
              <div style={{ fontSize: '12px', color: 'var(--color-text-muted)' }}>Запуск в 1 касание во весь экран</div>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'var(--color-bg)',
              border: 'none',
              borderRadius: '50%',
              width: '32px',
              height: '32px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              color: 'var(--color-text-muted)',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* App Icon preview */}
        <div
          style={{
            background: 'var(--color-bg)',
            border: '1px solid var(--color-border)',
            borderRadius: '16px',
            padding: '14px 16px',
            display: 'flex',
            alignItems: 'center',
            gap: '14px',
            marginBottom: '16px',
          }}
        >
          <img
            src="/apple-touch-icon.png"
            alt="App Icon"
            style={{
              width: '54px',
              height: '54px',
              borderRadius: '12px',
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.2)',
            }}
          />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: '15px', fontWeight: 700 }}>НутриТрекер & Финансы</div>
            <div style={{ fontSize: '12px', color: '#10b981', fontWeight: 600 }}>
              ✓ Полноэкранный режим PWA (без рамок Safari)
            </div>
          </div>
        </div>

        {/* Method Switcher Tabs */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            background: 'var(--color-bg)',
            padding: '4px',
            borderRadius: '12px',
            border: '1px solid var(--color-border)',
            marginBottom: '16px',
            gap: '4px',
          }}
        >
          <button
            style={{
              padding: '8px 12px',
              borderRadius: '8px',
              border: 'none',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
              background: activeTab === 'safari' ? 'var(--color-card-bg)' : 'transparent',
              color: activeTab === 'safari' ? 'var(--color-primary)' : 'var(--color-text-muted)',
              boxShadow: activeTab === 'safari' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
              transition: 'all 0.2s',
            }}
            onClick={() => setActiveTab('safari')}
          >
            🍎 Через Safari (PWA)
          </button>
          <button
            style={{
              padding: '8px 12px',
              borderRadius: '8px',
              border: 'none',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
              background: activeTab === 'telegram' ? 'var(--color-card-bg)' : 'transparent',
              color: activeTab === 'telegram' ? 'var(--color-primary)' : 'var(--color-text-muted)',
              boxShadow: activeTab === 'telegram' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
              transition: 'all 0.2s',
            }}
            onClick={() => setActiveTab('telegram')}
          >
            ✈️ В Telegram
          </button>
        </div>

        {activeTab === 'safari' ? (
          <div>
            <div style={{ fontSize: '13px', color: 'var(--color-text-muted)', marginBottom: '12px', lineHeight: 1.4 }}>
              Чтобы приложение открывалось <b>как полноценная программа (без адресной строки Safari)</b>, установите его через Safari:
            </div>

            {/* Quick Open in Safari button */}
            {isTelegram && (
              <button
                className="btn btn-primary"
                style={{ marginBottom: '14px', gap: '8px', background: '#2563eb' }}
                onClick={handleOpenInSafari}
              >
                <Compass size={18} />
                <span>1. Открыть ссылку в Safari</span>
              </button>
            )}

            {/* Steps */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '16px' }}>
              <div
                style={{
                  display: 'flex',
                  gap: '12px',
                  alignItems: 'flex-start',
                  background: 'var(--color-bg)',
                  padding: '12px',
                  borderRadius: '12px',
                  border: '1px solid var(--color-border)',
                }}
              >
                <div
                  style={{
                    width: '32px',
                    height: '32px',
                    borderRadius: '8px',
                    background: 'rgba(59, 130, 246, 0.12)',
                    color: '#3b82f6',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <Share2 size={18} />
                </div>
                <div style={{ fontSize: '13px' }}>
                  <div style={{ fontWeight: 700 }}>2. Нажмите «Поделиться» ⎋</div>
                  <div style={{ color: 'var(--color-text-muted)' }}>
                    В нижней панели Safari нажмите значок квадрата со стрелкой вверх.
                  </div>
                </div>
              </div>

              <div
                style={{
                  display: 'flex',
                  gap: '12px',
                  alignItems: 'flex-start',
                  background: 'var(--color-bg)',
                  padding: '12px',
                  borderRadius: '12px',
                  border: '1px solid var(--color-border)',
                }}
              >
                <div
                  style={{
                    width: '32px',
                    height: '32px',
                    borderRadius: '8px',
                    background: 'rgba(16, 185, 129, 0.12)',
                    color: '#10b981',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <PlusSquare size={18} />
                </div>
                <div style={{ fontSize: '13px' }}>
                  <div style={{ fontWeight: 700 }}>3. Выберите «На экран "Домой"» ⊞</div>
                  <div style={{ color: 'var(--color-text-muted)' }}>
                    Прокрутите меню действий вниз до пункта «На экран "Домой"».
                  </div>
                </div>
              </div>

              <div
                style={{
                  display: 'flex',
                  gap: '12px',
                  alignItems: 'flex-start',
                  background: 'var(--color-bg)',
                  padding: '12px',
                  borderRadius: '12px',
                  border: '1px solid var(--color-border)',
                }}
              >
                <div
                  style={{
                    width: '32px',
                    height: '32px',
                    borderRadius: '8px',
                    background: 'rgba(245, 158, 11, 0.12)',
                    color: '#f59e0b',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <Check size={18} />
                </div>
                <div style={{ fontSize: '13px' }}>
                  <div style={{ fontWeight: 700 }}>4. Нажмите «Добавить» вверху</div>
                  <div style={{ color: 'var(--color-text-muted)' }}>
                    Иконка появится на рабочем столе iPhone и будет запускаться как нативное приложение!
                  </div>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div>
            <div style={{ fontSize: '13px', color: 'var(--color-text-muted)', marginBottom: '14px', lineHeight: 1.4 }}>
              Telegram поддерживает создание прямого ярлыка Web App:
            </div>

            {hasTelegramA2HS ? (
              <button
                className="btn btn-primary"
                style={{ marginBottom: '14px', gap: '8px', background: '#0284c7' }}
                onClick={handleTelegramAdd}
              >
                <Sparkles size={18} />
                <span>Добавить ярлык через Telegram</span>
              </button>
            ) : (
              <div
                style={{
                  background: 'var(--color-bg)',
                  padding: '14px',
                  borderRadius: '12px',
                  border: '1px solid var(--color-border)',
                  marginBottom: '16px',
                  fontSize: '13px',
                }}
              >
                <div style={{ fontWeight: 700, marginBottom: '6px' }}>В правом верхнем углу Telegram:</div>
                <ol style={{ paddingLeft: '20px', lineHeight: 1.6, color: 'var(--color-text-muted)' }}>
                  <li>Нажмите на <b>три точки (•••)</b> в правом верхнем углу окна Mini App.</li>
                  <li>Выберите пункт <b>«Добавить на главный экран»</b>.</li>
                </ol>
              </div>
            )}
          </div>
        )}

        {/* Action Buttons */}
        <div style={{ display: 'flex', gap: '10px', marginTop: '10px' }}>
          <button
            className="btn btn-secondary"
            style={{ flex: 1, gap: '6px' }}
            onClick={handleCopyLink}
          >
            {copied ? <Check size={16} color="#10b981" /> : <Copy size={16} />}
            <span>{copied ? 'Скопировано!' : 'Скопировать ссылку'}</span>
          </button>
          <button
            className="btn btn-primary"
            style={{ flex: 1 }}
            onClick={onClose}
          >
            Закрыть
          </button>
        </div>
      </div>
    </div>
  );
};
