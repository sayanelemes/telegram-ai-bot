import React, { useState } from 'react';
import { X, Clock, Globe } from 'lucide-react';
import { ReminderItem } from '../api/types';
import { api } from '../api/client';

interface RemindersModalProps {
  isOpen: boolean;
  onClose: () => void;
  reminders: ReminderItem[];
  timezone: string;
  onRefresh: () => void;
}

export const RemindersModal: React.FC<RemindersModalProps> = ({
  isOpen,
  onClose,
  reminders,
  timezone,
  onRefresh,
}) => {
  if (!isOpen) return null;

  const [currentTimezone, setCurrentTimezone] = useState(timezone);
  const [editingType, setEditingType] = useState<string | null>(null);
  const [newTime, setNewTime] = useState('');

  const timezones = [
    { label: 'Алматы (UTC+5)', val: 'Asia/Almaty' },
    { label: 'Москва (UTC+3)', val: 'Europe/Moscow' },
    { label: 'Ташкент (UTC+5)', val: 'Asia/Tashkent' },
    { label: 'Бишкек (UTC+6)', val: 'Asia/Bishkek' },
    { label: 'Тбилиси (UTC+4)', val: 'Asia/Tbilisi' },
    { label: 'UTC (UTC+0)', val: 'UTC' },
  ];

  const handleToggle = async (r: ReminderItem) => {
    try {
      await api.updateReminder(r.reminder_type, { is_enabled: !r.is_enabled });
      if (window.Telegram?.WebApp?.HapticFeedback) {
        window.Telegram.WebApp.HapticFeedback.selectionChanged();
      }
      onRefresh();
    } catch (err) {
      alert('Ошибка при переключении: ' + err);
    }
  };

  const handleTimeSave = async (reminderType: string) => {
    if (!newTime) return;
    try {
      if (reminderType === 'water') {
        await api.updateReminder(reminderType, { interval_hours: Number(newTime) });
      } else {
        await api.updateReminder(reminderType, { time_str: newTime });
      }
      setEditingType(null);
      setNewTime('');
      onRefresh();
    } catch (err) {
      alert('Ошибка при изменении времени: ' + err);
    }
  };

  const handleTimezoneChange = async (tz: string) => {
    try {
      setCurrentTimezone(tz);
      await api.updateTimezone(tz);
      if (window.Telegram?.WebApp?.HapticFeedback) {
        window.Telegram.WebApp.HapticFeedback.notificationOccurred('success');
      }
      onRefresh();
    } catch (err) {
      alert('Ошибка при смене таймзоны: ' + err);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title">Напоминания</div>
          <button className="modal-close-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {/* Timezone */}
        <div className="card" style={{ marginBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
            <Globe size={18} color="var(--color-primary)" />
            <span style={{ fontSize: '14px', fontWeight: 700 }}>Часовой пояс</span>
          </div>
          <select
            className="form-select"
            value={currentTimezone}
            onChange={(e) => handleTimezoneChange(e.target.value)}
          >
            {timezones.map((tz) => (
              <option key={tz.val} value={tz.val}>
                {tz.label}
              </option>
            ))}
          </select>
        </div>

        {/* Reminders list */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {reminders.map((r) => {
            const isEditingThis = editingType === r.reminder_type;
            const displayTime = r.reminder_type === 'water' ? `каждые ${r.interval_hours} ч` : r.time_str;

            return (
              <div
                key={r.reminder_type}
                className="card"
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '12px 14px',
                  marginBottom: 0,
                }}
              >
                <div>
                  <div style={{ fontWeight: 700, fontSize: '15px' }}>{r.title}</div>
                  <div
                    style={{
                      fontSize: '13px',
                      color: 'var(--color-text-muted)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      cursor: 'pointer',
                    }}
                    onClick={() => {
                      setEditingType(r.reminder_type);
                      setNewTime(r.reminder_type === 'water' ? String(r.interval_hours) : r.time_str);
                    }}
                  >
                    <Clock size={12} />
                    <span>{displayTime} (изменить)</span>
                  </div>

                  {isEditingThis && (
                    <div style={{ marginTop: '8px', display: 'flex', gap: '6px' }}>
                      <input
                        className="form-input"
                        style={{ width: '90px', padding: '6px' }}
                        type={r.reminder_type === 'water' ? 'number' : 'text'}
                        placeholder={r.reminder_type === 'water' ? '2' : '09:00'}
                        value={newTime}
                        onChange={(e) => setNewTime(e.target.value)}
                      />
                      <button
                        className="btn btn-primary"
                        style={{ padding: '6px 10px', fontSize: '12px' }}
                        onClick={() => handleTimeSave(r.reminder_type)}
                      >
                        OK
                      </button>
                    </div>
                  )}
                </div>

                <button
                  style={{
                    padding: '6px 14px',
                    borderRadius: 'var(--radius-full)',
                    fontSize: '13px',
                    fontWeight: 700,
                    border: 'none',
                    cursor: 'pointer',
                    background: r.is_enabled ? 'var(--color-primary)' : 'var(--color-border)',
                    color: r.is_enabled ? 'var(--color-primary-text)' : 'var(--color-text-muted)',
                    transition: 'background 0.2s ease',
                  }}
                  onClick={() => handleToggle(r)}
                >
                  {r.is_enabled ? 'ВКЛ' : 'ВЫКЛ'}
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
