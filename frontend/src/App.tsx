import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  Coffee,
  FileInput,
  History,
  Inbox,
  LayoutList,
  MapPin,
  Package,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";
import { api, dateTime, post, sourceLabel } from "./api";
import type { Summary, Ticket, TicketRow } from "./types";
import { Empty, Modal, Notice, QueueArtwork, Spinner, Status, errorText } from "./ui";
import { clearDrafts, hasDrafts, useDirtyDrafts, useDraftState } from "./drafts";
import { ImportPage, JournalPage, RulesPage, StockPage } from "./pages";
import TicketPage from "./TicketPage";

type Screen = "queue" | "stock" | "imports" | "rules" | "audit";
const navigation = [
  { id: "queue" as Screen, label: "Очередь обращений", icon: LayoutList },
  { id: "stock" as Screen, label: "Детали и резервы", icon: Package },
  { id: "imports" as Screen, label: "Импорт данных", icon: FileInput },
  { id: "rules" as Screen, label: "Правила подготовки", icon: ShieldCheck },
  { id: "audit" as Screen, label: "Журнал действий", icon: History },
];

export default function App() {
  const [screen, setScreen] = useState<Screen>(() => {
    const section = new URLSearchParams(location.search).get("section");
    return navigation.some(n => n.id === section) ? section as Screen : "queue";
  });
  const [selected, setSelected] = useState<number | null>(
    () => Number(new URLSearchParams(location.search).get("ticket")) || null,
  );
  const [summary, setSummary] = useState<Summary | null>(null);
  const [health, setHealth] = useState<{
    status: string;
    llm_enabled: boolean;
    llm_configured: boolean;
  } | null>(null);
  const [loadError, setLoadError] = useState("");
  const [version, setVersion] = useState(0);
  const [showNew, setShowNew] = useState(false);
  const [toast, setToast] = useState("");
  const [pendingNavigation, setPendingNavigation] = useState<(() => void) | null>(null);
  useDirtyDrafts();
  const newDraft = useDirtyDrafts(0);
  const notify = useCallback((message: string) => setToast(message), []);
  const reload = useCallback(() => setVersion((v) => v + 1), []);
  const navigate = useCallback((target: Screen, id: number | null = null) => {
    const action = () => {setScreen(target); setSelected(id); history.pushState(null, "", id ? `?ticket=${id}` : target === "queue" ? "/" : `?section=${target}`); window.scrollTo({ top: 0 });};
    if (hasDrafts(selected ?? 0)) setPendingNavigation(() => action); else action();
  }, [selected]);
  useEffect(() => {
    Promise.all([
      api<Summary>("/summary"),
      api<{ status: string; llm_enabled: boolean; llm_configured: boolean }>(
        "/health",
      ),
    ])
      .then(([s, h]) => {
        setSummary(s);
        setHealth(h);
        setLoadError("");
      })
      .catch((e) => setLoadError(errorText(e)));
  }, [version]);
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(""), 5500);
      return () => clearTimeout(timer);
    }
  }, [toast]);
  useEffect(() => {
    const pop = () => {
      const section = new URLSearchParams(location.search).get("section");
      setScreen(navigation.some(n => n.id === section) ? section as Screen : "queue");
      setSelected(
        Number(new URLSearchParams(location.search).get("ticket")) || null,
      );
    };
    addEventListener("popstate", pop);
    return () => removeEventListener("popstate", pop);
  }, []);
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button
          className="brand"
          onClick={() => navigate("queue")}
          aria-label="КофеСервис, главная"
        >
          <span className="brand-icon">
            <Coffee size={25} strokeWidth={1.8} />
          </span>
          <span>
            КофеСервис<small>РЕГИОН</small>
          </span>
        </button>
        <div className="workspace-label">РАБОЧЕЕ МЕСТО</div>
        <nav aria-label="Основная навигация">
          {navigation.map((n) => (
            <button
              key={n.id}
              onClick={() => navigate(n.id)}
              className={`nav-item ${screen === n.id ? "active" : ""}`}
              aria-current={screen === n.id ? "page" : undefined}
            >
              <n.icon size={19} strokeWidth={1.7} />
              <span>{n.label}</span>
              {n.id === "queue" && summary && (
                <span className="nav-count">{summary.tickets}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="pilot-note">
            <span className="tiny-dot" />
            <strong>Локальный пилот</strong>
            <p>
              Подготовка выезда
              <br />
              по правилам сервиса
            </p>
          </div>
          <div className="operator">
            <span className="avatar">ДС</span>
            <div>
              <strong>Диспетчерская</strong>
              <small>Москва и Тула</small>
            </div>
          </div>
        </div>
      </aside>
      <div className="app-main">
        <header className="topbar">
          <div className="breadcrumb">
            КофеСервис Регион <ChevronRight size={14} />
            <strong>{navigation.find((n) => n.id === screen)?.label}</strong>
          </div>
          <div className="system-health">
            <span
              className={`tiny-dot ${!health || loadError ? "offline" : ""}`}
            />
            {health && !loadError ? "Сервер доступен" : "Проверка соединения"}
            <span className="topbar-separator" />
            <span className="engine-label">
              {health?.llm_enabled
                ? health.llm_configured ? "LLM настроена · результат в обращении" : "LLM не настроена · локальный разбор"
                : "Локальный разбор"}
            </span>
          </div>
        </header>
        <main className={`main-content ${selected ? "detail-content" : ""}`}>
          {newDraft && !showNew && <div className="draft-banner" role="status"><FileInput size={16} />Есть несохранённый черновик нового обращения.<button className="text-button" onClick={() => setShowNew(true)}>Продолжить ввод</button></div>}
          {loadError && (
            <div className="global-error">
              <Notice kind="error">
                {loadError}{" "}
                <button className="text-button" onClick={reload}>
                  Повторить
                </button>
              </Notice>
            </div>
          )}
          {screen === "queue" &&
            (selected ? (
              <TicketPage
                id={selected}
                onBack={() => navigate("queue")}
                onChange={reload}
                notify={notify}
                onSelect={(id) => navigate("queue", id)}
              />
            ) : (
              <>
                <div className="page-heading queue-hero">
                  <div>
                    <div className="eyebrow">ДИСПЕТЧЕРСКАЯ <span className="region-label">МОСКВА + ТУЛА</span></div>
                    <h1>Подготовка выездов</h1>
                    <p>Всё, что нужно инженеру. До первого выезда.</p>
                  </div>
                  <QueueArtwork />
                  <button
                    className="button primary"
                    onClick={() => setShowNew(true)}
                  >
                    <Plus size={18} />
                    Новое обращение
                  </button>
                </div>
                <div className="stats-grid">
                  {[
                    {
                      label: "В работе",
                      value: summary?.tickets,
                      icon: Inbox,
                      color: "teal",
                      sub: `${summary?.messages ?? "—"} исходных сообщений`,
                    },
                    {
                      label: "Нужна подготовка",
                      value: summary?.blocked,
                      icon: SlidersHorizontal,
                      color: "amber",
                      sub: "Есть препятствия к выезду",
                    },
                    {
                      label: "Карточки готовы",
                      value: summary?.ready,
                      icon: CheckCircle2,
                      color: "green",
                      sub: "Подготовлены к передаче",
                    },
                    {
                      label: "На согласование",
                      value: summary?.warranty,
                      icon: ShieldCheck,
                      color: "purple",
                      sub: "Гарантия или новая установка",
                    },
                  ].map((s) => (
                    <div className="stat-card" key={s.label}>
                      <div className="stat-top">
                        <span>{s.label}</span>
                        <span className={`stat-icon ${s.color}`}>
                          <s.icon size={18} />
                        </span>
                      </div>
                      <strong className={`stat-value ${String(s.value ?? "").length > 5 ? "long-value" : ""}`}>{s.value ?? "—"}</strong>
                      <small>{s.sub}</small>
                    </div>
                  ))}
                </div>
                <Queue
                  version={version}
                  open={(id) => navigate("queue", id)}
                  importData={() => navigate("imports")}
                  newMessage={() => setShowNew(true)}
                  reload={reload}
                />
                <div className="queue-footer">
                  <ShieldCheck size={16} />
                  <span>
                    Готовность проверяется по правилам сервиса. Симптом и
                    история не считаются диагнозом.
                  </span>
                  <button
                    className="text-button"
                    onClick={() => navigate("rules")}
                  >
                    Открыть правила <ArrowRight size={13} />
                  </button>
                </div>
              </>
            ))}
          {screen === "stock" && <StockPage version={version} />}
          {screen === "imports" && (
            <ImportPage
              version={version}
              onChange={reload}
              notify={notify}
              openQueue={() => navigate("queue")}
            />
          )}
          {screen === "rules" && <RulesPage />}
          {screen === "audit" && (
            <JournalPage
              version={version}
              onSelect={(id) => navigate("queue", id)}
            />
          )}
        </main>
        <footer className="app-footer"><span>КОФЕСЕРВИС РЕГИОН · ДИСПЕТЧЕРСКАЯ</span><a href="/assets/ATTRIBUTION.html" target="_blank" rel="noreferrer">Материалы и лицензии</a></footer>
      </div>
      {showNew && (
        <Modal title="Новое обращение" close={() => setShowNew(false)}>
          <NewMessageForm
            onCreated={(ticket) => {
              setShowNew(false);
              navigate("queue", ticket.id);
              reload();
              notify("Обращение сохранено и разобрано");
            }}
          />
        </Modal>
      )}
      {toast && (
        <div role="status" className="toast">
          <CheckCircle2 size={18} />
          {toast}
          <button
            className="icon-button"
            onClick={() => setToast("")}
            aria-label="Закрыть уведомление"
          >
            ×
          </button>
        </div>
      )}
      {pendingNavigation && <Modal title="Есть несохранённые изменения" close={() => setPendingNavigation(null)}><p>Изменения ещё не записаны в заявку. Черновик останется в этой вкладке: вы сможете вернуться и сохранить его.</p><div className="form-actions"><button className="button secondary" onClick={() => setPendingNavigation(null)}>Остаться</button><button className="button primary" onClick={() => {pendingNavigation(); setPendingNavigation(null);}}>Перейти, сохранив черновик</button></div></Modal>}
    </div>
  );
}

function Queue({
  version,
  open,
  importData,
  newMessage,
  reload,
}: {
  version: number;
  open: (id: number) => void;
  importData: () => void;
  newMessage: () => void;
  reload: () => void;
}) {
  const [rows, setRows] = useState<TicketRow[] | null>(null);
  const [q, setQ] = useState(""),
    [status, setStatus] = useState(""),
    [city, setCity] = useState(""),
    [source, setSource] = useState("");
  const [error, setError] = useState(""),
    [loading, setLoading] = useState(false);
  useEffect(() => {
    let active = true;
    const timer = setTimeout(
      () => {
        setLoading(true);
        api<TicketRow[]>(
          "/tickets?" + new URLSearchParams({ q, status, city, source }),
        )
          .then((data) => {
            if (active) {
              setRows(data);
              setError("");
            }
          })
          .catch((e) => {
            if (active) setError(errorText(e));
          })
          .finally(() => {
            if (active) setLoading(false);
          });
      },
      q ? 220 : 0,
    );
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [q, status, city, source, version]);
  const filtered = !!(q || status || city || source);
  return (
    <section className="panel queue-panel" aria-label="Очередь обращений">
      <div className="queue-heading">
        <div>
          <h2>
            Очередь обращений{" "}
            <span className="count-pill">{rows?.length ?? "—"}</span>
          </h2>
          <p>Сначала уточнения, затем детали и готовность.</p>
        </div>
        <button
          className="icon-button"
          onClick={reload}
          aria-label="Обновить очередь"
        >
          <RefreshCw size={17} className={loading ? "spin" : ""} />
        </button>
      </div>
      <div className="queue-filters">
        <label className="search-input">
          <Search size={17} />
          <input
            aria-label="Поиск обращений"
            placeholder="Клиент, номер машины, текст…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
        <select
          aria-label="Статус заявки"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">Все статусы</option>
          <option value="blocked">Нужна подготовка</option>
          <option value="review">Можно подготовить</option>
          <option value="ready">Карточка готова к передаче</option>
          <option value="manager">Менеджеру</option>
        </select>
        <select
          aria-label="Город"
          value={city}
          onChange={(e) => setCity(e.target.value)}
        >
          <option value="">Оба города</option>
          <option>Москва</option>
          <option>Тула</option>
        </select>
        <select
          aria-label="Источник данных"
          value={source}
          onChange={(e) => setSource(e.target.value)}
        >
          <option value="">Все источники</option>
          <option value="case">Данные кейса</option>
          <option value="manual">Ручной ввод</option>
          <option value="upload">Excel</option>
          <option value="demo">Демонстрация</option>
        </select>
      </div>
      {error && (
        <Notice kind="error">
          {error}{" "}
          <button className="text-button" onClick={reload}>
            Повторить
          </button>
        </Notice>
      )}
      {rows === null && !error ? (
        <Spinner />
      ) : rows?.length === 0 ? (
        <Empty
          title={
            filtered ? "Обращений не найдено" : "Начнём с первого обращения"
          }
          text={
            filtered
              ? "Измените запрос или сбросьте фильтры."
              : "Импортируйте Excel кейса или введите сообщение клиента вручную."
          }
        >
          {filtered ? (
            <button
              className="button secondary"
              onClick={() => {
                setQ("");
                setStatus("");
                setCity("");
                setSource("");
              }}
            >
              Сбросить фильтры
            </button>
          ) : (
            <div className="button-row">
              <button className="button primary" onClick={importData}>
                <ArrowDownToLine size={17} />
                Импортировать Excel
              </button>
              <button className="button secondary" onClick={newMessage}>
                <Plus size={17} />
                Ввести сообщение
              </button>
            </div>
          )}
        </Empty>
      ) : (
        <div className={`table-scroll ${loading ? "refreshing" : ""}`}>
          <table className="queue-table">
            <thead>
              <tr>
                <th>ОБРАЩЕНИЕ / КЛИЕНТ</th>
                <th>ОБОРУДОВАНИЕ</th>
                <th>СИМПТОМ</th>
                <th>СЛЕДУЮЩЕЕ ДЕЙСТВИЕ</th>
                <th>ВРЕМЯ</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows?.map((t) => (
                <tr
                  key={t.id}
                  onClick={() => open(t.id)}
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") open(t.id);
                  }}
                  aria-label={`Открыть ${t.label}, ${t.sender}`}
                >
                  <td>
                    <div className="row-ident">
                      <span className="ticket-code">{t.label}</span>
                      {t.external_ids.length > 0 && (
                        <span className="external-code">
                          {t.external_ids.join(", ")}
                        </span>
                      )}
                    </div>
                    <strong>
                      {t.equipment?.client ?? t.sender.split(",")[0]}
                    </strong>
                    <div className="row-meta">
                      {sourceLabel(t.source)}
                      {t.message_count > 1 && ` · ${t.message_count} сообщения`}
                    </div>
                  </td>
                  <td>
                    {t.equipment ? (
                      <>
                        <strong className="equipment-inline">
                          {t.equipment.model}
                          <span>№ {t.equipment.serial}</span>
                        </strong>
                        <div className="row-meta">
                          <MapPin size={12} />
                          {t.equipment.address}
                        </div>
                      </>
                    ) : (
                      <>
                        <span className="unknown-text">
                          Машина не определена
                        </span>
                        <div className="row-meta">Нужен номер или адрес</div>
                      </>
                    )}
                  </td>
                  <td>
                    <div className="symptom-tags">
                      {t.symptom_labels.map((s) => (
                        <span key={s}>{s}</span>
                      ))}
                    </div>
                    <div className="row-meta clamp-text" title={t.text}>
                      {t.text}
                    </div>
                  </td>
                  <td>
                    <Status value={t.status} />
                    <div className="row-meta blocker-text">
                      {t.status === "ready"
                        ? "Карточка инженера подготовлена"
                        : t.status === "manager"
                          ? "Зафиксирован маршрут менеджеру"
                          : (t.blockers[0]?.next_action ?? "Подготовить карточку инженера")}
                    </div>
                    {t.warranty && (
                      <span className="micro-tag">Согласование</span>
                    )}
                  </td>
                  <td className="time-cell">
                    {dateTime(t.received_at, true)}
                    {t.duplicate_count > 0 && (
                      <div className="duplicate-tag">
                        Связи: {t.duplicate_count}
                      </div>
                    )}
                  </td>
                  <td>
                    <button
                      className="row-open"
                      onClick={(e) => {
                        e.stopPropagation();
                        open(t.id);
                      }}
                      aria-label={`Открыть ${t.label}`}
                    >
                      <ChevronRight size={17} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function NewMessageForm({
  onCreated,
  ticket,
}: {
  onCreated: (ticket: Ticket) => void;
  ticket?: Ticket;
}) {
  const draftId = ticket?.id ?? 0;
  const [sender, setSender] = useDraftState(draftId, "new-message", "sender", ticket?.messages[0].sender ?? "");
  const [text, setText] = useDraftState(draftId, "new-message", "text", ""),
    [channel, setChannel] = useDraftState(draftId, "new-message", "channel", "Ручной ввод"),
    [at, setAt] = useDraftState(draftId, "new-message", "at", "");
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const requestId = useRef(crypto.randomUUID());
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    const body = {
      sender,
      text,
      channel,
      request_id: requestId.current,
      ...(at ? { received_at: new Date(at).toISOString() } : {}),
    };
    try {
      if (ticket) {
        const result = await post<Ticket>(
            `/tickets/${ticket.id}/messages?revision=${ticket.revision}`,
            body,
          );
        clearDrafts(draftId, "new-message"); onCreated(result);
      }
      else {
        const result = await post<{ ticket: Ticket }>("/messages", body);
        clearDrafts(draftId, "new-message"); onCreated(result.ticket);
      }
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="form-stack" onSubmit={submit}>
      <p className="muted form-intro">
        {ticket
          ? "Новое сообщение сохранится в истории. Подготовку и подтверждения потребуется проверить заново."
          : "Вставьте исходный текст. Приложение предложит машину и вопросы для подготовки."}
      </p>
      <label>
        Кто обращается
        <input
          autoFocus
          required
          minLength={2}
          maxLength={200}
          value={sender}
          onChange={(e) => setSender(e.target.value)}
          placeholder="Кафе «Кедр», администратор"
        />
      </label>
      <div className="form-grid">
        <label>
          Канал
          <select value={channel} onChange={(e) => setChannel(e.target.value)}>
            <option>Ручной ввод</option>
            <option>Почта</option>
            <option>Звонок</option>
            <option>Мессенджер</option>
          </select>
        </label>
        <label>
          Дата и время <span className="optional">необязательно</span>
          <input
            type="datetime-local"
            value={at}
            onChange={(e) => setAt(e.target.value)}
          />
          <small>Если не указано, используется текущее время.</small>
        </label>
      </div>
      <label>
        Сообщение клиента
        <textarea
          aria-label="Сообщение клиента"
          required
          minLength={3}
          maxLength={10000}
          rows={6}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Например: на машине 205 вода появляется справа после приготовления…"
        />
      </label>
      {error && <Notice kind="error">{error}</Notice>}
      <div className="form-actions">
        <span className="muted">
          <ShieldCheck size={14} />
          Исходный текст сохраняется
        </span>
        <button className="button primary" disabled={busy} type="submit">
          {busy ? (
            <RefreshCw size={17} className="spin" />
          ) : (
            <Activity size={17} />
          )}
          {ticket ? "Сохранить уточнение" : "Сохранить и разобрать"}
        </button>
      </div>
    </form>
  );
}
