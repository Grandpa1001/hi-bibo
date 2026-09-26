/**
 * Jedna warstwa nad Telegram.WebApp.
 *
 * Ekrany deklarują przyciski natywne przez sygnały (`glowny`, `drugi`, `wstecz`).
 * W Telegramie sygnały są synchronizowane z MainButton / SecondaryButton / BackButton,
 * w trybie mock rysuje je komponent `PasekMock` — ekrany nie wiedzą, gdzie działają.
 */
import { effect, signal } from "@preact/signals";
import type { WebApp } from "telegram-web-app";

export type Przycisk = { tekst: string; onClick: () => void; postep?: boolean; wylaczony?: boolean };

const W: WebApp | undefined = (window as any).Telegram?.WebApp;
const params = new URLSearchParams(location.search);

/** Prawdziwy Telegram = jest podpisane initData. */
export const wTelegramie = !!W?.initData;
/** Tryb mock: dev serwer albo ?mock=1 — sztuczne API i przyciski w HTML. */
export const mock = !wTelegramie && (import.meta.env.DEV || params.has("mock"));

export const initData = W?.initData ?? "";
export const startParam = W?.initDataUnsafe?.start_param ?? "";

export const glowny = signal<Przycisk | null>(null);
export const drugi = signal<Przycisk | null>(null);
export const wstecz = signal<(() => void) | null>(null);
export const zamknieta = signal(false); // mock: symulacja close()

const KOLOR_GLOWNY = "#009688";

function wersja(v: string) {
  try { return !!W?.isVersionAtLeast(v); } catch { return false; }
}

export function start() {
  if (!wTelegramie || !W) return;
  W.ready();
  W.expand();
  try {
    W.setHeaderColor("#FFFFFF");
    W.setBackgroundColor("#F2F2F2");
    if (wersja("7.10")) W.setBottomBarColor("#FFFFFF");
  } catch { /* starsze klienty */ }

  // MainButton — jeden handler, podmieniany przez sygnał.
  let mbKlik: (() => void) | null = null;
  W.MainButton.onClick(() => mbKlik?.());
  effect(() => {
    const p = glowny.value;
    const mb = W.MainButton;
    if (!p) { mb.hideProgress(); mb.hide(); mbKlik = null; return; }
    mbKlik = p.onClick;
    mb.setParams({ text: p.tekst, color: KOLOR_GLOWNY, text_color: "#FFFFFF", is_active: !p.wylaczony, is_visible: true });
    p.postep ? mb.showProgress(false) : mb.hideProgress();
  });

  if (wersja("7.10")) {
    let sbKlik: (() => void) | null = null;
    W.SecondaryButton.onClick(() => sbKlik?.());
    effect(() => {
      const p = drugi.value;
      const sb = W.SecondaryButton;
      if (!p) { sb.hide(); sbKlik = null; return; }
      sbKlik = p.onClick;
      sb.setParams({ text: p.tekst, is_active: !p.wylaczony, is_visible: true, position: "bottom" } as any);
    });
  }

  let bbKlik: (() => void) | null = null;
  W.BackButton.onClick(() => bbKlik?.());
  effect(() => {
    bbKlik = wstecz.value;
    bbKlik ? W.BackButton.show() : W.BackButton.hide();
  });
}

/** Czy SecondaryButton jest natywny (inaczej ekran rysuje go sam). */
export const drugiNatywny = wTelegramie && wersja("7.10");

export function haptyka(rodzaj: "lekko" | "sukces" | "ostrzezenie") {
  try {
    const h = W?.HapticFeedback;
    if (!h || !wTelegramie) return;
    if (rodzaj === "lekko") h.impactOccurred("light");
    else h.notificationOccurred(rodzaj === "sukces" ? "success" : "warning");
  } catch { /* brak haptyki */ }
}

export function okienko(tytul: string, tresc: string) {
  if (wTelegramie && W && wersja("6.2")) {
    W.showPopup({ title: tytul, message: tresc, buttons: [{ type: "ok" }] });
  } else {
    popupMock.value = { tytul, tresc };
  }
}
export const popupMock = signal<{ tytul: string; tresc: string } | null>(null);

export function zamknij() {
  if (wTelegramie && W) W.close();
  else zamknieta.value = true;
}

export function potwierdzanieZamkniecia(wlacz: boolean) {
  if (!wTelegramie || !W || !wersja("6.2")) return;
  wlacz ? W.enableClosingConfirmation() : W.disableClosingConfirmation();
}

/** Szkic tekstu: CloudStorage jest przypisany do bota, nie do adresu (tunel zmienia adres). */
export const szkic = {
  async czytaj(klucz: string): Promise<string> {
    if (wTelegramie && W && wersja("6.9")) {
      return new Promise((ok) => W.CloudStorage.getItem(klucz, (_e: unknown, v?: string | null) => ok(v ?? "")));
    }
    try { return sessionStorage.getItem(klucz) ?? ""; } catch { return ""; }
  },
  zapisz(klucz: string, wartosc: string) {
    if (wTelegramie && W && wersja("6.9")) {
      wartosc ? W.CloudStorage.setItem(klucz, wartosc.slice(0, 4000)) : W.CloudStorage.removeItem(klucz);
      return;
    }
    try { wartosc ? sessionStorage.setItem(klucz, wartosc) : sessionStorage.removeItem(klucz); } catch { /* */ }
  },
};
