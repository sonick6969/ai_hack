import { test, expect } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";

const output = path.resolve(import.meta.dirname, "../../artifacts/redesign");
fs.mkdirSync(output, { recursive:true });

test("Неизвестный ответ остаётся препятствием; черновик переживает переходы", async ({page}) => {
  const result = await page.request.post("/api/messages", {data:{sender:"Кафе «Кедр», проверка уточнений",text:"На машине 205 вода появляется справа после приготовления.",received_at:"2026-11-16T13:00:00+03:00"}});
  const ticket = (await result.json()).ticket;
  await page.goto(`/?ticket=${ticket.id}`);
  await page.getByRole("tab",{name:"Уточнения",exact:true}).click();
  const location = page.getByLabel("Где появляется вода?",{exact:true});
  await location.fill("Причину не знаю, вода появляется справа под корпусом");
  await page.getByRole("tab",{name:"Детали",exact:true}).click();
  await page.getByRole("tab",{name:"Уточнения",exact:true}).click();
  await expect(location).toHaveValue("Причину не знаю, вода появляется справа под корпусом");
  await page.getByRole("button",{name:"Детали и резервы",exact:true}).click();
  await expect(page.getByRole("dialog",{name:"Есть несохранённые изменения"})).toBeVisible();
  await page.getByRole("button",{name:"Остаться",exact:true}).click();
  await page.getByRole("button",{name:"Ответ пока неизвестен",exact:true}).first().click();
  const firstSave = page.waitForResponse(r => r.url().endsWith(`/api/tickets/${ticket.id}`) && r.request().method() === "PATCH");
  await page.getByRole("button",{name:"Сохранить ответы и симптом",exact:true}).click();
  await firstSave;
  await expect(page.getByText("Неизвестно · вопрос остаётся открытым",{exact:true})).toBeVisible();
  const current = await (await page.request.get(`/api/tickets/${ticket.id}`)).json();
  expect(current.readiness.questions[0].status).toBe("unknown");
  expect(current.readiness.can_prepare).toBe(false);
  expect(current.data.answers.leak_location).toContain("справа");
  await page.screenshot({path:path.join(output,"unknown-answer.png"),fullPage:true});
  await location.fill("Причину не знаю, вода появляется справа под корпусом");
  await page.getByRole("button",{name:"Использовать записанный ответ",exact:true}).click();
  const secondSave = page.waitForResponse(r => r.url().endsWith(`/api/tickets/${ticket.id}`) && r.request().method() === "PATCH");
  await page.getByRole("button",{name:"Сохранить ответы и симптом",exact:true}).click();
  await secondSave;
  const final = await (await page.request.get(`/api/tickets/${ticket.id}`)).json();
  expect(final.readiness.questions[0].resolved).toBe(true);
});

test("Все рабочие экраны при 1440, 1280 и 390 px", async ({page}) => {
  const errors: string[]=[];
  page.on("pageerror",error=>errors.push(error.message));
  for (const width of [1440,1280,390]) {
    await page.setViewportSize({width,height:width===390?844:1000});
    for (const [section,heading] of [["queue","Подготовка выездов"],["stock","Детали и резервы"],["imports","Импорт данных"],["rules","Правила сервиса"],["audit","Журнал действий"]]) {
      await page.goto(section==="queue"?"/":`/?section=${section}`);
      await expect(page.getByRole("heading",{name:heading,exact:true})).toBeVisible();
      await expect(page.locator(".loading")).toHaveCount(0);
      await page.evaluate(()=>document.fonts.ready);
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
      await page.screenshot({path:path.join(output,`${section}-${width}.png`),fullPage:false});
    }
    await page.goto("/?ticket=6");
    await expect(page.getByRole("heading",{name:"Кафе «Кедр»",exact:true})).toBeVisible();
    await page.getByRole("tab",{name:"Уточнения",exact:true}).click();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:path.join(output,`ticket-${width}.png`),fullPage:false});
  }
  expect(errors).toEqual([]);
});

test("Большие показатели, длинное имя, пустая очередь и клавиатура", async ({page}) => {
  await page.setViewportSize({width:390,height:844});
  await page.route("**/api/summary",async route => {
    const response=await route.fetch();
    const summary=await response.json();
    await route.fulfill({json:{...summary,tickets:1234567,messages:9999999}});
  });
  await page.goto("/");
  await expect(page.locator(".stat-value").first()).toHaveText("1234567");
  expect(await page.locator(".stat-value").first().evaluate(node=>node.scrollWidth<=node.clientWidth)).toBe(true);
  await page.getByLabel("Поиск обращений",{exact:true}).fill("__нет_такого_клиента__");
  await expect(page.getByText("Обращений не найдено",{exact:true})).toBeVisible();
  await page.screenshot({path:path.join(output,"empty-search-390.png"),fullPage:false});
  await page.unroute("**/api/summary");
  await page.goto("/");
  await page.getByRole("button",{name:"Новое обращение",exact:true}).click();
  const dialog=page.getByRole("dialog");
  await dialog.getByLabel("Кто обращается",{exact:true}).fill('Кафе «Очень длинное русское название организации для проверки переноса и доступности на небольшом экране», администратор смены');
  await dialog.getByLabel("Сообщение клиента",{exact:true}).fill("Кофемашина не работает, точный номер и симптом нужно уточнить.");
  await dialog.getByRole("button",{name:"Сохранить и разобрать",exact:true}).click();
  await expect(page.getByRole("heading",{name:/Кафе «Очень длинное/})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:path.join(output,"long-client-390.png"),fullPage:false});
  await page.getByRole("button",{name:"Добавить сообщение",exact:true}).click();
  await page.getByRole("button",{name:"Закрыть",exact:true}).focus();
  await page.keyboard.press("Shift+Tab");
  await expect(page.getByRole("button",{name:"Сохранить уточнение",exact:true})).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});
