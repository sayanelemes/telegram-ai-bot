import React, { useState, useEffect } from 'react';
import { Plus, Trash2, Wallet, Loader2, PiggyBank, AlertTriangle, ArrowDownLeft, ArrowUpRight, Sparkles, Filter } from 'lucide-react';
import { ExpensesSummary, ExpenseEntry, ReceiptAnalysisResult, ExpenseParsedResult, BudgetSummary } from '../api/types';
import { api } from '../api/client';
import { AddExpenseModal } from '../components/AddExpenseModal';
import { AddIncomeModal } from '../components/AddIncomeModal';
import { ConfirmExpenseModal } from '../components/ConfirmExpenseModal';
import { BudgetModal } from '../components/BudgetModal';

export const ExpensesPage: React.FC = () => {
  const [data, setData] = useState<ExpensesSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isAddExpenseOpen, setIsAddExpenseOpen] = useState(false);
  const [isAddIncomeOpen, setIsAddIncomeOpen] = useState(false);
  const [isBudgetModalOpen, setIsBudgetModalOpen] = useState(false);
  const [analyzedExpense, setAnalyzedExpense] = useState<(ReceiptAnalysisResult | ExpenseParsedResult) | null>(null);
  const [filterType, setFilterType] = useState<'all' | 'expense' | 'income'>('all');

  useEffect(() => {
    loadExpenses();
  }, []);

  const loadExpenses = async () => {
    setIsLoading(true);
    try {
      const summary = await api.getExpenses();
      setData(summary);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSaveExpense = async (saveData: any) => {
    await api.saveExpense(saveData);
    loadExpenses();
  };

  const handleDeleteTransaction = async (id: number, typeName: string = 'запись') => {
    if (confirm(`Удалить ${typeName}?`)) {
      try {
        await api.deleteExpense(id);
        loadExpenses();
      } catch (err) {
        alert('Ошибка при удалении: ' + err);
      }
    }
  };

  const handleSaveBudget = async (weekly: number, monthly: number) => {
    await api.updateBudget(weekly, monthly);
    loadExpenses();
  };

  const budget = data?.budget;

  // Filter recent operations
  const filteredRecent = (data?.recent || []).filter((item) => {
    if (filterType === 'all') return true;
    if (filterType === 'expense') return item.entry_type !== 'income';
    if (filterType === 'income') return item.entry_type === 'income';
    return true;
  });

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <div className="section-title" style={{ fontSize: '20px', margin: 0 }}>
          <span>Финансы и бюджет</span>
        </div>
        <button
          className="btn btn-secondary"
          style={{ padding: '6px 12px', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}
          onClick={() => setIsBudgetModalOpen(true)}
        >
          <PiggyBank size={16} color="var(--color-primary)" />
          <span>Бюджет</span>
        </button>
      </div>

      {isLoading || !data ? (
        <div style={{ textAlign: 'center', padding: '40px' }}>
          <Loader2 className="animate-spin" size={32} color="var(--color-primary)" style={{ margin: '0 auto' }} />
        </div>
      ) : (
        <div>
          {/* Main Action Buttons: Add Expense & Add Income */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px', marginBottom: '16px' }}>
            <button
              className="btn btn-primary"
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                padding: '12px',
                fontSize: '14px',
                fontWeight: 700,
              }}
              onClick={() => setIsAddExpenseOpen(true)}
            >
              <ArrowDownLeft size={18} />
              <span>+ Расход</span>
            </button>

            <button
              className="btn"
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                padding: '12px',
                fontSize: '14px',
                fontWeight: 700,
                background: '#10b981',
                color: '#ffffff',
                border: 'none',
                borderRadius: 'var(--radius-md)',
              }}
              onClick={() => setIsAddIncomeOpen(true)}
            >
              <ArrowUpRight size={18} />
              <span>+ Доход</span>
            </button>
          </div>

          {/* Totals & Balance Cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px', marginBottom: '16px' }}>
            <div className="card" style={{ padding: '12px', textAlign: 'center', marginBottom: 0 }}>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--color-text-muted)' }}>Расходы (мес)</div>
              <div style={{ fontSize: '15px', fontWeight: 800, color: 'var(--color-danger)' }}>
                {data.month_total.toLocaleString('ru-RU')} ₸
              </div>
            </div>

            <div className="card" style={{ padding: '12px', textAlign: 'center', marginBottom: 0 }}>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--color-text-muted)' }}>Доходы (мес)</div>
              <div style={{ fontSize: '15px', fontWeight: 800, color: '#10b981' }}>
                +{data.month_income.toLocaleString('ru-RU')} ₸
              </div>
            </div>

            <div className="card" style={{ padding: '12px', textAlign: 'center', marginBottom: 0 }}>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--color-text-muted)' }}>Баланс</div>
              <div
                style={{
                  fontSize: '15px',
                  fontWeight: 800,
                  color: data.net_balance >= 0 ? '#10b981' : 'var(--color-danger)',
                }}
              >
                {data.net_balance >= 0 ? '+' : ''}
                {data.net_balance.toLocaleString('ru-RU')} ₸
              </div>
            </div>
          </div>

          {/* Budget Overview Section */}
          {budget && (budget.weekly_budget > 0 || budget.monthly_budget > 0) ? (
            <div style={{ marginBottom: '16px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px' }}>
                {/* Weekly Budget Card */}
                {budget.weekly_budget > 0 && (
                  <div className="card" style={{ padding: '14px', marginBottom: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                      <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--color-text-muted)' }}>
                        Недельный бюджет
                      </span>
                      <span style={{ fontSize: '11px', fontWeight: 700, color: budget.week_exceeded > 0 ? 'var(--color-danger)' : 'var(--color-primary)' }}>
                        {budget.week_percentage}%
                      </span>
                    </div>

                    <div style={{ fontSize: '15px', fontWeight: 800 }}>
                      {budget.week_spent.toLocaleString('ru-RU')} / {budget.weekly_budget.toLocaleString('ru-RU')} ₸
                    </div>

                    <div className="progress-container" style={{ height: '6px', margin: '8px 0 6px 0' }}>
                      <div
                        className="progress-bar-fill"
                        style={{
                          width: `${Math.min(100, budget.week_percentage)}%`,
                          backgroundColor: budget.week_exceeded > 0 ? 'var(--color-danger)' : 'var(--color-primary)',
                        }}
                      />
                    </div>

                    <div style={{ fontSize: '11px', color: budget.week_exceeded > 0 ? 'var(--color-danger)' : 'var(--color-text-muted)' }}>
                      {budget.week_exceeded > 0
                        ? `Превышение на ${budget.week_exceeded.toLocaleString('ru-RU')} ₸`
                        : `Осталось ${budget.week_remaining.toLocaleString('ru-RU')} ₸`}
                    </div>
                  </div>
                )}

                {/* Monthly Budget Card */}
                {budget.monthly_budget > 0 && (
                  <div className="card" style={{ padding: '14px', marginBottom: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                      <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--color-text-muted)' }}>
                        Месячный бюджет
                      </span>
                      <span style={{ fontSize: '11px', fontWeight: 700, color: budget.month_exceeded > 0 ? 'var(--color-danger)' : 'var(--color-primary)' }}>
                        {budget.month_percentage}%
                      </span>
                    </div>

                    <div style={{ fontSize: '15px', fontWeight: 800 }}>
                      {budget.month_spent.toLocaleString('ru-RU')} / {budget.monthly_budget.toLocaleString('ru-RU')} ₸
                    </div>

                    <div className="progress-container" style={{ height: '6px', margin: '8px 0 6px 0' }}>
                      <div
                        className="progress-bar-fill"
                        style={{
                          width: `${Math.min(100, budget.month_percentage)}%`,
                          backgroundColor: budget.month_exceeded > 0 ? 'var(--color-danger)' : 'var(--color-primary)',
                        }}
                      />
                    </div>

                    <div style={{ fontSize: '11px', color: budget.month_exceeded > 0 ? 'var(--color-danger)' : 'var(--color-text-muted)' }}>
                      {budget.month_exceeded > 0
                        ? `Превышение на ${budget.month_exceeded.toLocaleString('ru-RU')} ₸`
                        : `Осталось ${budget.month_remaining.toLocaleString('ru-RU')} ₸`}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div
              className="card"
              style={{
                padding: '12px 14px',
                marginBottom: '16px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                background: 'rgba(37, 99, 235, 0.05)',
                border: '1px dashed var(--color-border)',
              }}
            >
              <div>
                <div style={{ fontSize: '13px', fontWeight: 700 }}>Установите бюджет</div>
                <div style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>
                  Задайте лимиты на неделю и месяц для контроля расходов
                </div>
              </div>
              <button
                className="btn btn-primary"
                style={{ padding: '6px 12px', fontSize: '12px' }}
                onClick={() => setIsBudgetModalOpen(true)}
              >
                Настроить
              </button>
            </div>
          )}

          {/* Categories */}
          {data.categories.length > 0 && (
            <div style={{ marginBottom: '20px' }}>
              <div className="section-title">Категории расходов ({data.month_title})</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px' }}>
                {data.categories.map((cat) => (
                  <div key={cat.category} className="card" style={{ padding: '12px', marginBottom: 0 }}>
                    <div style={{ fontSize: '13px', fontWeight: 600 }}>{cat.label}</div>
                    <div style={{ fontSize: '16px', fontWeight: 800, marginTop: '2px' }}>
                      {cat.total.toLocaleString('ru-RU')} ₸
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>
                      {cat.count} покупок
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recent Operations Section with Filter Tabs */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <div className="section-title" style={{ margin: 0 }}>Операции</div>
              <div style={{ display: 'flex', gap: '4px', background: 'var(--color-card-bg)', padding: '3px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--color-border)' }}>
                <button
                  type="button"
                  style={{
                    border: 'none',
                    padding: '4px 8px',
                    fontSize: '11px',
                    fontWeight: 600,
                    borderRadius: '4px',
                    cursor: 'pointer',
                    background: filterType === 'all' ? 'var(--color-primary)' : 'transparent',
                    color: filterType === 'all' ? '#fff' : 'var(--color-text-muted)',
                  }}
                  onClick={() => setFilterType('all')}
                >
                  Все
                </button>
                <button
                  type="button"
                  style={{
                    border: 'none',
                    padding: '4px 8px',
                    fontSize: '11px',
                    fontWeight: 600,
                    borderRadius: '4px',
                    cursor: 'pointer',
                    background: filterType === 'expense' ? 'var(--color-danger)' : 'transparent',
                    color: filterType === 'expense' ? '#fff' : 'var(--color-text-muted)',
                  }}
                  onClick={() => setFilterType('expense')}
                >
                  Расходы
                </button>
                <button
                  type="button"
                  style={{
                    border: 'none',
                    padding: '4px 8px',
                    fontSize: '11px',
                    fontWeight: 600,
                    borderRadius: '4px',
                    cursor: 'pointer',
                    background: filterType === 'income' ? '#10b981' : 'transparent',
                    color: filterType === 'income' ? '#fff' : 'var(--color-text-muted)',
                  }}
                  onClick={() => setFilterType('income')}
                >
                  Доходы
                </button>
              </div>
            </div>

            {filteredRecent.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {filteredRecent.map((item) => {
                  const isIncome = item.entry_type === 'income';

                  return (
                    <div
                      key={item.id}
                      className="card"
                      style={{
                        padding: '12px 14px',
                        marginBottom: 0,
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            {isIncome ? (
                              <ArrowUpRight size={16} color="#10b981" />
                            ) : (
                              <ArrowDownLeft size={16} color="var(--color-danger)" />
                            )}
                            <span style={{ fontWeight: 700, fontSize: '14px' }}>{item.merchant}</span>
                          </div>

                          <div style={{ fontSize: '12px', color: 'var(--color-text-muted)', marginTop: '2px' }}>
                            {item.category_label} • {item.expense_date}
                          </div>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                          <div
                            style={{
                              fontWeight: 800,
                              fontSize: '15px',
                              color: isIncome ? '#10b981' : 'var(--color-text)',
                            }}
                          >
                            {isIncome ? '+' : '-'} {item.amount.toLocaleString('ru-RU')} {item.currency}
                          </div>
                          <button
                            title={`Удалить ${isIncome ? 'доход' : 'расход'}`}
                            style={{
                              background: 'none',
                              border: 'none',
                              color: 'var(--color-text-muted)',
                              cursor: 'pointer',
                              padding: '4px',
                            }}
                            onClick={() => handleDeleteTransaction(item.id, isIncome ? 'доход' : 'расход')}
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      </div>

                      {/* AI Impulsive Purchase or Feedback Badge */}
                      {item.is_impulsive ? (
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px',
                            background: 'rgba(239, 68, 68, 0.08)',
                            color: 'var(--color-danger)',
                            padding: '6px 10px',
                            borderRadius: 'var(--radius-sm)',
                            marginTop: '8px',
                            fontSize: '11px',
                            fontWeight: 600,
                          }}
                        >
                          <AlertTriangle size={14} />
                          <span>⚠️ Импульсивная покупка! Не рекомендуется</span>
                        </div>
                      ) : item.ai_analysis && !isIncome ? (
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px',
                            background: 'rgba(16, 185, 129, 0.08)',
                            color: '#10b981',
                            padding: '6px 10px',
                            borderRadius: 'var(--radius-sm)',
                            marginTop: '8px',
                            fontSize: '11px',
                            fontWeight: 600,
                          }}
                        >
                          <Sparkles size={14} />
                          <span>{item.ai_analysis}</span>
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="empty-state card">
                <Wallet size={36} color="var(--color-text-muted)" style={{ margin: '0 auto 10px auto', display: 'block' }} />
                <div style={{ fontWeight: 600, fontSize: '15px' }}>
                  {filterType === 'income' ? 'Доходов пока нет' : 'Операций пока нет'}
                </div>
                <div style={{ fontSize: '13px' }}>
                  {filterType === 'income'
                    ? 'Нажмите кнопку «+ Доход» вверху, чтобы зафиксировать поступление'
                    : 'Сфотографируйте чек или введите расход/доход'}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Modals */}
      <AddExpenseModal
        isOpen={isAddExpenseOpen}
        onClose={() => setIsAddExpenseOpen(false)}
        onAnalysisComplete={(res) => setAnalyzedExpense(res)}
      />

      <AddIncomeModal
        isOpen={isAddIncomeOpen}
        onClose={() => setIsAddIncomeOpen(false)}
        onIncomeSaved={() => loadExpenses()}
      />

      <ConfirmExpenseModal
        data={analyzedExpense}
        onClose={() => setAnalyzedExpense(null)}
        onSave={handleSaveExpense}
      />

      <BudgetModal
        isOpen={isBudgetModalOpen}
        budget={budget}
        onClose={() => setIsBudgetModalOpen(false)}
        onSave={handleSaveBudget}
      />
    </div>
  );
};
