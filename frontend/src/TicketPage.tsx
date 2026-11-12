import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  ClipboardCheck,
  Copy,
  FileText,
  GitMerge,
  History,
  MapPin,
  Package,
  Plus,
  Printer,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Trash2,
  Truck,
  Wrench,
} from "lucide-react";
import { api, dateOnly, dateTime, sourceLabel } from "./api";
import type { EngineerCard, Equipment, Plan, Stock, Ticket } from "./types";
import {
  Empty,
  Modal,
  Notice,
  SectionTitle,
  Spinner,
  Status,
  Tick,
  errorText,
} from "./ui";
import { NewMessageForm } from "./App";
import { JournalPage } from "./pages";

type Perform = (
  endpoint: string,
  data?: Record<string, unknown>,
  method?: string,
) => Promise<boolean>;
type Tab = "message" | "questions" | "parts" | "card" | "audit";
const tabs = [
  { id: "message" as Tab, label: "Обращение и машина", icon: FileText },
  { id: "questions" as Tab, label: "Уточнения", icon: CircleHelp },
  { id: "parts" as Tab, label: "Выезд и детали", icon: Package },
  { id: "card" as Tab, label: "Карточка инженера", icon: ClipboardCheck },
  { id: "audit" as Tab, label: "Журнал", icon: History },
];

export default function TicketPage({
  id,
  onBack,
  onChange,
  notify,
  onSelect,
}: {
  id: number;
  onBack: () => void;
  onChange: () => void;
  notify: (text: string) => void;
  onSelect: (id: number) => void;
}) {
  const [ticket, setTicket] = useState<Ticket | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<Tab>("message"),
    [append, setAppend] = useState(false);
  const [equipment, setEquipment] = useState<Equipment[]>([]),
    [stock, setStock] = useState<Stock[]>([]);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    setTicket(null);
    setError("");
    setTab("message");
    api<Ticket>(`/tickets/${id}`)
      .then(setTicket)
      .catch((e) => setError(errorText(e)));
    api<Equipment[]>("/equipment")
      .then(setEquipment)
      .catch((e) => setError(errorText(e)));
  }, [id, refresh]);
  useEffect(() => {
    api<Stock[]>(
      "/inventory" +
        (ticket?.equipment ? "?model=" + ticket.equipment.model : ""),
    )
      .then(setStock)
      .catch((e) => setError(errorText(e)));
  }, [ticket?.revision, ticket?.equipment_id, id, busy]);
  const perform: Perform = async (endpoint, data = {}, method = "POST") => {
    if (!ticket) return false;
    setBusy(true);
    setError("");
    try {
      const path = `/tickets/${ticket.id}${endpoint}`;
      const updated = await api<Ticket>(
        path + (method === "DELETE" ? `?revision=${ticket.revision}` : ""),
        {
          method,
          ...(method === "DELETE"
            ? {}
            : { body: JSON.stringify({ revision: ticket.revision, ...data }) }),
        },
      );
      setTicket(updated);
      onChange();
      if (updated.id !== id) onSelect(updated.id);
      notify(
        endpoint === "/prepare"
          ? "Карточка инженера подготовлена"
          : endpoint === "/reserve"
            ? "Резерв подтверждён"
            : endpoint === "/release"
              ? "Резерв отменён"
              : "Изменения сохранены",
      );
      return true;
    } catch (e) {
      setError(errorText(e));
      return false;
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <button className="back-link" onClick={onBack}>
        <ArrowLeft size={16} />
        Очередь обращений
      </button>
      {error && (
        <div className="sticky-error">
          <Notice kind="error">
            {error}{" "}
            <button
              className="text-button"
              onClick={() => setRefresh((r) => r + 1)}
            >
              Обновить карточку
            </button>
          </Notice>
        </div>
      )}
      {!ticket ? (
        !error && <Spinner text="Открываем заявку…" />
      ) : (
        <>
          <div className="ticket-page-heading">
            <div>
              <div className="ticket-heading-meta">
                <span className="ticket-code">{ticket.label}</span>
                <Status value={ticket.readiness.status} />
                <span className="muted small">версия {ticket.revision}</span>
              </div>
              <h1>
                {ticket.equipment?.client ??
                  ticket.messages[0].sender.split(",")[0]}
              </h1>
              <p>
                <MapPin size={15} />
                {ticket.equipment?.address ??
                  "Адрес и машина требуют уточнения"}
                <span className="dot-divider">·</span>
                {ticket.symptom_labels.join(", ")}
              </p>
            </div>
            <div className="button-row">
              <button
                className="button secondary"
                onClick={() => setAppend(true)}
                disabled={busy}
              >
                <Plus size={16} />
                Добавить сообщение
              </button>
              <a
                className="button secondary icon-only"
                href={`/api/tickets/${id}/print`}
                target="_blank"
                rel="noreferrer"
                aria-label="Печать карточки инженера"
              >
                <Printer size={18} />
              </a>
            </div>
          </div>
          <div className="ticket-layout">
            <div className="ticket-workspace">
              <div className="tabs" role="tablist" aria-label="Разделы заявки">
                {tabs.map((item) => (
                  <button
                    key={item.id}
                    role="tab"
                    aria-selected={tab === item.id}
                    className={tab === item.id ? "active" : ""}
                    onClick={() => setTab(item.id)}
                  >
                    <item.icon size={15} />
                    {item.label}
                    {item.id === "questions" &&
                      ticket.readiness.questions.some((q) => !q.resolved) && (
                        <span className="tab-count">
                          {
                            ticket.readiness.questions.filter(
                              (q) => !q.resolved,
                            ).length
                          }
                        </span>
                      )}
                  </button>
                ))}
              </div>
              <div role="tabpanel" className="tab-content">
                {tab === "message" && (
                  <>
                    <Messages ticket={ticket} />
                    <Machine
                      key={`machine-${ticket.revision}`}
                      ticket={ticket}
                      equipment={equipment}
                      perform={perform}
                      busy={busy}
                    />
                    <Duplicates
                      key={`duplicates-${ticket.revision}`}
                      ticket={ticket}
                      perform={perform}
                      busy={busy}
                    />
                    {ticket.state === "manager" && (
                      <Notice kind="warning">
                        <strong>Зафиксирован маршрут менеджеру.</strong>{" "}
                        {ticket.data.manager_note}
                        <button
                          className="text-button"
                          disabled={busy}
                          onClick={() => void perform("/reopen")}
                        >
                          Вернуть в работу
                        </button>
                      </Notice>
                    )}
                    <button
                      className="button secondary next-step"
                      onClick={() => setTab("questions")}
                    >
                      К уточнениям <ArrowRight size={16} />
                    </button>
                  </>
                )}
                {tab === "questions" && (
                  <>
                    <Questions
                      key={`questions-${ticket.revision}`}
                      ticket={ticket}
                      perform={perform}
                      busy={busy}
                    />
                    <button
                      className="button secondary next-step"
                      onClick={() => setTab("parts")}
                    >
                      К плану выезда <ArrowRight size={16} />
                    </button>
                  </>
                )}
                {tab === "parts" && (
                  <Parts
                    key={`parts-${ticket.revision}`}
                    ticket={ticket}
                    stock={stock}
                    perform={perform}
                    busy={busy}
                  />
                )}
                {tab === "card" && (
                  <CardPreview
                    id={ticket.id}
                    revision={ticket.revision}
                    prepared={ticket.prepared_revision}
                  />
                )}
                {tab === "audit" && (
                  <JournalPage
                    version={ticket.revision + refresh}
                    onSelect={onSelect}
                    ticketId={ticket.id}
                  />
                )}
              </div>
            </div>
            <Readiness
              ticket={ticket}
              perform={perform}
              busy={busy}
              setTab={setTab}
            />
          </div>
          {append && (
            <Modal
              title="Добавить сообщение к заявке"
              close={() => setAppend(false)}
            >
              <NewMessageForm
                ticket={ticket}
                onCreated={(t) => {
                  setTicket(t);
                  setAppend(false);
                  onChange();
                  notify(
                    "Уточнение добавлено. Подготовку нужно проверить заново.",
                  );
                }}
              />
            </Modal>
          )}
        </>
      )}
    </>
  );
}

