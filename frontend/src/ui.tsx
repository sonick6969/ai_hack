import { useEffect, useRef } from "react";
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
  const dialog = useRef<HTMLElement>(null);
  const closeRef = useRef(close);
  closeRef.current = close;
  useEffect(() => {
    const priorFocus = document.activeElement as HTMLElement | null;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeRef.current();
      if (e.key === "Tab") {
        const controls = Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]') ?? []).filter(node => node.getClientRects().length);
        const first = controls[0], last = controls[controls.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
        if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    };
    if (!dialog.current?.contains(document.activeElement)) dialog.current?.querySelector<HTMLElement>("input,textarea,button")?.focus();
    document.addEventListener("keydown", handler);
    const prior = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prior;
      document.removeEventListener("keydown", handler);
      priorFocus?.focus();
    };
  }, []);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <section
        ref={dialog}
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

export function QueueArtwork() {
  return <div className="queue-artwork" aria-hidden="true">
    <div className="art-sky" />
    <div className="art-photo"><img src="/assets/espresso-machine.jpg" alt="" width="683" height="1024" /><span>СЕРВИСНЫЙ ЦЕХ</span></div>
    <svg className="art-scribble" viewBox="0 0 230 140" fill="none"><path d="M20 35C14 9 74 4 100 17c31 17-4 49-47 40C6 48 4 21 43 11M115 90c35-30 53-34 91-32m-19-14 19 14-22 10" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"/><path d="m124 12 9 18 20-5-10 18 13 15-22-3-10 19-5-22-22-1 19-13Z" stroke="currentColor" strokeWidth="2" /></svg>
    <span className="art-sticker">сначала детали<br/>обращения</span>
    <span className="art-tape" />
  </div>;
}
