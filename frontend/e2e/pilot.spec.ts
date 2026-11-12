import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";

const root = path.resolve(import.meta.dirname, "../..");
const screenshots = path.join(root, "artifacts");
let datasetSource = "case";
test.describe.configure({ mode: "serial" });

test("Excel: загрузка настоящего файла, отчёт и повтор без дублей", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Импорт данных", exact: true })
    .click();
  await page
    .getByLabel("Выбрать Excel", { exact: true })
    .setInputFiles(path.join(root, "Данные_к_кейсу_06 (1).xlsx"));
  await expect(
    page.getByRole("heading", { name: "Данные_к_кейсу_06 (1).xlsx" }).first(),
  ).toBeVisible();
  await expect(
    page.getByText(/^(Импорт выполнен|Уже импортирован)$/).first(),
  ).toBeVisible();
  const imports = await (await page.request.get("/api/imports")).json();
  datasetSource = imports.find(
    (r: { filename: string }) => r.filename === "Данные_к_кейсу_06 (1).xlsx",
  ).source;
  await expect(
    page.getByText("Оборудование!A15:H15", { exact: true }).first(),
  ).toBeVisible();
  const before = await (await page.request.get("/api/summary")).json();
  expect(before.messages).toBeGreaterThanOrEqual(23);
  await page
    .getByRole("button", { name: "Импортировать файл кейса", exact: true })
    .click();
  await expect(
    page.getByText("Уже импортирован", { exact: true }).first(),
  ).toBeVisible();
  const after = await (await page.request.get("/api/summary")).json();
  expect(after.messages).toBe(before.messages);
  await page.screenshot({
    path: path.join(screenshots, "import-report.png"),
    fullPage: true,
  });
});

