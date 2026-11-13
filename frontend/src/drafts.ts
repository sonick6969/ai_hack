import { useEffect, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

const prefix = "coffee:draft:v1:";
const event = "coffee-drafts-changed";
const keyFor = (id: number, section: string, field = "") => `${prefix}${id}:${section}:${field}`;
const keys = () => Object.keys(sessionStorage).filter((key) => key.startsWith(prefix));

export function hasDrafts(id?: number) {
  return keys().some((key) => id === undefined || key.startsWith(`${prefix}${id}:`));
}

export function clearDrafts(id: number, section: string) {
  keys().filter((key) => key.startsWith(keyFor(id, section))).forEach((key) => sessionStorage.removeItem(key));
  window.dispatchEvent(new Event(event));
}

export function useDraftState<T>(id: number, section: string, field: string, initial: T): [T, Dispatch<SetStateAction<T>>] {
  const key = keyFor(id, section, field);
  const [value, setValue] = useState<T>(() => {
    try { return JSON.parse(sessionStorage.getItem(key) ?? "null")?.value ?? initial; }
    catch { return initial; }
  });
  const initialJSON = JSON.stringify(initial);
  useEffect(() => {
    if (JSON.stringify(value) === initialJSON) sessionStorage.removeItem(key);
    else sessionStorage.setItem(key, JSON.stringify({ value }));
    window.dispatchEvent(new Event(event));
  }, [key, value, initialJSON]);
  return [value, setValue];
}

export function useDirtyDrafts(id?: number) {
  const [dirty, setDirty] = useState(() => hasDrafts(id));
  useEffect(() => {
    const update = () => setDirty(hasDrafts(id));
    const unload = (e: BeforeUnloadEvent) => { if (hasDrafts(id)) { e.preventDefault(); e.returnValue = ""; } };
    update();
    window.addEventListener(event, update);
    window.addEventListener("beforeunload", unload);
    return () => { window.removeEventListener(event, update); window.removeEventListener("beforeunload", unload); };
  }, [id]);
  return dirty;
}
