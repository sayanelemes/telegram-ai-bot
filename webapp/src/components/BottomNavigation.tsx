import React from 'react';
import { Home, History, Wallet, User } from 'lucide-react';

interface BottomNavigationProps {
  currentTab: string;
  onSelectTab: (tab: string) => void;
}

export const BottomNavigation: React.FC<BottomNavigationProps> = ({ currentTab, onSelectTab }) => {
  const tabs = [
    { id: 'dashboard', label: 'Главная', icon: Home },
    { id: 'history', label: 'История', icon: History },
    { id: 'expenses', label: 'Финансы', icon: Wallet },
    { id: 'profile', label: 'Профиль', icon: User },
  ];

  const handleTabClick = (tabId: string) => {
    if (window.Telegram?.WebApp?.HapticFeedback) {
      window.Telegram.WebApp.HapticFeedback.selectionChanged();
    }
    onSelectTab(tabId);
  };

  return (
    <nav className="bottom-nav">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = currentTab === tab.id;
        return (
          <button
            key={tab.id}
            className={`nav-item ${isActive ? 'active' : ''}`}
            onClick={() => handleTabClick(tab.id)}
          >
            <Icon size={20} strokeWidth={isActive ? 2.4 : 1.8} />
            <span>{tab.label}</span>
          </button>
        );
      })}
    </nav>
  );
};