test("Очередь: поиск, фильтры, пустой результат и точная машина", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Поиск обращений", { exact: true }).fill("211");
  await expect(page.locator("tbody tr")).toHaveCount(2);
  await expect(page.locator("tbody tr").first()).toContainText("Кафе «Парк»");
  await page.getByLabel("Город", { exact: true }).selectOption("Тула");
  await expect(
    page.getByText("Обращений не найдено", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Сбросить фильтры", exact: true })
    .click();
  await page
    .getByLabel("Источник данных", { exact: true })
    .selectOption(datasetSource);
  await expect(page.locator("tbody tr")).toHaveCount(23);
  await page.screenshot({
    path: path.join(screenshots, "queue.png"),
    fullPage: true,
  });
});

test("Незнакомый текст: машина, ответы, реальный резерв, готовность, PDF и изменение", async ({
  page,
}) => {
  const jsErrors: string[] = [];
  page.on("pageerror", (error) => jsErrors.push(error.message));
  const started = Date.now();
  await page.goto("/");
  await page
    .getByRole("button", { name: "Новое обращение", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByLabel("Кто обращается", { exact: true })
    .fill("Кафе «Угол», новая смена");
  const unfamiliar = `На С100, s/n 119, со вчера кофе наливается медленно. Работ не было. Проверка через интерфейс ${Date.now()}.`;
  await dialog
    .getByLabel("Сообщение клиента", { exact: true })
    .fill(unfamiliar);
  await dialog.getByLabel(/Дата и время/).fill("2026-11-16T12:30");
  await dialog
    .getByRole("button", { name: "Сохранить и разобрать", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Кафе «Угол»", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Подготовить выезд", exact: true }),
  ).toBeDisabled();
  const id = Number(new URL(page.url()).searchParams.get("ticket"));
  await page
    .getByRole("button", { name: "Подтвердить машину и адрес", exact: true })
    .click();
  await expect(page.getByText("Подтверждена", { exact: true })).toBeVisible();
  const separate = page.getByLabel(
    "Если это отдельная проблема — объясните почему",
    { exact: true },
  );
  if (await separate.count()) {
    await separate.fill(
      "Отдельная проверка интерфейса, диспетчер сверил обращения.",
    );
    await page
      .getByRole("button", {
        name: "Сохранить как отдельную проблему",
        exact: true,
      })
      .click();
    await expect(separate).toHaveValue(
      "Отдельная проверка интерфейса, диспетчер сверил обращения.",
    );
  }
  await page.getByRole("tab", { name: "Уточнения" }).click();
  await page
    .getByLabel("Наблюдаемый симптом", { exact: true })
    .fill(
      "Со вчера кофе идёт медленно на C100 №119. Работ перед появлением симптома не было.",
    );
  await page
    .getByLabel("Описание симптома проверено диспетчером", { exact: true })
    .check();
  await page
    .getByLabel("С какого момента поток стал слабым?", { exact: true })
    .fill("Со вчерашнего вечера");
  await page
    .getByLabel("Какие работы были перед этим?", { exact: true })
    .fill("Работ не было");
  await page
    .getByRole("button", { name: "Сохранить ответы и симптом", exact: true })
    .click();
  await page.getByRole("tab", { name: "Выезд и детали" }).click();
  await page
    .getByLabel("Что должен сделать инженер?", { exact: true })
    .fill(
      "Проверить подачу воды и поток. Фильтр F010 взять для подготовки; необходимость замены определить на осмотре.",
    );
  await page
    .getByLabel("Оставшиеся неопределённости", { exact: true })
    .fill("Причина медленного потока неизвестна. Нужна проверка на месте.");
  await page
    .getByLabel(
      "Цель и состав выезда согласованы; ограничения диагностики понятны",
      { exact: true },
    )
    .check();
  await page
    .getByRole("button", { name: "Сохранить план выезда", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Подготовить выезд", exact: true }),
  ).toBeEnabled();
  await page.getByLabel("Деталь", { exact: true }).selectOption("F010");
  await page
    .getByLabel("Склад получения", { exact: true })
    .selectOption("Тула");
  await page
    .getByRole("button", { name: "Добавить в план", exact: true })
    .click();
  await expect(
    page.getByText("Не зарезервировано", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Подготовить выезд", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Подтвердить резерв", exact: true })
    .click();
  await expect(page.getByText("В резерве", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Подтвердить резерв", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Подготовить выезд", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Можно выезжать", exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Карточка инженера" }).click();
  await expect(
    page.getByRole("heading", {
      name: "Задание сервисному инженеру",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.locator(".engineer-paper")).toContainText("119");
  await expect(page.locator(".engineer-paper")).toContainText(
    "Тула, ул. Советская, 40",
  );
  await expect(page.locator(".engineer-paper")).toContainText("F010");
  const toastClose = page.getByRole("button", {
    name: "Закрыть уведомление",
    exact: true,
  });
  if (await toastClose.count()) await toastClose.click();
  await page.screenshot({
    path: path.join(screenshots, "prepared-card.png"),
    fullPage: true,
  });
  const popupPromise = page.waitForEvent("popup");
  await page.getByRole("link", { name: "Печать / PDF", exact: true }).click();
  const popup = await popupPromise;
  await popup.waitForLoadState();
  await expect(popup.locator("body")).toContainText("ГОТОВО К ВЫЕЗДУ");
  await popup.emulateMedia({ media: "print" });
  await popup.pdf({
    path: path.join(screenshots, "engineer-card.pdf"),
    format: "A4",
    printBackground: true,
  });
  await popup.close();
  const preparationMs = Date.now() - started;
  await page
    .getByRole("button", { name: "Добавить сообщение", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByLabel("Сообщение клиента", { exact: true })
    .fill("Уточнение по потоку: с вечера стал ещё медленнее, работ не было.");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Сохранить уточнение", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Подготовим без пробелов", exact: true }),
  ).toBeVisible();
  const state = await (await page.request.get(`/api/tickets/${id}`)).json();
  expect(state.readiness.ready).toBe(false);
  expect(state.prepared_revision).toBeNull();
  expect(jsErrors).toEqual([]);
  // Release the test's own stock; keep the record and its audit as reproducible evidence.
  await page.request.post(`/api/tickets/${id}/release`, {
    data: { revision: state.revision },
  });
  fs.writeFileSync(
    path.join(screenshots, "workflow-measurement.json"),
    JSON.stringify(
      {
        ticket_id: id,
        preparation_ms: preparationMs,
        automated: true,
        human_time_measured: false,
        unfamiliar_text: unfamiliar,
        javascript_errors: jsErrors,
      },
      null,
      2,
    ),
  );
});

test("Нулевой остаток: настоящий отказ резерва виден диспетчеру", async ({
  page,
}) => {
  await createThroughForm(
    page,
    "Кафе «Кедр», проверка склада",
    "На машине 205 вода появляется справа после приготовления. Проверка нулевого остатка.",
  );
  await page.getByRole("tab", { name: "Выезд и детали" }).click();
  await page.getByLabel("Деталь", { exact: true }).selectOption("G200");
  await page
    .getByRole("button", { name: "Добавить в план", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Подтвердить резерв", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("свободно 0");
  await expect(
    page.getByText("Не зарезервировано", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Подготовить выезд", exact: true }),
  ).toBeDisabled();
});

test("Неизвестная машина остаётся вне реестра и передаётся менеджеру", async ({
  page,
}) => {
  await createThroughForm(
    page,
    "Гостиница «Север», проверка",
    "В баре вторая машина, номер 270, течёт из-под поддона постоянно.",
  );
  await expect(
    page.getByText("Подходящей машины нет среди кандидатов.", { exact: false }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Машины нет в реестре — маршрут менеджеру" })
    .click();
  await page
    .getByLabel("Сведения для передачи", { exact: true })
    .fill(
      "Номер 270, модель пока неизвестна. Диспетчер запросит шильдик и передаст менеджеру.",
    );
  await page
    .getByRole("button", {
      name: "Зафиксировать маршрут менеджеру",
      exact: true,
    })
    .click();
  await expect(
    page.getByText("Зафиксирован маршрут менеджеру.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Подготовить выезд", exact: true }),
  ).toBeDisabled();
});

test("Уточнение по той же течи объединяется с сохранением исходных сообщений", async ({
  page,
}) => {
  await createThroughForm(
    page,
    "Кафе «Кедр», проверка объединения",
    "Уточнение по течи: номер 205, вода справа после приготовления.",
  );
  await expect(
    page.getByRole("heading", { name: "Повторы и уточнения", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Объединить", exact: true })
    .first()
    .click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByLabel("Почему это одна проблема?", { exact: true })
    .fill("Подтверждено: тот же клиент, машина 205, та же течь.");
  await dialog
    .getByRole("button", { name: "Объединить сообщения", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const id = Number(new URL(page.url()).searchParams.get("ticket"));
  const state = await (await page.request.get(`/api/tickets/${id}`)).json();
  expect(state.messages.length).toBeGreaterThan(1);
  expect(state.readiness.ready).toBe(false);
});

test("Узкий экран: навигация, поля и карточка не выходят за ширину", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Новое обращение", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Закрыть", exact: true }).click();
  const response = await page.request.get(
    `/api/tickets?source=${datasetSource}&q=119`,
  );
  const rows = await response.json();
  await page.goto(`/?ticket=${rows[0].id}`);
  await expect(
    page.getByRole("heading", { name: "Кафе «Угол»", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: path.join(screenshots, "mobile-detail.png"),
    fullPage: true,
  });
});

test("Ошибка сети: явная ошибка и восстановление очереди", async ({ page }) => {
  await page.route("**/api/tickets?*", (route) => route.abort("failed"));
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("Нет связи с сервером");
  await page.unroute("**/api/tickets?*");
  await page
    .getByRole("button", { name: "Обновить очередь", exact: true })
    .click();
  await expect(page.locator("tbody tr").first()).toBeVisible();
});

async function createThroughForm(page: Page, sender: string, text: string) {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Новое обращение", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByLabel("Кто обращается", { exact: true })
    .fill(sender);
  await page
    .getByRole("dialog")
    .getByLabel("Сообщение клиента", { exact: true })
    .fill(text);
  await page
    .getByRole("dialog")
    .getByLabel(/Дата и время/)
    .fill("2026-11-16T12:45");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Сохранить и разобрать", exact: true })
    .click();
  await expect(
    page.getByRole("tab", { name: "Обращение и машина", exact: true }),
  ).toBeVisible();
}