function Messages({ ticket }: { ticket: Ticket }) {
  return (
    <section className="panel padded">
      <SectionTitle number="01" title="Исходное обращение">
        <span className="tag">{ticket.messages.length} сообщ.</span>
      </SectionTitle>
      <div className="messages">
        {ticket.messages.map((m) => (
          <article className="message" key={m.id}>
            <div className="message-heading">
              <span className="message-avatar">
                {m.channel === "Звонок"
                  ? "ЗВ"
                  : m.channel === "Почта"
                    ? "ПЧ"
                    : "СБ"}
              </span>
              <div>
                <strong>{m.sender}</strong>
                <small>
                  {m.external_id ? m.external_id + " · " : ""}
                  {m.channel} · {dateTime(m.received_at)}
                </small>
              </div>
              <span className={`source-tag source-${m.source}`}>
                {sourceLabel(m.source)}
              </span>
            </div>
            <blockquote>{m.text}</blockquote>
            <span className="cell-source">Источник: {m.source_ref}</span>
            {m.analysis.llm_status?.includes("fallback") && (
              <Notice kind="warning">
                LLM не вернула пригодный ответ. Использован локальный разбор;
                проверьте поля вручную.
              </Notice>
            )}
            {m.analysis.llm_status === "not_configured" && (
              <Notice kind="warning">
                LLM включена, но ключ или модель не настроены. Использован
                локальный разбор.
              </Notice>
            )}
          </article>
        ))}
      </div>
      <div className="extraction-box">
        <div className="extraction-heading">
          <Sparkles size={16} />
          <strong>Результат разбора</strong>
          <span>требует подтверждения</span>
        </div>
        <div className="extracted-grid">
          <div>
            <small>Модель</small>
            <strong>{ticket.analysis.models.join(", ") || "Не указана"}</strong>
          </div>
          <div>
            <small>Серийный номер</small>
            <strong>{ticket.analysis.serials.join(", ") || "Не указан"}</strong>
          </div>
          <div>
            <small>Тема обращения</small>
            <strong>{ticket.symptom_labels.join(", ")}</strong>
          </div>
          <div>
            <small>Код на экране</small>
            <strong>{ticket.analysis.codes.join(", ") || "Не указан"}</strong>
          </div>
        </div>
        {Object.entries(ticket.analysis.facts).length > 0 && (
          <details className="technical-details">
            <summary>
              Извлечённые фрагменты и происхождение <ChevronDown size={14} />
            </summary>
            {ticket.analysis.evidence.map((f, i) => (
              <p key={i}>
                <code>{f.field}</code> — «{f.quote}»{" "}
                <span className="cell-source">
                  {f.source_ref}
                  {f.provider === "llm" ? " · LLM" : ""}
                </span>
              </p>
            ))}
          </details>
        )}
      </div>
      {ticket.analysis.unsafe_request && (
        <Notice kind="warning">
          Клиент просит самостоятельный ремонт. Инструкции по разборке не
          передавайте; уточните симптом и согласуйте безопасный сценарий по
          П-10.
        </Notice>
      )}
    </section>
  );
}

