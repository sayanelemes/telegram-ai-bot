import React, { useState, useEffect } from 'react';
import { BottomNavigation } from './components/BottomNavigation';
import { DashboardPage } from './pages/DashboardPage';
import { HistoryPage } from './pages/HistoryPage';
import { ExpensesPage } from './pages/ExpensesPage';
import { ProfilePage } from './pages/ProfilePage';
import { AuthScreen } from './components/AuthScreen';
import { api } from './api/client';
import { DashboardData } from './api/types';
import { Loader2 } from 'lucide-react';

export const App: React.FC = () => {
  const [currentTab, setCurrentTab] = useState<string>('dashboard');
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Initialize Telegram WebApp & Standalone session
  useEffect(() => {
    if (window.Telegram?.WebApp) {
      window.Telegram.WebApp.ready();
      window.Telegram.WebApp.expand();

      // Apply Telegram theme colors if provided
      const theme = window.Telegram.WebApp.themeParams;
      if (theme) {
        const root = document.documentElement;
        if (theme.bg_color) root.style.setProperty('--tg-theme-bg-color', theme.bg_color);
        if (theme.text_color) root.style.setProperty('--tg-theme-text-color', theme.text_color);
        if (theme.hint_color) root.style.setProperty('--tg-theme-hint-color', theme.hint_color);
        if (theme.button_color) root.style.setProperty('--tg-theme-button-color', theme.button_color);
        if (theme.button_text_color) root.style.setProperty('--tg-theme-button-text-color', theme.button_text_color);
        if (theme.secondary_bg_color) root.style.setProperty('--tg-theme-secondary-bg-color', theme.secondary_bg_color);
      }

      // If inside Telegram, fetch and cache standalone token for future PWA launches
      if (window.Telegram.WebApp.initData) {
        api.getAuthToken().catch(() => {});
      }
    }
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await api.getDashboard();
      setDashboardData(data);
    } catch (err: any) {
      console.error('Error fetching dashboard:', err);
      setError(err.message || 'Не удалось загрузить данные');
    } finally {
      setIsLoading(false);
    }
  };

  const isAuthError =
    error &&
    (error.toLowerCase().includes('авторизац') ||
      error.toLowerCase().includes('initdata') ||
      error.includes('401'));

  return (
    <div className="app-container">
      <main className="content-area">
        {isLoading ? (
          <div style={{ textAlign: 'center', padding: '60px 16px' }}>
            <Loader2 className="animate-spin" size={40} color="var(--color-primary)" style={{ margin: '0 auto 16px auto', display: 'block' }} />
            <div style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>Загрузка приложения...</div>
          </div>
        ) : isAuthError ? (
          <AuthScreen onSuccess={loadDashboard} />
        ) : error ? (
          <div style={{ textAlign: 'center', padding: '40px 16px' }}>
            <div style={{ color: 'var(--color-danger)', fontWeight: 700, marginBottom: '8px' }}>
              Ошибка подключения
            </div>
            <div style={{ fontSize: '13px', color: 'var(--color-text-muted)', marginBottom: '16px' }}>
              {error}
            </div>
            <button className="btn btn-primary" onClick={loadDashboard}>
              Повторить попытку
            </button>
          </div>
        ) : (
          <>
            {currentTab === 'dashboard' && dashboardData && (
              <DashboardPage
                data={dashboardData}
                onRefresh={loadDashboard}
                onNavigateToProfile={() => setCurrentTab('profile')}
              />
            )}
            {currentTab === 'history' && <HistoryPage />}
            {currentTab === 'expenses' && <ExpensesPage />}
            {currentTab === 'profile' && (
              <ProfilePage onProfileUpdated={loadDashboard} />
            )}
          </>
        )}
      </main>

      {!isAuthError && (
        <BottomNavigation
          currentTab={currentTab}
          onSelectTab={(tab) => setCurrentTab(tab)}
        />
      )}
    </div>
  );
};

export default App;
