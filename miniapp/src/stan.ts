/** Stan Mini App: trasa (hash) i bieżąca sprawa. Logika przebiegu sprawy jest tu, ekrany tylko ją wywołują. */
import { signal } from "@preact/signals";
import { api, BladApi, type Wyrok, type Zeznanie } from "./api";
import { haptyka, potwierdzanieZamkniecia, startParam, szkic, zamknij } from "./tg";

// --- trasy -------------------------------------------------------------------

export type Trasa =
  | { ekran: "start" }
  | { ekran: "sprawa" }
  | { ekran: "kartoteka" }
  | { ekran: "kontrola"; id: string };

function czytajTrase(): Trasa {
  const h = location.hash.replace(/^#\/?/, "");
  const [a, b] = h.split("/");
  if (a === "sprawa") return { ekran: "sprawa" };
  if (a === "kartoteka") return { ekran: "kartoteka" };
  if (a === "kontrola" && b) return { ekran: "kontrola", id: decodeURIComponent(b) };
  // Link t.me/<bot>/<app>?startapp=kontrola_<id> (poza MVP, ale nic nie kosztuje)
  const m = /^kontrola_(.+)$/.exec(startParam);
  if (!h && m) return { ekran: "kontrola", id: m[1] };
  return { ekran: "start" };
}

export const trasa = signal<Trasa>(czytajTrase());
addEventListener("hashchange", () => { trasa.value = czytajTrase(); });

export function idz(t: "start" | "sprawa" | "kartoteka") {
  location.hash = t === "start" ? "#/" : `#/${t}`;
}

// --- sprawa ------------------------------------------------------------------

export type Krok = "zeznanie" | "analiza" | "przesluchanie" | "obrady" | "werdykt";

export type Sprawa = {
  id: string;
  numer: number;
  krok: Krok;
  wymowka: string;
  riposta: string;
  zeznanie?: Zeznanie;
  wyrok?: Wyrok;
  podpowiedzUzyta: boolean;
  kontrola: boolean;
  zamykanie: boolean;
};

export const sprawa = signal<Sprawa | null>(null);
export const blad = signal<{ komunikat: string; ponow: () => void } | null>(null);

const SZKIC_W = "bt_szkic_wymowka";
const SZKIC_R = "bt_szkic_riposta";

function zmien(z: Partial<Sprawa>) {
  if (sprawa.value) sprawa.value = { ...sprawa.value, ...z };
}

async function probuj(akcja: () => Promise<void>, wroc: Partial<Sprawa>) {
  blad.value = null;
  try {
    await akcja();
  } catch (e) {
    zmien(wroc);
    const komunikat = e instanceof BladApi ? e.message : "Coś poszło nie tak. Spróbuj jeszcze raz.";
    blad.value = { komunikat, ponow: () => probuj(akcja, wroc) };
  }
}

let tworze = false;

export async function nowaSprawa() {
  if (tworze) return;
  tworze = true;
  blad.value = null;
  sprawa.value = null;
  idz("sprawa");
  try {
    await probuj(async () => {
      const s = await api.nowaSprawa();
      sprawa.value = { id: s.id, numer: s.numer, krok: "zeznanie", wymowka: await szkic.czytaj(SZKIC_W),
                       riposta: "", podpowiedzUzyta: false, kontrola: false, zamykanie: false };
    }, {});
  } finally {
    tworze = false;
  }
}

/** Wejście na #/sprawa bez otwartej sprawy (np. przeładowanie) — otwieramy nową; szkic wymówki wraca. */
export function zapewnijSprawe() {
  if (!sprawa.value && !tworze && !blad.value) nowaSprawa();
}

export function wpiszWymowke(t: string) {
  zmien({ wymowka: t });
  szkic.zapisz(SZKIC_W, t);
  potwierdzanieZamkniecia(!!t.trim());
}

export function wpiszRiposte(t: string) {
  zmien({ riposta: t });
  szkic.zapisz(SZKIC_R, t);
  potwierdzanieZamkniecia(!!t.trim());
}

export async function zlozZeznanie() {
  const s = sprawa.value;
  if (!s || !s.wymowka.trim()) return;
  haptyka("lekko");
  zmien({ krok: "analiza" });
  await probuj(async () => {
    const z = await api.zeznanie(s.id, s.wymowka.trim());
    szkic.zapisz(SZKIC_W, "");
    zmien({ zeznanie: z, krok: "przesluchanie", riposta: await szkic.czytaj(SZKIC_R) });
  }, { krok: "zeznanie" });
}

export async function odpowiedz(uniewinnienie = false) {
  const s = sprawa.value;
  if (!s || (!uniewinnienie && !s.riposta.trim())) return;
  haptyka("lekko");
  zmien({ krok: "obrady" });
  await probuj(async () => {
    const w = await api.riposta(s.id, uniewinnienie ? { uniewinnienie: true } : { riposta: s.riposta.trim() });
    szkic.zapisz(SZKIC_R, "");
    potwierdzanieZamkniecia(false);
    zmien({ wyrok: w, krok: "werdykt" });
    haptyka(w.werdykt === "czesciowo" ? "ostrzezenie" : "sukces");
  }, { krok: "przesluchanie" });
}

export function uzyjPodpowiedzi() {
  zmien({ podpowiedzUzyta: true });
}

export function przelaczKontrole() {
  zmien({ kontrola: !sprawa.value?.kontrola });
}

export async function zamknijAkta(kontrolaMin: number) {
  const s = sprawa.value;
  if (!s || s.zamykanie) return;
  zmien({ zamykanie: true });
  await probuj(async () => {
    await api.zamknij(s.id, s.kontrola ? kontrolaMin : null);
    sprawa.value = null;
    zamknij();
  }, { zamykanie: false });
}

export function porzucSprawe() {
  sprawa.value = null;
  blad.value = null;
  potwierdzanieZamkniecia(false);
  idz("start");
}
