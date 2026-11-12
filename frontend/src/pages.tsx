import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  Database,
  FileSpreadsheet,
  FlaskConical,
  History,
  Package,
  RefreshCw,
  Search,
  ShieldCheck,
  UploadCloud,
} from "lucide-react";
import { api, dateTime, post, sourceLabel } from "./api";
import type { Audit, ImportReport, Stock } from "./types";
import { Empty, Notice, Spinner, errorText } from "./ui";

export function ImportPage({
  version,
  onChange,
  notify,
  openQueue,
}: {
  version: number;
  onChange: () => void;
  notify: (text: string) => void;
  openQueue: () => void;
}) {
  const [reports, setReports] = useState<ImportReport[] | null>(null),
    [current, setCurrent] = useState<ImportReport | null>(null);
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(""),
    [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    api<ImportReport[]>("/imports")
      .then(setReports)
      .catch((e) => setError(errorText(e)));
  }, [version]);
  const run = async (action: "case" | "file" | "demo", file?: File) => {
    setBusy(action);
    setError("");
    try {
      if (action === "demo") {
        const result = await post<{ created: number; skipped: number }>(
          "/imports/demo",
          {},
        );
        notify(
          `Демо: добавлено ${result.created}, уже существовало ${result.skipped}`,
        );
      } else {
        let report: ImportReport;
        if (file) {
          if (file.size > 10 * 1024 * 1024)
            throw new Error("Максимальный размер файла — 10 МБ.");
          const form = new FormData();
          form.append("file", file);
          report = await api<ImportReport>("/imports/excel", {
            method: "POST",
            body: form,
          });
        } else report = await post<ImportReport>("/imports/case", {});
        setCurrent(report);
        if (report.status === "success")
          notify(
            report.duplicate_file
              ? "Этот файл уже импортирован. Новых обращений нет."
              : "Импорт завершён. Можно открыть очередь.",
          );
      }
      onChange();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
      if (input.current) input.current.value = "";
    }
  };
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">ИСТОЧНИКИ</div>
          <h1>Импорт данных</h1>
          <p>Excel превращается в проверяемую очередь обращений.</p>
        </div>
        <button className="button secondary" onClick={openQueue}>
          Открыть очередь <ArrowRight size={16} />
        </button>
      </div>
      <div className="import-layout">
        <section className="panel import-panel">
          <div className="panel-heading">
            <FileSpreadsheet size={20} />
            <div>
              <h2>Загрузить Excel</h2>
              <p>Все четыре листа — одним файлом .xlsx</p>
            </div>
          </div>
          <div
            className={`drop-zone ${dragging ? "dragging" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              if (!busy && e.dataTransfer.files[0])
                void run("file", e.dataTransfer.files[0]);
            }}
          >
            <span className="upload-icon">
              <UploadCloud size={32} strokeWidth={1.4} />
            </span>
            <h3>Перетащите файл сюда</h3>
            <p>или выберите его на компьютере · до 10 МБ</p>
            <input
              ref={input}
              className="visually-hidden"
              type="file"
              accept=".xlsx"
              aria-label="Выбрать Excel"
              onChange={(e) => {
                if (e.target.files?.[0]) void run("file", e.target.files[0]);
              }}
            />
            <button
              className="button primary"
              disabled={!!busy}
              onClick={() => input.current?.click()}
            >
              Выбрать .xlsx
            </button>
          </div>
          <div className="import-template">
            <FileSpreadsheet size={22} />
            <div>
              <strong>Предоставленный файл кейса</strong>
              <small>23 обращения · 12 машин · 10 деталей · 10 правил</small>
            </div>
            <button
              className="button secondary compact"
              disabled={!!busy}
              onClick={() => void run("case")}
            >
              Импортировать файл кейса
            </button>
          </div>
          {busy && (
            <Spinner
              text={
                busy === "demo"
                  ? "Добавляем демонстрационные сообщения…"
                  : "Проверяем листы и импортируем…"
              }
            />
          )}
        </section>
        <div className="import-info">
          <section className="panel padded">
            <span className="mini-label">ПРОВЕРКА ПЕРЕД ЗАПИСЬЮ</span>
            <h3>Ничего не теряется</h3>
            <ul className="feature-list">
              <li>
                <CheckCircle2 size={16} />
                Проверка структуры и значений
              </li>
              <li>
                <CheckCircle2 size={16} />
                Ссылки на исходные ячейки
              </li>
              <li>
                <CheckCircle2 size={16} />
                Повтор файла без дублей
              </li>
              <li>
                <CheckCircle2 size={16} />
                Ошибка отменяет весь импорт
              </li>
            </ul>
            <p className="muted small">
              Листы: Заявки, Оборудование, Запчасти, Правила. Исправьте ошибки в
              Excel и загрузите исправленный файл.
            </p>
          </section>
          <section className="demo-card">
            <FlaskConical size={19} />
            <h3>Отдельная демонстрация</h3>
            <p>
              Три дополнительных сообщения. Помечаются «Демонстрация»,
              используют справочники кейса.
            </p>
            <button
              className="text-button"
              disabled={!!busy}
              onClick={() => void run("demo")}
            >
              Добавить демо-примеры <ArrowRight size={14} />
            </button>
          </section>
        </div>
      </div>
      {error && <Notice kind="error">{error}</Notice>}
      {current && <Report report={current} highlighted />}
      <div className="subheading">
        <h2>История импорта</h2>
        <span className="muted">{reports?.length ?? "—"} загрузок</span>
      </div>
      {reports === null && !error ? (
        <Spinner />
      ) : reports?.length === 0 ? (
        <div className="panel">
          <Empty
            title="Загрузок пока нет"
            text="После импорта здесь появятся результаты проверки и ошибки по строкам."
          />
        </div>
      ) : (
        reports
          ?.filter((r) => r.id !== current?.id)
          .map((report) => <Report key={report.id} report={report} />)
      )}
    </>
  );
}

function Report({
  report,
  highlighted = false,
}: {
  report: ImportReport;
  highlighted?: boolean;
}) {
  return (
    <section
      className={`panel import-report ${highlighted ? "highlighted" : ""}`}
      aria-label={`Отчёт импорта ${report.id}`}
    >
      <div className="report-heading">
        <div
          className={`report-icon ${report.status === "error" ? "error" : ""}`}
        >
          <FileSpreadsheet size={22} />
        </div>
        <div>
          <h3>{report.filename}</h3>
          <span className="muted small">
            {dateTime(report.created_at)} · {sourceLabel(report.source)} ·
            импорт № {report.id}
          </span>
        </div>
        <span
          className={`badge ${report.status === "error" ? "status-blocked" : "status-ready"}`}
        >
          {report.status === "error"
            ? "Импорт отменён"
            : report.duplicate_file
              ? "Уже импортирован"
              : "Импорт выполнен"}
        </span>
      </div>
      {report.status === "success" && (
        <div className="report-counts">
          {Object.entries(report.counts).map(([label, count]) => (
            <div key={label}>
              <strong>{count}</strong>
              <span>{label}</span>
            </div>
          ))}
          <div>
            <strong>{report.created.messages}</strong>
            <span>Новых сообщений</span>
          </div>
          <div>
            <strong>{report.skipped}</strong>
            <span>Пропущено существующих</span>
          </div>
        </div>
      )}
      {report.duplicate_file && (
        <Notice>
          Файл с этой контрольной суммой уже обработан. Данные и резервы не
          изменены.
        </Notice>
      )}
      {report.errors.map((e, i) => (
        <Notice key={i} kind="error">
          <strong>{e.cell}</strong> — {e.message}
        </Notice>
      ))}
      {report.warnings.map((w, i) => (
        <Notice key={i} kind="warning">
          <strong>{w.cell}</strong> — {w.message}
        </Notice>
      ))}
      <details className="technical-details">
        <summary>
          Происхождение и контрольная сумма <ChevronDown size={13} />
        </summary>
        <code>SHA-256: {report.sha256}</code>
      </details>
    </section>
  );
}

export function StockPage({ version }: { version: number }) {
  const [rows, setRows] = useState<Stock[] | null>(null),
    [error, setError] = useState("");
  const [q, setQ] = useState(""),
    [city, setCity] = useState(""),
    [model, setModel] = useState("");
  useEffect(() => {
    api<Stock[]>("/inventory")
      .then(setRows)
      .catch((e) => setError(errorText(e)));
  }, [version]);
  const visible = rows?.filter(
    (r) =>
      (!q || `${r.sku} ${r.name}`.toLowerCase().includes(q.toLowerCase())) &&
      (!city || r.warehouse === city) &&
      (!model || r.models.includes(model)),
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">СКЛАД</div>
          <h1>Детали и резервы</h1>
          <p>
            Доступность на двух складах с учётом всех подтверждённых резервов.
          </p>
        </div>
        <span className="tag">
          <Database size={14} />
          Единое хранилище
        </span>
      </div>
      <Notice>
        Свободно = на складе − исходный резерв − резервы пилота. Перевоз между
        Москвой и Тулой занимает один рабочий день.
      </Notice>
      <section className="panel">
        <div className="queue-filters">
          <label className="search-input">
            <Search size={17} />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Код или название детали"
              aria-label="Поиск деталей"
            />
          </label>
          <select
            value={city}
            onChange={(e) => setCity(e.target.value)}
            aria-label="Склад"
          >
            <option value="">Оба склада</option>
            <option>Москва</option>
            <option>Тула</option>
          </select>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            aria-label="Совместимая модель"
          >
            <option value="">Все модели</option>
            <option>C100</option>
            <option>C200</option>
            <option>C300</option>
          </select>
        </div>
        {error && <Notice kind="error">{error}</Notice>}
        {!rows && !error ? (
          <Spinner />
        ) : !visible?.length ? (
          <Empty
            title="Деталей нет"
            text={
              rows?.length
                ? "Измените фильтры поиска."
                : "Импортируйте справочник из Excel."
            }
          />
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>ДЕТАЛЬ</th>
                  <th>МОДЕЛИ</th>
                  <th>СКЛАД</th>
                  <th>НА СКЛАДЕ</th>
                  <th>ИСХОДНЫЙ РЕЗЕРВ</th>
                  <th>РЕЗЕРВ ПИЛОТА</th>
                  <th>СВОБОДНО</th>
                </tr>
              </thead>
              <tbody>
                {visible?.map((r) => (
                  <tr key={r.sku + r.warehouse}>
                    <td>
                      <strong>{r.sku}</strong>
                      <div className="row-meta">{r.name}</div>
                      <span className="cell-source">{r.source_ref}</span>
                    </td>
                    <td>{r.models.join(", ")}</td>
                    <td>{r.warehouse}</td>
                    <td>{r.on_hand}</td>
                    <td>{r.external_reserved}</td>
                    <td>{r.pilot_reserved}</td>
                    <td>
                      <span
                        className={`stock-number ${r.free ? "available" : "unavailable"}`}
                      >
                        {r.free}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

export function RulesPage() {
  const [rules, setRules] = useState<
      { code: string; topic: string; text: string; source_ref: string }[] | null
    >(null),
    [error, setError] = useState("");
  useEffect(() => {
    api<NonNullable<typeof rules>>("/rules")
      .then(setRules)
      .catch((e) => setError(errorText(e)));
  }, []);
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">БАЗА ПОДГОТОВКИ</div>
          <h1>Правила сервиса</h1>
          <p>Первоисточник — лист «Правила» предоставленного Excel.</p>
        </div>
        <span className="tag">
          <ShieldCheck size={15} />
          {rules?.length ?? "—"} правил
        </span>
      </div>
      {error && <Notice kind="error">{error}</Notice>}
      {rules === null && !error ? (
        <Spinner />
      ) : rules?.length === 0 ? (
        <div className="panel">
          <Empty
            title="Правила ещё не загружены"
            text="Импортируйте Excel, чтобы увидеть точные формулировки компании."
          />
        </div>
      ) : (
        <div className="rules-grid">
          {rules?.map((r) => (
            <section className="panel rule-card" key={r.code}>
              <span className="rule-code">{r.code}</span>
              <h2>{r.topic}</h2>
              <p>{r.text}</p>
              <span className="cell-source">{r.source_ref}</span>
            </section>
          ))}
        </div>
      )}
      <Notice kind="warning">
        <strong>Допустимые действия клиента:</strong> выключить и включить
        машину, проверить подачу воды, заново установить заварочный блок
        согласно руководству пользователя. Инструкции по разборке не передаются.
      </Notice>
    </>
  );
}

export const actionLabels: Record<string, string> = {
  message_created: "Создано обращение",
  ticket_updated: "Заявка изменена",
  part_added: "Добавлена деталь",
  reserved: "Подтверждён резерв",
  reservations_cancelled: "Снят резерв",
  transfer_agreed: "Согласован перевоз",
  tickets_merged: "Объединены обращения",
  merged_into: "Заявка объединена с основной",
  manager_route_recorded: "Зафиксирован маршрут менеджеру",
  reopened: "Заявка возвращена в работу",
  message_appended: "Добавлено уточнение",
  part_removed_and_released: "Деталь удалена, резерв освобождён",
  senior_approval_recorded: "Записано согласование старшего инженера",
  prepared: "Подготовлен выезд",
  excel_imported: "Выполнен импорт Excel",
  excel_import_failed: "Ошибка импорта Excel",
};

export function JournalPage({
  version,
  onSelect,
  ticketId,
}: {
  version: number;
  onSelect: (id: number) => void;
  ticketId?: number;
}) {
  const [rows, setRows] = useState<Audit[] | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    api<Audit[]>("/audit" + (ticketId ? `?ticket_id=${ticketId}` : ""))
      .then(setRows)
      .catch((e) => setError(errorText(e)));
  }, [version, ticketId]);
  return (
    <>
      {!ticketId && (
        <div className="page-heading">
          <div>
            <div className="eyebrow">ПРОЗРАЧНОСТЬ</div>
            <h1>Журнал действий</h1>
            <p>Последние 200 изменений с исполнителем и временем.</p>
          </div>
          <History size={25} className="muted" />
        </div>
      )}
      {error && <Notice kind="error">{error}</Notice>}
      <section className="panel journal">
        {rows === null && !error ? (
          <Spinner />
        ) : !rows?.length ? (
          <Empty
            title="Действий пока нет"
            text="Изменения заявок и резервов появятся здесь автоматически."
          />
        ) : (
          rows?.map((r) => (
            <article className="audit-item" key={r.id}>
              <span className="audit-dot" />
              <div>
                <div className="audit-heading">
                  <strong>{actionLabels[r.action] ?? r.action}</strong>
                  {r.ticket_id && (
                    <button
                      className="text-button"
                      onClick={() => onSelect(r.ticket_id!)}
                    >
                      КСР-{String(r.ticket_id).padStart(3, "0")}
                    </button>
                  )}
                  <time>{dateTime(r.created_at)}</time>
                </div>
                <span className="muted small">{r.actor}</span>
                <details className="technical-details">
                  <summary>Подробности записи</summary>
                  <pre>{JSON.stringify(r.details, null, 2)}</pre>
                </details>
              </div>
            </article>
          ))
        )}
      </section>
    </>
  );
}
