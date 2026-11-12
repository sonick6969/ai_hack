import { useEffect } from "react";
import type { ReactNode } from "react";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  Inbox,
  Loader2,
  X,
} from "lucide-react";
import { statusLabel } from "./api";

export function Spinner({ text = "Загружаем данные…" }: { text?: string }) {
  return (
    <div className="loading" role="status">
      <Loader2 size={22} className="spin" />
      <span>{text}</span>
    </div>
  );
}
export function Status({ value }: { value: string }) {
  return (
    <span className={`badge status-${value}`}>
      <span className="status-dot" />
      {statusLabel(value)}
    </span>
  );
}
export function Notice({
  children,
  kind = "info",
}: {
  children: ReactNode;
  kind?: string;
}) {
  return (
    <div
      className={`notice notice-${kind}`}
      role={kind === "error" ? "alert" : "note"}
    >
      {kind === "success" ? (
        <CheckCircle2 size={18} />
      ) : (
        <AlertCircle size={18} />
      )}
      <div>{children}</div>
    </div>
  );
}
export function Empty({
  title,
  text,
  children,
}: {
  title: string;
  text: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Inbox size={29} strokeWidth={1.5} />
      </div>
      <h3>{title}</h3>
      <p>{text}</p>
      {children}
    </div>
  );
}
export function Modal({
  title,
  children,
  close,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
}) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", handler);
    const prior = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prior;
      document.removeEventListener("keydown", handler);
    };
  }, [close]);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="modal-heading">
          <h2>{title}</h2>
          <button
            className="icon-button"
            type="button"
            onClick={close}
            aria-label="Закрыть"
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}
export function Tick({ passed }: { passed: boolean }) {
  return passed ? (
    <Check size={15} className="text-green" />
  ) : (
    <span className="open-circle" />
  );
}
export const errorText = (error: unknown) =>
  error instanceof Error ? error.message : "Не удалось выполнить действие.";

export function SectionTitle({
  number,
  title,
  children,
}: {
  number?: string;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="section-title">
      <div>
        {number && <span className="section-number">{number}</span>}
        <h2>{title}</h2>
      </div>
      {children}
    </div>
  );
}