function Machine({
  ticket,
  equipment,
  perform,
  busy,
}: {
  ticket: Ticket;
  equipment: Equipment[];
  perform: Perform;
  busy: boolean;
}) {
  const [chosen, setChosen] = useState(ticket.equipment_id ?? "");
  const [resolution, setResolution] = useState(
    ticket.data.identity_resolution ?? "",
  );
  const [manual, setManual] = useState(false),
    [manager, setManager] = useState(false),
    [note, setNote] = useState("");
  const confirmed =
    ticket.data.equipment_confirmed && ticket.data.address_confirmed;
  const candidates = manual ? equipment : ticket.matching.candidates;
  const confirm = (e: FormEvent) => {
    e.preventDefault();
    void perform(
      "",
      {
        equipment_id: chosen,
        equipment_confirmed: true,
        address_confirmed: true,
        identity_resolution: resolution,
      },
      "PATCH",
    );
  };
  return (
    <section className="panel padded">
      <SectionTitle number="02" title="Конкретная машина">
        {confirmed && (
          <span className="badge status-ready">
            <Check size={13} />
            Подтверждена
          </span>
        )}
      </SectionTitle>
      <Notice
        kind={
          ticket.matching.status === "conflict" ||
          ticket.matching.status === "unknown"
            ? "warning"
            : "info"
        }
      >
        {ticket.matching.reason}
        {ticket.matching.client_typo &&
          " В названии клиента возможна опечатка."}
      </Notice>
      <form onSubmit={confirm} className="form-stack">
        <div className="candidate-list">
          {candidates.map((eq) => (
            <label
              className={`candidate ${chosen === eq.id ? "selected" : ""}`}
              key={eq.id}
            >
              <input
                type="radio"
                name="machine"
                value={eq.id}
                checked={chosen === eq.id}
                onChange={() => setChosen(eq.id)}
              />
              <div className="candidate-body">
                <div>
                  <strong>{eq.model}</strong>
                  <span className="serial">№ {eq.serial}</span>
                  <span className="cell-source">{eq.id}</span>
                </div>
                <span>{eq.client}</span>
                <small>
                  <MapPin size={12} />
                  {eq.address}
                </small>
                {"reasons" in eq && (
                  <div className="match-reasons">
                    {(eq.reasons as string[]).map((r) => (
                      <span key={r}>
                        <Check size={11} />
                        {r}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </label>
          ))}
        </div>
        {!candidates.length && (
          <p className="muted">
            Подходящей машины нет среди кандидатов. Сверьте шильдик и договор;
            можно проверить весь реестр.
          </p>
        )}
        <button
          className="text-button align-start"
          type="button"
          onClick={() => setManual((v) => !v)}
        >
          <Search size={14} />
          {manual
            ? "Вернуться к кандидатам"
            : "Выбрать вручную из всего реестра"}
        </button>
        {(["conflict", "unknown"].includes(ticket.matching.status) ||
          (chosen &&
            !ticket.matching.candidates.some((c) => c.id === chosen))) && (
          <label>
            Как разрешено противоречие?
            <textarea
              aria-label="Как разрешено противоречие?"
              rows={2}
              value={resolution}
              onChange={(e) => setResolution(e.target.value)}
              placeholder="Кто подтвердил номер, модель и договор; что было ошибкой в исходном сообщении"
            />
          </label>
        )}
        {chosen && (
          <button
            className="button primary align-start"
            disabled={
              busy ||
              (confirmed &&
                chosen === ticket.equipment_id &&
                resolution === (ticket.data.identity_resolution ?? ""))
            }
            type="submit"
          >
            <CheckCircle2 size={17} />
            Подтвердить машину и адрес
          </button>
        )}
      </form>
      {ticket.equipment && (
        <div className="history-box">
          <div>
            <History size={16} />
            <strong>Доступная история</strong>
            <span>{dateOnly(ticket.equipment.last_visit)}</span>
          </div>
          <p>{ticket.equipment.history || "В реестре нет записи о визитах."}</p>
          <span className="cell-source">
            {ticket.equipment.source_ref} · установка{" "}
            {dateOnly(ticket.equipment.installed_at)}
          </span>
        </div>
      )}
      {!ticket.equipment && ticket.state !== "manager" && (
        <div className="manager-route">
          <button className="text-button" onClick={() => setManager((v) => !v)}>
            Машины нет в реестре — маршрут менеджеру <ArrowRight size={14} />
          </button>
          {manager && (
            <form
              className="form-stack"
              onSubmit={(e) => {
                e.preventDefault();
                void perform("/manager", { note });
              }}
            >
              <label>
                Сведения для передачи
                <textarea
                  aria-label="Сведения для передачи"
                  required
                  minLength={5}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Модель и серийный номер либо что ещё нужно запросить; ответственный менеджер"
                />
              </label>
              <Notice>
                Это фиксация маршрута внутри пилота. Диспетчер передаёт сведения
                менеджеру самостоятельно.
              </Notice>
              <button
                className="button secondary align-start"
                type="submit"
                disabled={busy}
              >
                Зафиксировать маршрут менеджеру
              </button>
            </form>
          )}
        </div>
      )}
    </section>
  );
}

function Duplicates({
  ticket,
  perform,
  busy,
}: {
  ticket: Ticket;
  perform: Perform;
  busy: boolean;
}) {
  const [selected, setSelected] = useState<number | null>(null),
    [reason, setReason] = useState("");
  const [separate, setSeparate] = useState(
    ticket.data.duplicate_resolution ?? "",
  );
  const [expanded, setExpanded] = useState(false);
  const duplicate = ticket.duplicates.find((d) => d.id === selected);
  if (!ticket.duplicates.length) return null;
  return (
    <section className="panel padded">
      <SectionTitle title="Повторы и уточнения">
        <span className="count-pill">{ticket.duplicates.length}</span>
      </SectionTitle>
      <p className="muted small">
        Похожие обращения не объединяются автоматически. Проверьте, совпадают ли
        машина и проблема.
      </p>
      <div className="duplicate-list">
        {ticket.duplicates.slice(0, expanded ? undefined : 3).map((d) => (
          <article key={d.id}>
            <div>
              <strong>
                {d.label}
                {d.external_id && ` · ${d.external_id}`}
              </strong>
              <p>{d.text}</p>
              <small>{d.reason}</small>
            </div>
            <button
              className="button secondary compact"
              disabled={busy}
              onClick={() => setSelected(d.id)}
            >
              <GitMerge size={14} />
              Объединить
            </button>
          </article>
        ))}
      </div>
      {ticket.duplicates.length > 3 && (
        <button className="text-button" onClick={() => setExpanded((v) => !v)}>
          {expanded ? "Свернуть" : "Показать все связи"}
        </button>
      )}
      <form
        className="form-stack separated"
        onSubmit={(e) => {
          e.preventDefault();
          void perform("", { duplicate_resolution: separate }, "PATCH");
        }}
      >
        <label>
          Если это отдельная проблема — объясните почему
          <textarea
            aria-label="Если это отдельная проблема — объясните почему"
            rows={2}
            value={separate}
            minLength={5}
            required
            onChange={(e) => setSeparate(e.target.value)}
            placeholder="Например: новая жалоба на пар, течь оформлена отдельно"
          />
        </label>
        <button
          className="button secondary align-start"
          type="submit"
          disabled={busy}
        >
          Сохранить как отдельную проблему
        </button>
      </form>
      {duplicate && (
        <Modal
          title={`Объединить с ${duplicate.label}`}
          close={() => setSelected(null)}
        >
          <form
            className="form-stack"
            onSubmit={async (e) => {
              e.preventDefault();
              if (
                await perform("/merge", {
                  target_id: duplicate.id,
                  target_revision: duplicate.revision,
                  reason,
                })
              )
                setSelected(null);
            }}
          >
            <Notice kind="warning">
              Все сообщения {ticket.label} добавятся в {duplicate.label}.
              Подготовку, ответы и согласование основной заявки потребуется
              проверить заново.
            </Notice>
            <label>
              Почему это одна проблема?
              <textarea
                aria-label="Почему это одна проблема?"
                required
                minLength={5}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Клиент подтвердил: уточнение той же течи на той же машине"
              />
            </label>
            <button className="button primary" type="submit" disabled={busy}>
              <GitMerge size={17} />
              Объединить сообщения
            </button>
          </form>
        </Modal>
      )}
    </section>
  );
}

function Questions({
  ticket,
  perform,
  busy,
}: {
  ticket: Ticket;
  perform: Perform;
  busy: boolean;
}) {
  const [symptom, setSymptom] = useState(
    ticket.data.symptom ?? ticket.messages[0].text,
  );
  const [confirmed, setConfirmed] = useState(
    ticket.data.symptom_confirmed ?? false,
  );
  const [issues, setIssues] = useState(ticket.analysis.symptoms);
  const [answers, setAnswers] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      ticket.readiness.questions.map((q) => [q.key, q.answer || q.suggested]),
    ),
  );
  const save = (e: FormEvent) => {
    e.preventDefault();
    void perform(
      "",
      { symptom, symptom_confirmed: confirmed, answers, issue_types: issues },
      "PATCH",
    );
  };
  return (
    <section className="panel padded">
      <SectionTitle number="03" title="Уточнения и подтверждения">
        <span className="tag">
          {ticket.readiness.questions.filter((q) => q.resolved).length} /{" "}
          {ticket.readiness.questions.length}
        </span>
      </SectionTitle>
      <p className="muted small">
        Фрагменты из сообщения подставлены для проверки. Сохранение фиксирует
        ответы диспетчера.
      </p>
      <form onSubmit={save} className="form-stack">
        <div className="issue-editor" role="group" aria-label="Типы симптомов">
          <strong>Тип симптома</strong>
          <div>
            {Object.entries({
              leak: "Течь",
              flow: "Слабый поток",
              error: "Ошибка / нет кофе",
              noise: "Посторонний шум",
              steam: "Слабый пар",
              maintenance: "Обслуживание",
              request: "Запрос инструкции",
              unknown: "Нужно уточнить",
            }).map(([key, label]) => (
              <label className="checkbox-label" key={key}>
                <input
                  type="checkbox"
                  checked={issues.includes(key)}
                  onChange={(e) =>
                    setIssues((current) =>
                      e.target.checked
                        ? key === "unknown"
                          ? ["unknown"]
                          : [...current.filter((v) => v !== "unknown"), key]
                        : current.length === 1
                          ? ["unknown"]
                          : current.filter((v) => v !== key),
                    )
                  }
                />
                {label}
              </label>
            ))}
          </div>
          <small>
            Если разбор ошибся, исправьте тип и сохраните форму: обязательные
            вопросы обновятся.
          </small>
        </div>
        <label>
          Наблюдаемый симптом
          <textarea
            aria-label="Наблюдаемый симптом"
            value={symptom}
            onChange={(e) => setSymptom(e.target.value)}
            required
            minLength={8}
            maxLength={3000}
            rows={3}
          />
          <small>
            Что происходит с машиной. Не назначайте причину по описанию или
            прошлому ремонту.
          </small>
        </label>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          Описание симптома проверено диспетчером
        </label>
        {ticket.readiness.questions.map((q, i) => (
          <div className="question-field" key={q.key}>
            <span className={`question-index ${q.resolved ? "done" : ""}`}>
              {q.resolved ? <Check size={14} /> : i + 1}
            </span>
            <label>
              {q.question}
              <input
                aria-label={q.question}
                value={answers[q.key] ?? ""}
                onChange={(e) =>
                  setAnswers((a) => ({ ...a, [q.key]: e.target.value }))
                }
                maxLength={1000}
                placeholder={q.hint}
              />
              <small>
                {q.suggested && !q.answer
                  ? `Из сообщения: «${q.suggested}». Проверьте перед сохранением.`
                  : q.hint}
              </small>
            </label>
          </div>
        ))}
        {ticket.readiness.questions.length === 0 && (
          <Notice kind="success">
            Для этого типа обращения правило П-5 не требует дополнительных
            полей. Подтвердите симптом и план выезда.
          </Notice>
        )}
        {ticket.error_codes.map((c) => (
          <Notice key={c.code} kind={c.known ? "info" : "warning"}>
            <strong>{c.code}</strong> — {c.meaning}.{" "}
            {c.known && "Это сработавшая проверка, а не диагноз детали."}
          </Notice>
        ))}
        <button
          className="button primary align-start"
          type="submit"
          disabled={busy}
        >
          <CheckCircle2 size={17} />
          Сохранить ответы и симптом
        </button>
      </form>
    </section>
  );
}

function Parts({
  ticket,
  stock,
  perform,
  busy,
}: {
  ticket: Ticket;
  stock: Stock[];
  perform: Perform;
  busy: boolean;
}) {
  const [purpose, setPurpose] = useState(ticket.data.purpose ?? "diagnostic"),
    [note, setNote] = useState(ticket.data.purpose_note ?? "");
  const [visit, setVisit] = useState(ticket.data.visit_date ?? ""),
    [uncertainties, setUncertainties] = useState(
      ticket.data.uncertainties ?? "",
    );
  const [confirmed, setConfirmed] = useState(
    ticket.data.plan_confirmed ?? false,
  );
  const [sku, setSku] = useState(""),
    [warehouse, setWarehouse] = useState(
      ticket.equipment?.address.startsWith("Тула") ? "Тула" : "Москва",
    ),
    [quantity, setQuantity] = useState(1);
  const [showAll, setShowAll] = useState(false);
  const skus = [
    ...new Set(stock.filter((s) => showAll || s.compatible).map((s) => s.sku)),
  ];
  const selected = stock.find(
    (s) => s.sku === sku && s.warehouse === warehouse,
  );
  const save = (e: FormEvent) => {
    e.preventDefault();
    void perform(
      "",
      {
        purpose,
        purpose_note: note,
        visit_date: visit || null,
        uncertainties,
        plan_confirmed: confirmed,
      },
      "PATCH",
    );
  };
  return (
    <>
      <section className="panel padded">
        <SectionTitle number="04" title="Цель визита" />
        <form onSubmit={save} className="form-stack">
          <div className="purpose-options">
            {[
              {
                id: "diagnostic",
                label: "Диагностика",
                text: "Осмотр и проверка гипотез",
              },
              {
                id: "repair",
                label: "Ремонт",
                text: "С подготовленными деталями",
              },
              {
                id: "maintenance",
                label: "Обслуживание",
                text: "Плановая замена",
              },
            ].map((p) => (
              <label className={purpose === p.id ? "selected" : ""} key={p.id}>
                <input
                  type="radio"
                  name="purpose"
                  checked={purpose === p.id}
                  value={p.id}
                  onChange={() => setPurpose(p.id)}
                />
                <strong>{p.label}</strong>
                <small>{p.text}</small>
              </label>
            ))}
          </div>
          <label>
            Что должен сделать инженер?
            <textarea
              aria-label="Что должен сделать инженер?"
              required
              minLength={8}
              maxLength={2000}
              rows={3}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Проверить место течи и соединения. Деталь определить после осмотра."
            />
          </label>
          <label>
            Плановая дата визита{" "}
            <span className="optional">нужна при перевозе</span>
            <input
              type="date"
              value={visit}
              onChange={(e) => setVisit(e.target.value)}
            />
          </label>
          <label>
            Оставшиеся неопределённости
            <textarea
              aria-label="Оставшиеся неопределённости"
              rows={2}
              value={uncertainties}
              onChange={(e) => setUncertainties(e.target.value)}
              maxLength={3000}
              placeholder="Что ещё неизвестно инженеру; каких документов или наблюдений нет"
            />
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            Цель и состав выезда согласованы; ограничения диагностики понятны
          </label>
          <button
            className="button primary align-start"
            disabled={busy}
            type="submit"
          >
            <Check size={17} />
            Сохранить план выезда
          </button>
        </form>
      </section>
      <section className="panel padded">
        <SectionTitle number="05" title="Детали и склад получения">
          <span className="tag">{ticket.plans.length} поз.</span>
        </SectionTitle>
        <Notice>
          Наличие не доказывает необходимость замены. Причину и нужную деталь
          определяет инженер. Выбор детали — решение подготовки, а не
          автоматический диагноз.
        </Notice>
        {ticket.plans.length > 0 ? (
          <>
            <div className="plan-list">
              {ticket.plans.map((plan) => (
                <div className="plan-item" key={plan.id}>
                  <div className="plan-main">
                    <span className="part-symbol">
                      <Package size={18} />
                    </span>
                    <div>
                      <strong>
                        {plan.sku} · {plan.name}
                      </strong>
                      <small>
                        {plan.warehouse} · {plan.quantity} шт.
                      </small>
                    </div>
                    <span
                      className={`badge ${plan.reserved_quantity === plan.quantity ? "status-ready" : "status-blocked"}`}
                    >
                      {plan.reserved_quantity === plan.quantity
                        ? "В резерве"
                        : "Не зарезервировано"}
                    </span>
                    <button
                      className="icon-button danger"
                      aria-label={`Удалить ${plan.sku}`}
                      disabled={busy}
                      onClick={() =>
                        void perform(`/parts/${plan.id}`, {}, "DELETE")
                      }
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                  {plan.transfer_required && (
                    <TransferForm plan={plan} busy={busy} perform={perform} />
                  )}
                </div>
              ))}
            </div>
            <div className="button-row reservation-actions">
              <button
                className="button primary"
                disabled={busy}
                onClick={() => void perform("/reserve")}
              >
                <ShieldCheck size={17} />
                Подтвердить резерв
              </button>
              <button
                className="button secondary"
                disabled={
                  busy || !ticket.plans.some((p) => p.reserved_quantity > 0)
                }
                onClick={() => void perform("/release")}
              >
                Отменить резерв
              </button>
            </div>
          </>
        ) : (
          <div className="inline-empty">
            <Package size={22} />
            <div>
              <strong>Детали пока не запланированы</strong>
              <p>Для диагностики без деталей подтвердите это в плане выезда.</p>
            </div>
          </div>
        )}
        {!ticket.equipment ? (
          <Notice kind="warning">
            Сначала выберите конкретную машину, чтобы проверить совместимость
            деталей.
          </Notice>
        ) : (
          <form
            className="add-part-form"
            onSubmit={(e) => {
              e.preventDefault();
              void perform("/parts", { sku, warehouse, quantity });
            }}
          >
            <div className="catalog-heading">
              <h3>Добавить из справочника</h3>
              <label className="checkbox-label small">
                <input
                  type="checkbox"
                  checked={showAll}
                  onChange={(e) => setShowAll(e.target.checked)}
                />
                Показать несовместимые
              </label>
            </div>
            <label>
              Деталь
              <select
                aria-label="Деталь"
                value={sku}
                required
                onChange={(e) => setSku(e.target.value)}
              >
                <option value="">
                  Выберите деталь для {ticket.equipment.model}
                </option>
                {skus.map((code) => {
                  const part = stock.find((s) => s.sku === code)!;
                  return (
                    <option key={code} value={code}>
                      {code} · {part.name}
                      {part.compatible ? "" : " · несовместима"}
                    </option>
                  );
                })}
              </select>
            </label>
            <div className="form-grid">
              <label>
                Склад получения
                <select
                  aria-label="Склад получения"
                  value={warehouse}
                  onChange={(e) => setWarehouse(e.target.value)}
                >
                  <option>Москва</option>
                  <option>Тула</option>
                </select>
              </label>
              <label>
                Количество
                <input
                  type="number"
                  required
                  min={1}
                  max={100}
                  value={quantity}
                  onChange={(e) => setQuantity(Number(e.target.value))}
                />
              </label>
            </div>
            {selected && (
              <div
                className={`stock-summary ${selected.free === 0 ? "stock-empty" : ""}`}
              >
                <Package size={18} />
                <span>
                  На складе: <strong>{selected.on_hand}</strong> · исходный
                  резерв: <strong>{selected.external_reserved}</strong> · пилот:{" "}
                  <strong>{selected.pilot_reserved}</strong>
                </span>
                <strong>Свободно {selected.free}</strong>
              </div>
            )}
            {selected && !selected.compatible && (
              <Notice kind="error">
                Деталь несовместима с моделью {ticket.equipment.model}.
                Добавление запрещено.
              </Notice>
            )}
            <button
              type="submit"
              className="button secondary align-start"
              disabled={busy || !selected || !selected.compatible}
            >
              <Plus size={16} />
              Добавить в план
            </button>
          </form>
        )}
      </section>
    </>
  );
}

function TransferForm({
  plan,
  perform,
  busy,
}: {
  plan: Plan;
  perform: Perform;
  busy: boolean;
}) {
  const [date, setDate] = useState(plan.available_on ?? ""),
    [note, setNote] = useState(plan.transfer_note);
  return (
    <div className="transfer-box">
      <div>
        <Truck size={17} />
        <strong>Деталь в другом городе</strong>
      </div>
      <p>
        Перевоз — один рабочий день. Склад-источник: {plan.warehouse}. Для
        готовности нужны согласованный срок получения и дата визита.
      </p>
      {plan.transfer_confirmed ? (
        <div className="transfer-agreed">
          <CheckCircle2 size={16} />
          <span>
            Перевоз согласован к {dateOnly(plan.available_on)} ·{" "}
            {plan.transfer_note}
          </span>
        </div>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void perform(`/parts/${plan.id}/transfer`, {
              available_on: date,
              note,
            });
          }}
          className="form-stack"
        >
          <label>
            Согласованная дата получения
            <input
              type="date"
              required
              value={date}
              onChange={(e) => setDate(e.target.value)}
            />
          </label>
          <label>
            Кто и как подтвердил перевоз
            <input
              required
              minLength={5}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Ответственный, подтверждение склада и место получения"
            />
          </label>
          <button
            className="button secondary compact align-start"
            disabled={busy}
            type="submit"
          >
            Согласовать перевоз
          </button>
        </form>
      )}
    </div>
  );
}

function Readiness({
  ticket,
  perform,
  busy,
  setTab,
}: {
  ticket: Ticket;
  perform: Perform;
  busy: boolean;
  setTab: (tab: Tab) => void;
}) {
  const [name, setName] = useState(""),
    [note, setNote] = useState(""),
    [approvalOpen, setApprovalOpen] = useState(false);
  const readiness = ticket.readiness;
  const checklistTab = (key: string): Tab =>
    ["registry", "identity", "identity_conflict", "duplicates"].includes(key)
      ? "message"
      : ["symptom", "questions", "safe_actions"].includes(key)
        ? "questions"
        : "parts";
  return (
    <aside className="readiness-sidebar">
      <section
        className={`panel readiness-panel ${readiness.ready ? "is-ready" : ""}`}
      >
        <div className="readiness-top">
          <span className="readiness-icon">
            {readiness.ready ? (
              <CheckCircle2 size={24} />
            ) : (
              <ClipboardCheck size={24} />
            )}
          </span>
          <span className="mini-label">ПРОВЕРКА ГОТОВНОСТИ</span>
          <h2>
            {readiness.ready
              ? "Можно выезжать"
              : readiness.can_prepare
                ? "Всё для подготовки есть"
                : "Подготовим без пробелов"}
          </h2>
          <p>
            {readiness.ready
              ? "Карточка соответствует текущей версии заявки."
              : readiness.can_prepare
                ? "Подтвердите подготовку и передайте карточку инженеру."
                : "Сначала устраните препятствия, затем подтвердите выезд."}
          </p>
          <div className="readiness-progress">
            <span
              style={{
                width: `${(readiness.passed / readiness.total) * 100}%`,
              }}
            />
          </div>
          <div className="progress-caption">
            <strong>
              {readiness.passed} из {readiness.total}
            </strong>
            <span>проверок пройдено</span>
          </div>
        </div>
        <div className="readiness-checks">
          {readiness.checks.map((c) => (
            <button
              key={c.key}
              className={`readiness-check ${c.passed ? "passed" : ""}`}
              onClick={() => setTab(checklistTab(c.key))}
              title={`${c.rule}: ${c.detail}`}
            >
              <Tick passed={c.passed} />
              <span>
                {c.label}
                <small>{c.rule}</small>
              </span>
              {!c.passed && <ArrowRight size={12} />}
            </button>
          ))}
        </div>
        <div className="readiness-actions">
          <button
            className="button primary"
            disabled={busy || !readiness.can_prepare || readiness.ready}
            onClick={() => void perform("/prepare")}
          >
            {busy ? (
              <RefreshCw size={17} className="spin" />
            ) : (
              <CheckCircle2 size={18} />
            )}
            {readiness.ready ? "Выезд подготовлен" : "Подготовить выезд"}
          </button>
          <button className="button secondary" onClick={() => setTab("card")}>
            <FileText size={17} />
            Предпросмотр карточки
          </button>
          {!readiness.can_prepare && (
            <small>
              Препятствий: {readiness.blockers.length}. Нажмите на пункт, чтобы
              перейти к исправлению.
            </small>
          )}
        </div>
      </section>
      {readiness.warranty.required && (
        <section className="warranty-card">
          <div>
            <ShieldCheck size={19} />
            <h3>Требуется согласование</h3>
          </div>
          <p>{readiness.warranty.reason}</p>
          {ticket.data.approval?.revision === ticket.revision ? (
            <div className="approval-record">
              <CheckCircle2 size={16} />
              <span>
                {ticket.data.approval.name}
                <small>{ticket.data.approval.note}</small>
              </span>
            </div>
          ) : (
            <>
              <button
                className="text-button"
                disabled={busy}
                onClick={() => setApprovalOpen((v) => !v)}
              >
                Записать согласование <ArrowRight size={13} />
              </button>
              {approvalOpen && (
                <form
                  className="form-stack"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void perform("/approval", { name, note });
                  }}
                >
                  <label>
                    Старший инженер
                    <input
                      required
                      minLength={3}
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="Фамилия и имя"
                    />
                  </label>
                  <label>
                    Основание согласования
                    <textarea
                      required
                      minLength={5}
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      rows={2}
                      placeholder="Согласованный план, дата и способ подтверждения"
                    />
                  </label>
                  <p className="muted small">
                    Пилот фиксирует полученное согласование. Проверки полномочий
                    сотрудника нет.
                  </p>
                  <button
                    type="submit"
                    className="button secondary compact"
                    disabled={busy}
                  >
                    Сохранить согласование
                  </button>
                </form>
              )}
            </>
          )}
        </section>
      )}
      <div className="preparation-note">
        <ShieldCheck size={16} />
        <p>
          Изменение заявки снимает подготовку и согласование. Перед выездом
          проверяйте актуальную карточку.
        </p>
      </div>
    </aside>
  );
}

