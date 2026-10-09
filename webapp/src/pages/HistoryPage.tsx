import React, { useState, useEffect } from 'react';
import { ChevronDown, ChevronUp, Calendar, Loader2 } from 'lucide-react';
import { HistoryDay, FoodEntry } from '../api/types';
import { api } from '../api/client';
import { MealCard } from '../components/MealCard';
import { MealDetailModal } from '../components/MealDetailModal';

export const HistoryPage: React.FC = () => {
  const [historyDays, setHistoryDays] = useState<HistoryDay[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [expandedDate, setExpandedDate] = useState<string | null>(null);
  const [dateMeals, setDateMeals] = useState<Record<string, FoodEntry[]>>({});
  const [selectedMeal, setSelectedMeal] = useState<FoodEntry | null>(null);

  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    setIsLoading(true);
    try {
      const days = await api.getHistory(14, 0);
      setHistoryDays(days);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleExpandDate = async (date: string) => {
    if (expandedDate === date) {
      setExpandedDate(null);
      return;
    }

    setExpandedDate(date);
    if (!dateMeals[date]) {
      try {
        const meals = await api.getHistoryByDate(date);
        setDateMeals((prev) => ({ ...prev, [date]: meals }));
      } catch (err) {
        console.error(err);
      }
    }
  };

  const formatDateLabel = (dateStr: string) => {
    const today = new Date().toISOString().split('T')[0];
    const yesterday = new Date(Date.now() - 86400000).toISOString().split('T')[0];

    if (dateStr === today) return 'Сегодня';
    if (dateStr === yesterday) return 'Вчера';

    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
    } catch {
      return dateStr;
    }
  };

  return (
    <div>
      <div className="section-title" style={{ fontSize: '20px', marginBottom: '18px' }}>
        <span>История питания</span>
      </div>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: '40px' }}>
          <Loader2 className="animate-spin" size={32} color="var(--color-primary)" style={{ margin: '0 auto' }} />
        </div>
      ) : historyDays.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {historyDays.map((day) => {
            const isExpanded = expandedDate === day.date;
            const meals = dateMeals[day.date] || [];

            return (
              <div key={day.date} className="card" style={{ padding: '14px', marginBottom: 0 }}>
                <div
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
                  onClick={() => toggleExpandDate(day.date)}
                >
                  <div>
                    <div style={{ fontWeight: 700, fontSize: '15px' }}>{formatDateLabel(day.date)}</div>
                    <div style={{ fontSize: '13px', color: 'var(--color-text-muted)' }}>
                      {day.calories} / {day.target_calories} ккал • {day.meals_count} приёмов
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontWeight: 700, fontSize: '14px' }}>{day.percentage}%</span>
                    {isExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                  </div>
                </div>

                <div className="progress-container" style={{ marginTop: '10px' }}>
                  <div
                    className="progress-bar-fill"
                    style={{
                      width: `${Math.min(100, day.percentage)}%`,
                      backgroundColor: day.percentage > 100 ? 'var(--color-warning)' : 'var(--color-primary)',
                    }}
                  />
                </div>

                {/* Expanded meals */}
                {isExpanded && (
                  <div style={{ marginTop: '14px', paddingTop: '10px', borderTop: '1px solid var(--color-border)' }}>
                    {meals.length > 0 ? (
                      meals.map((meal) => (
                        <MealCard
                          key={meal.id}
                          meal={meal}
                          onClick={() => setSelectedMeal(meal)}
                          onDelete={async (id) => {
                            await api.deleteFood(id);
                            loadHistory();
                          }}
                        />
                      ))
                    ) : (
                      <div style={{ fontSize: '13px', color: 'var(--color-text-muted)', textAlign: 'center', padding: '10px' }}>
                        Загрузка приёмов пищи...
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="empty-state card">
          <Calendar size={36} color="var(--color-text-muted)" style={{ margin: '0 auto 10px auto', display: 'block' }} />
          <div style={{ fontWeight: 600, fontSize: '15px' }}>История пока пуста</div>
          <div style={{ fontSize: '13px' }}>Добавляйте блюда каждый день, чтобы видеть прогресс</div>
        </div>
      )}

      <MealDetailModal
        meal={selectedMeal}
        onClose={() => setSelectedMeal(null)}
        onDelete={async (id) => {
          await api.deleteFood(id);
          loadHistory();
        }}
      />
    </div>
  );
};
