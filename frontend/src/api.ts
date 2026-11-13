export class ApiError extends Error {
  constructor(
    message: string,
    public code: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch("/api" + path, {
    ...options,
    headers: {
      ...(options.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...options.headers,
    },
    signal: options.signal ?? AbortSignal.timeout(25000),
  }).catch((error) => {
    throw new ApiError(
      error.name === "TimeoutError"
        ? "Сервер не ответил вовремя. Обновите данные перед повтором."
        : "Нет связи с сервером. Проверьте, что backend запущен.",
      "network",
    );
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new ApiError(
      body.error?.message ?? "Не удалось выполнить действие.",
      body.error?.code ?? "http",
      body.error?.details,
    );
  return body as T;
}
export const post = <T>(path: string, data: unknown) =>
  api<T>(path, { method: "POST", body: JSON.stringify(data) });
export const patch = <T>(path: string, data: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(data) });
export const dateTime = (value: string | null | undefined, short = false) =>
  value
    ? new Intl.DateTimeFormat("ru-RU", {
        day: "2-digit",
        month: short ? "2-digit" : "short",
        ...(short ? {} : { year: "numeric" }),
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Europe/Moscow",
      }).format(new Date(value))
    : "—";
export const dateOnly = (value: string | null | undefined) =>
  value
    ? new Intl.DateTimeFormat("ru-RU", {
        day: "2-digit",
        month: "long",
        year: "numeric",
        timeZone: "Europe/Moscow",
      }).format(new Date(value + "T12:00:00"))
    : "—";
export const sourceLabel = (source: string) =>
  ({
    case: "Данные кейса",
    upload: "Excel",
    demo: "Демонстрация",
    manual: "Ручной ввод",
  })[source] ?? source;
export const statusLabel = (status: string) =>
  ({
    blocked: "Нужна подготовка",
    review: "Можно подготовить",
    ready: "Карточка готова к передаче",
    manager: "Менеджеру",
  })[status] ?? status;