function CardPreview({
  id,
  revision,
  prepared,
}: {
  id: number;
  revision: number;
  prepared: number | null;
}) {
  const [card, setCard] = useState<EngineerCard | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    api<EngineerCard>(`/tickets/${id}/card`)
      .then(setCard)
      .catch((e) => setError(errorText(e)));
  }, [id, revision, prepared]);
  if (error) return <Notice kind="error">{error}</Notice>;
  if (!card) return <Spinner text="Формируем карточку инженера…" />;
  return (
    <>
      <div className="preview-toolbar">
        <span className="muted small">
          Актуальное состояние · версия {card.revision}
        </span>
        <a
          className="button secondary"
          href={`/api/tickets/${id}/print`}
          target="_blank"
          rel="noreferrer"
        >
          <Printer size={16} />
          Печать / PDF
        </a>
      </div>
      <article className="engineer-paper">
        <div className="paper-brand">
          <CoffeeLogo />
          <span>КОФЕСЕРВИС РЕГИОН</span>
          <span>{card.label}</span>
        </div>
        <h2>Задание сервисному инженеру</h2>
        <div className={`paper-status ${card.ready ? "ready" : ""}`}>
          {card.ready ? "ГОТОВО К ВЫЕЗДУ" : "ЧЕРНОВИК · ВЫЕЗД НЕ ПОДГОТОВЛЕН"}
        </div>
        <h3>{card.equipment?.client ?? "Машина не определена"}</h3>
        <p>{card.equipment?.address ?? "Адрес не подтверждён"}</p>
        <div className="paper-equipment">
          <span>
            Модель <strong>{card.equipment?.model ?? "—"}</strong>
          </span>
          <span>
            Серийный № <strong>{card.equipment?.serial ?? "—"}</strong>
          </span>
          <span>
            Визит <strong>{dateOnly(card.visit_date)}</strong>
          </span>
        </div>
        <section>
          <h4>
            Симптом {card.symptom_confirmed && <CheckCircle2 size={13} />}
          </h4>
          <p>{card.symptom || "Описание не подтверждено."}</p>
        </section>
        <section>
          <h4>Подтверждённые сведения</h4>
          {card.confirmed.length ? (
            <ul>
              {card.confirmed.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          ) : (
            <p className="muted">Подтверждений пока нет.</p>
          )}
        </section>
        <section>
          <h4>Доступная история</h4>
          <span className="muted small">
            {dateOnly(card.history.date)} · {card.history.source_ref}
          </span>
          <p>{card.history.text}</p>
        </section>
        <section>
          <h4>Детали и склад получения</h4>
          {card.parts.length ? (
            <div className="table-scroll">
              <table className="paper-table">
                <thead>
                  <tr>
                    <th>Деталь</th>
                    <th>Кол.</th>
                    <th>Склад</th>
                    <th>Резерв</th>
                  </tr>
                </thead>
                <tbody>
                  {card.parts.map((p) => (
                    <tr key={p.id}>
                      <td>
                        {p.sku} · {p.name}
                      </td>
                      <td>{p.quantity}</td>
                      <td>
                        {p.warehouse}
                        {p.transfer_required && (
                          <small>Перевоз: {dateOnly(p.available_on)}</small>
                        )}
                      </td>
                      <td>
                        {p.reserved_quantity === p.quantity
                          ? "Подтверждён"
                          : "Не подтверждён"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p>Детали не запланированы.</p>
          )}
        </section>
        <section>
          <h4>Цель визита</h4>
          <strong>{card.purpose}</strong>
          <p>{card.purpose_note || "План не согласован."}</p>
        </section>
        <section>
          <h4>Согласование</h4>
          <p>{card.warranty.reason}</p>
          {card.approval && (
            <p>
              {card.approval.name}: {card.approval.note}
            </p>
          )}
        </section>
        <section>
          <h4>Оставшиеся неопределённости</h4>
          <ul>
            {card.uncertainties.map((u, i) => (
              <li key={i}>{u}</li>
            ))}
          </ul>
        </section>
        {card.blockers.length > 0 && (
          <section className="paper-blockers">
            <h4>Препятствия к выезду</h4>
            <ul>
              {card.blockers.map((b) => (
                <li key={b.key}>{b.label}</li>
              ))}
            </ul>
          </section>
        )}
        <footer>
          Версия {card.revision} ·{" "}
          {card.prepared_at
            ? `Подготовлено ${dateTime(card.prepared_at)}`
            : "Подготовка не подтверждена"}
          <br />
          Причину неисправности определяет инженер на осмотре.
        </footer>
      </article>
    </>
  );
}
function CoffeeLogo() {
  return <Wrench size={17} />;
}
