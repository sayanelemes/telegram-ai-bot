import React, { useState, useEffect } from 'react';
import { Edit2, Bell, Flame, Activity, Loader2, Smartphone, Sun, Moon, Laptop, Palette } from 'lucide-react';
import { ProfileData, ReminderItem } from '../api/types';
import { api } from '../api/client';
import { EditProfileModal } from '../components/EditProfileModal';
import { RemindersModal } from '../components/RemindersModal';
import { AddToHomeScreenModal } from '../components/AddToHomeScreenModal';
import { ThemeToggle } from '../components/ThemeToggle';
import { useTheme } from '../context/ThemeContext';

interface ProfilePageProps {
  onProfileUpdated?: () => void;
}

export const ProfilePage: React.FC<ProfilePageProps> = ({ onProfileUpdated }) => {
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [reminders, setReminders] = useState<ReminderItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const [isEditProfileOpen, setIsEditProfileOpen] = useState(false);
  const [isRemindersOpen, setIsRemindersOpen] = useState(false);
  const [isA2HSOpen, setIsA2HSOpen] = useState(false);
  const { theme, setTheme } = useTheme();

  useEffect(() => {
    loadAll();
  }, []);

  const loadAll = async () => {
    setIsLoading(true);
    try {
      const [profData, remData] = await Promise.all([
        api.getProfile(),
        api.getReminders(),
      ]);
      setProfile(profData);
      setReminders(remData);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSaveProfile = async (saveData: any) => {
    const updated = await api.updateProfile(saveData);
    setProfile(updated);
    if (onProfileUpdated) onProfileUpdated();
  };

  const getGoalLabel = (goal?: string) => {
    if (goal === 'loss') return '📉 Похудение';
    if (goal === 'gain') return '📈 Набор веса';
    return '⚖️ Поддержание веса';
  };

  const getActivityLabel = (act?: string) => {
    if (act === 'sedentary') return '🛋 Минимальная';
    if (act === 'light') return '🚶 Лёгкая';
    if (act === 'moderate') return '🏃 Средняя';
    if (act === 'high') return '🏋️ Высокая';
    if (act === 'very_high') return '🔥 Очень высокая';
    return '🏃 Средняя';
  };

  return (
    <div>
      <div className="section-title" style={{ fontSize: '20px', marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>Профиль</span>
        <ThemeToggle />
      </div>

      {isLoading || !profile ? (
        <div style={{ textAlign: 'center', padding: '40px' }}>
          <Loader2 className="animate-spin" size={32} color="var(--color-primary)" style={{ margin: '0 auto' }} />
        </div>
      ) : (
        <div>
          {/* Main User Card */}
          <div className="card" style={{ marginBottom: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '14px' }}>
              <div>
                <div style={{ fontSize: '18px', fontWeight: 800 }}>👤 Параметры тела</div>
                <div style={{ fontSize: '12px', color: 'var(--color-text-muted)' }}>
                  {profile.gender === 'female' ? 'Женщина' : 'Мужчина'}
                </div>
              </div>
              <button
                className="btn btn-secondary"
                style={{ width: 'auto', padding: '6px 12px', fontSize: '13px' }}
                onClick={() => setIsEditProfileOpen(true)}
              >
                <Edit2 size={14} />
                <span>Изменить</span>
              </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px', textAlign: 'center' }}>
              <div style={{ background: 'var(--color-bg)', padding: '10px', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>Возраст</div>
                <div style={{ fontSize: '16px', fontWeight: 800 }}>{profile.age || '-'} лет</div>
              </div>
              <div style={{ background: 'var(--color-bg)', padding: '10px', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>Рост</div>
                <div style={{ fontSize: '16px', fontWeight: 800 }}>{profile.height_cm || '-'} см</div>
              </div>
              <div style={{ background: 'var(--color-bg)', padding: '10px', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>Вес</div>
                <div style={{ fontSize: '16px', fontWeight: 800 }}>{profile.weight_kg || '-'} кг</div>
              </div>
            </div>

            <div style={{ marginTop: '12px', display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
              <span style={{ color: 'var(--color-text-muted)' }}>Активность:</span>
              <span style={{ fontWeight: 600 }}>{getActivityLabel(profile.activity_level)}</span>
            </div>
            <div style={{ marginTop: '4px', display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
              <span style={{ color: 'var(--color-text-muted)' }}>Цель:</span>
              <span style={{ fontWeight: 600 }}>{getGoalLabel(profile.goal)}</span>
            </div>
          </div>

          {/* Calorie Goals & Metabolism */}
          <div className="card" style={{ marginBottom: '16px' }}>
            <div style={{ fontSize: '16px', fontWeight: 700, marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Flame size={18} color="var(--color-primary)" />
              <span>Суточная норма (Mifflin-St Jeor)</span>
            </div>

            <div style={{ textAlign: 'center', padding: '12px 0', borderBottom: '1px solid var(--color-border)', marginBottom: '12px' }}>
              <div style={{ fontSize: '12px', color: 'var(--color-text-muted)' }}>Целевая калорийность</div>
              <div style={{ fontSize: '32px', fontWeight: 800, color: 'var(--color-primary)' }}>
                {profile.target_calories?.toLocaleString('ru-RU') || '-'} ккал
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px', textAlign: 'center' }}>
              <div>
                <div style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>Белки</div>
                <div style={{ fontSize: '15px', fontWeight: 700, color: 'var(--color-protein)' }}>
                  {profile.target_protein_g || '-'} г
                </div>
              </div>
              <div>
                <div style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>Жиры</div>
                <div style={{ fontSize: '15px', fontWeight: 700, color: 'var(--color-fat)' }}>
                  {profile.target_fat_g || '-'} г
                </div>
              </div>
              <div>
                <div style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>Углеводы</div>
                <div style={{ fontSize: '15px', fontWeight: 700, color: 'var(--color-carbs)' }}>
                  {profile.target_carbs_g || '-'} г
                </div>
              </div>
            </div>

            <div style={{ marginTop: '14px', paddingTop: '10px', borderTop: '1px solid var(--color-border)', fontSize: '12px', color: 'var(--color-text-muted)', display: 'flex', justifyContent: 'space-between' }}>
              <span>Базовый метаболизм (BMR): <b>{profile.bmr} ккал</b></span>
              <span>Расход (TDEE): <b>{profile.tdee} ккал</b></span>
            </div>
          </div>

          {/* Theme Selector Card */}
          <div className="card" style={{ marginBottom: '14px' }}>
            <div style={{ fontSize: '15px', fontWeight: 700, marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Palette size={18} color="var(--color-primary)" />
              <span>Тема оформления</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' }}>
              <button
                onClick={() => setTheme('light')}
                style={{
                  padding: '10px 6px',
                  borderRadius: '10px',
                  border: theme === 'light' ? '2px solid var(--color-primary)' : '1px solid var(--color-border)',
                  background: theme === 'light' ? 'rgba(37, 99, 235, 0.1)' : 'var(--color-bg)',
                  color: theme === 'light' ? 'var(--color-primary)' : 'var(--color-text)',
                  fontWeight: theme === 'light' ? 700 : 500,
                  fontSize: '13px',
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '4px',
                  transition: 'all 0.15s ease',
                }}
              >
                <Sun size={18} color={theme === 'light' ? 'var(--color-primary)' : 'var(--color-text-muted)'} />
                <span>Светлая</span>
              </button>

              <button
                onClick={() => setTheme('dark')}
                style={{
                  padding: '10px 6px',
                  borderRadius: '10px',
                  border: theme === 'dark' ? '2px solid var(--color-primary)' : '1px solid var(--color-border)',
                  background: theme === 'dark' ? 'rgba(59, 130, 246, 0.15)' : 'var(--color-bg)',
                  color: theme === 'dark' ? 'var(--color-primary)' : 'var(--color-text)',
                  fontWeight: theme === 'dark' ? 700 : 500,
                  fontSize: '13px',
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '4px',
                  transition: 'all 0.15s ease',
                }}
              >
                <Moon size={18} color={theme === 'dark' ? 'var(--color-primary)' : 'var(--color-text-muted)'} />
                <span>Тёмная</span>
              </button>

              <button
                onClick={() => setTheme('auto')}
                style={{
                  padding: '10px 6px',
                  borderRadius: '10px',
                  border: theme === 'auto' ? '2px solid var(--color-primary)' : '1px solid var(--color-border)',
                  background: theme === 'auto' ? 'rgba(37, 99, 235, 0.1)' : 'var(--color-bg)',
                  color: theme === 'auto' ? 'var(--color-primary)' : 'var(--color-text)',
                  fontWeight: theme === 'auto' ? 700 : 500,
                  fontSize: '13px',
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '4px',
                  transition: 'all 0.15s ease',
                }}
              >
                <Laptop size={18} color={theme === 'auto' ? 'var(--color-primary)' : 'var(--color-text-muted)'} />
                <span>Системная</span>
              </button>
            </div>
          </div>

          {/* Reminders Button */}
          <button
            className="btn btn-secondary"
            style={{ marginBottom: '10px' }}
            onClick={() => setIsRemindersOpen(true)}
          >
            <Bell size={18} color="var(--color-primary)" />
            <span>Настройки напоминаний ({reminders.filter((r) => r.is_enabled).length} вкл)</span>
          </button>

          {/* Add to iPhone Home Screen Button */}
          <button
            className="btn btn-secondary"
            style={{
              marginBottom: '20px',
              border: '1px solid rgba(59, 130, 246, 0.3)',
              background: 'rgba(59, 130, 246, 0.08)',
              color: '#2563eb',
            }}
            onClick={() => setIsA2HSOpen(true)}
          >
            <Smartphone size={18} color="#2563eb" />
            <span>📱 Добавить на экран «Домой» (iPhone)</span>
          </button>
        </div>
      )}

      {/* Modals */}
      {profile && (
        <EditProfileModal
          profile={profile}
          isOpen={isEditProfileOpen}
          onClose={() => setIsEditProfileOpen(false)}
          onSave={handleSaveProfile}
        />
      )}

      <RemindersModal
        isOpen={isRemindersOpen}
        onClose={() => setIsRemindersOpen(false)}
        reminders={reminders}
        timezone={profile?.timezone || 'Asia/Almaty'}
        onRefresh={loadAll}
      />

      <AddToHomeScreenModal
        isOpen={isA2HSOpen}
        onClose={() => setIsA2HSOpen(false)}
      />
    </div>
  );
};
