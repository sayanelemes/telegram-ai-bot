import React, { useState, useEffect } from 'react';
import { Plus, UtensilsCrossed, Smartphone, X } from 'lucide-react';
import { DashboardData, FoodEntry, FoodAnalysisResult } from '../api/types';
import { CalorieHero } from '../components/CalorieHero';
import { MacroBars } from '../components/MacroBars';
import { MealCard } from '../components/MealCard';
import { MealDetailModal } from '../components/MealDetailModal';
import { AddFoodModal } from '../components/AddFoodModal';
import { ConfirmFoodModal } from '../components/ConfirmFoodModal';
import { AddToHomeScreenModal } from '../components/AddToHomeScreenModal';
import { ThemeToggle } from '../components/ThemeToggle';
import { api } from '../api/client';

interface DashboardPageProps {
  data: DashboardData;
  onRefresh: () => void;
  onNavigateToProfile: () => void;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({
  data,
  onRefresh,
  onNavigateToProfile,
}) => {
  const [selectedMeal, setSelectedMeal] = useState<FoodEntry | null>(null);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [analyzedFood, setAnalyzedFood] = useState<FoodAnalysisResult | null>(null);
  const [isA2HSOpen, setIsA2HSOpen] = useState(false);
  const [showA2HSBanner, setShowA2HSBanner] = useState(false);

  useEffect(() => {
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches || (window.navigator as any).standalone === true;
    const isDismissed = localStorage.getItem('dismiss_a2hs_banner') === 'true';
    if (!isStandalone && !isDismissed) {
      setShowA2HSBanner(true);
    }
  }, []);

  const handleDismissBanner = (e: React.MouseEvent) => {
    e.stopPropagation();
    setShowA2HSBanner(false);
    localStorage.setItem('dismiss_a2hs_banner', 'true');
  };

  const handleDeleteMeal = async (id: number) => {
    try {
      await api.deleteFood(id);
      onRefresh();
    } catch (err) {
      alert('Ошибка при удалении блюда: ' + err);
    }
  };

  const handleSaveConfirmedFood = async (savePayload: any) => {
    await api.saveFood(savePayload);
    onRefresh();
  };

  return (
    <div>
      {/* User greeting */}
      <div className="app-header">
        <div className="user-greeting">
          <h1>Привет, {data.user_name}! 👋</h1>
          <p>Дневник питания и расходов</p>
        </div>
        <ThemeToggle />
      </div>

      {/* iOS Home Screen Quick Banner */}
      {showA2HSBanner && (
        <div
          className="card"
          style={{
            background: 'linear-gradient(135deg, rgba(37, 99, 235, 0.12) 0%, rgba(59, 130, 246, 0.05) 100%)',
            border: '1px solid rgba(59, 130, 246, 0.3)',
            marginBottom: '14px',
            padding: '12px 14px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '10px',
            cursor: 'pointer',
          }}
          onClick={() => setIsA2HSOpen(true)}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                background: '#2563eb',
                color: '#fff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              <Smartphone size={18} />
            </div>
            <div>
              <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--color-text)' }}>
                Добавить на экран iPhone
              </div>
              <div style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>
                Запуск в 1 клик во весь экран
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '12px', fontWeight: 700, color: '#2563eb' }}>Установить →</span>
            <button
              onClick={handleDismissBanner}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--color-text-muted)',
                padding: '4px',
                cursor: 'pointer',
                display: 'flex',
              }}
            >
              <X size={15} />
            </button>
          </div>
        </div>
      )}

      {!data.is_profile_configured && (
        <div
          className="card"
          style={{
            background: 'rgba(37, 99, 235, 0.08)',
            border: '1px solid rgba(37, 99, 235, 0.25)',
            marginBottom: '16px',
            cursor: 'pointer',
          }}
          onClick={onNavigateToProfile}
        >
          <div style={{ fontWeight: 700, fontSize: '14px', marginBottom: '2px' }}>
            🎯 Настройте ваш профиль
          </div>
          <div style={{ fontSize: '12px', color: 'var(--color-text-muted)' }}>
            Укажите вес, рост и цель для точного персонального расчёта калорий →
          </div>
        </div>
      )}

      {/* Main Calorie Hero */}
      <CalorieHero calories={data.calories} />

      {/* Macros */}
      <MacroBars macros={data.macros} />

      {/* Today's Meals */}
      <div className="section-title">
        <span>Сегодня</span>
        <span style={{ fontSize: '13px', fontWeight: 500, color: 'var(--color-text-muted)' }}>
          {data.meals.length} приёмов пищи
        </span>
      </div>

      {data.meals.length > 0 ? (
        data.meals.map((meal) => (
          <MealCard
            key={meal.id}
            meal={meal}
            onClick={() => setSelectedMeal(meal)}
            onDelete={handleDeleteMeal}
          />
        ))
      ) : (
        <div className="empty-state card">
          <UtensilsCrossed size={36} color="var(--color-text-muted)" style={{ margin: '0 auto 10px auto', display: 'block' }} />
          <div style={{ fontWeight: 600, fontSize: '15px', marginBottom: '4px' }}>
            Приёмов пищи пока нет
          </div>
          <div style={{ fontSize: '13px' }}>
            Нажмите <b>+</b> внизу, чтобы сфотографировать блюдо или ввести текст
          </div>
        </div>
      )}

      {/* Floating Action Button */}
      <button className="fab-btn" onClick={() => setIsAddModalOpen(true)}>
        <Plus size={28} />
      </button>

      {/* Modals */}
      <MealDetailModal
        meal={selectedMeal}
        onClose={() => setSelectedMeal(null)}
        onDelete={handleDeleteMeal}
      />

      <AddFoodModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        onAnalysisComplete={(res) => setAnalyzedFood(res)}
      />

      <ConfirmFoodModal
        data={analyzedFood}
        onClose={() => setAnalyzedFood(null)}
        onSave={handleSaveConfirmedFood}
      />

      <AddToHomeScreenModal
        isOpen={isA2HSOpen}
        onClose={() => setIsA2HSOpen(false)}
      />
    </div>
  );
};
