/** Klient API wtyczki bibo-tryby (kontrakt: docs/BIBOTEKTYW-DEV.md §8) + sztuczne API do trybu mock. */
import { initData, sztuczneApi } from "./tg";

export type Werdykt = "obalona" | "czesciowo" | "uniewinniona";
export type Podejrzany = { nazwa: string; emoji: string; nowy: boolean; zatrzymanie: number; ostatnio: string | null };

export type Hub = {
  tryby: { id: string; nazwa: string; opis: string; aktywny: boolean }[];
  statystyki: { zamkniete: number; obalone: number; najczestszy: { nazwa: string; emoji: string } | null };
};
export type Zeznanie = { podejrzany: Podejrzany; pytanie: string; podpowiedz: string; zrodlo: "model" | "bank" };
export type Wyrok = { werdykt: Werdykt; podsumowanie: string; krok: string; zrodlo: "model" | "bank" };
export type SprawaInfo = { id: string; numer: number; podejrzany: { nazwa: string; emoji: string }; krok: string; werdykt: Werdykt; kontrola: string | null };
export type Kartoteka = {
  podejrzani: { nazwa: string; emoji: string; zatrzymania: number; obalone: number; ruszylo: number; ostatnio: string }[];
  sprawy: { numer: number; podejrzany: string; werdykt: Werdykt; ruszylo: boolean | null; data: string }[];
};

export class BladApi extends Error {
  constructor(public kod: string, public status: number, komunikat: string) { super(komunikat); }
}

export interface Api {
  hub(): Promise<Hub>;
  nowaSprawa(): Promise<{ id: string; numer: number }>;
  zeznanie(id: string, wymowka: string): Promise<Zeznanie>;
  riposta(id: string, dane: { riposta: string } | { uniewinnienie: true }): Promise<Wyrok>;
  zamknij(id: string, kontrolaMin: number | null): Promise<{ ok: true; kontrola: string | null }>;
  sprawa(id: string): Promise<SprawaInfo>;
  kontrola(id: string, ruszylo: boolean): Promise<{ ok: true }>;
  kartoteka(): Promise<Kartoteka>;
}

const KOMUNIKATY: Record<string, string> = {
  podpis: "Sesja wygasła. Otwórz Bibotektywa jeszcze raz z czatu.",
  uzytkownik: "Ta Mini App należy do innego Bibo.",
  sprawa: "Tej sprawy już nie ma w aktach.",
  limit: "Dużo śledztw jak na godzinę. Odpocznij chwilę i wróć.",
  model: "Bibo się zawiesił. Spróbuj jeszcze raz za moment.",
  siec: "Brak połączenia z Bibo. Spróbuj jeszcze raz.",
};

async function zadanie<T>(metoda: "GET" | "POST", sciezka: string, dane?: unknown): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`./api/${sciezka}`, {
      method: metoda,
      headers: { "X-Init-Data": initData, ...(dane ? { "Content-Type": "application/json" } : {}) },
      body: dane ? JSON.stringify(dane) : undefined,
    });
  } catch {
    throw new BladApi("siec", 0, KOMUNIKATY.siec);
  }
  const json = await r.json().catch(() => ({}));
  if (!r.ok) {
    const kod = json.blad ?? "siec";
    throw new BladApi(kod, r.status, json.komunikat ?? KOMUNIKATY[kod] ?? KOMUNIKATY.siec);
  }
  return json as T;
}

const prawdziwe: Api = {
  hub: () => zadanie("GET", "hub"),
  nowaSprawa: () => zadanie("POST", "sprawa"),
  zeznanie: (id, wymowka) => zadanie("POST", `sprawa/${id}/zeznanie`, { wymowka }),
  riposta: (id, dane) => zadanie("POST", `sprawa/${id}/riposta`, dane),
  zamknij: (id, kontrola_min) => zadanie("POST", `sprawa/${id}/zamknij`, { kontrola_min }),
  sprawa: (id) => zadanie("GET", `sprawa/${id}`),
  kontrola: (id, ruszylo) => zadanie("POST", `sprawa/${id}/kontrola`, { ruszylo }),
  kartoteka: () => zadanie("GET", "kartoteka"),
};

// --- Sztuczne API (tryb mock) -------------------------------------------------

const czekaj = (ms: number) => new Promise((r) => setTimeout(r, ms));

const BANK: Record<string, { nazwa: string; emoji: string; zatrzymanie: number; pytanie: string; podpowiedz: string }> = {
  perf: { nazwa: "Perfekcjonista", emoji: "🎩", zatrzymanie: 3, pytanie: "Jaka wersja na 60% przydałaby się już dziś, nawet bez tego ideału?", podpowiedz: "Szkielet nie blokuje szlifów. Te mogą dojść później." },
  jutro: { nazwa: "Jutrzejszy Ja", emoji: "📅", zatrzymanie: 2, pytanie: "Co takiego będzie jutro, czego nie ma teraz? Konkretnie.", podpowiedz: "Jutro masz te same 24 godziny i o jedną sprawę więcej." },
  paliwo: { nazwa: "Brak Paliwa", emoji: "🔋", zatrzymanie: 1, pytanie: "Czy to zmęczenie, czy niechęć do tej jednej rzeczy? Po czym to poznajesz?", podpowiedz: "Jeśli to prawdziwe zmęczenie, uniewinnienie to też dobry wynik." },
  mgla: { nazwa: "Mgła Startowa", emoji: "🌫️", zatrzymanie: 1, pytanie: "Gdybyś miał zrobić tylko pierwsze 5 minut, co by to było?", podpowiedz: "Nie musisz znać całości. Wystarczy pierwszy ruch." },
};

function klasyfikuj(t: string) {
  t = t.toLowerCase();
  if (/research|idealn|perfek|najpierw/.test(t)) return "perf";
  if (/jutr|później|potem|wieczorem/.test(t)) return "jutro";
  if (/zmęcz|siły|padam|wykończ/.test(t)) return "paliwo";
  return "mgla";
}

function sztuczne(): Api {
  let numer = 7;
  let ostatnia: { id: string; typ: string; krok?: string; werdykt?: Werdykt } | null = null;
  return {
    async hub() {
      await czekaj(250);
      return {
        tryby: [
          { id: "detektyw", nazwa: "Bibotektyw", opis: "Przesłuchaj wymówkę, która Cię blokuje", aktywny: true },
          { id: "misja10", nazwa: "Misja 10 minut", opis: "Tylko 10 minut, potem wolno przestać", aktywny: false },
          { id: "zrzut", nazwa: "Zrzut z głowy", opis: "Wszystko na stół, wybierasz jedno", aktywny: false },
        ],
        statystyki: { zamkniete: 6, obalone: 4, najczestszy: { nazwa: "Perfekcjonista", emoji: "🎩" } },
      };
    },
    async nowaSprawa() {
      await czekaj(200);
      ostatnia = { id: `s_mock${numer}`, typ: "mgla" };
      return { id: ostatnia.id, numer };
    },
    async zeznanie(_id, wymowka) {
      await czekaj(1500);
      if (/błąd|blad/i.test(wymowka)) throw new BladApi("model", 503, KOMUNIKATY.model);
      const typ = klasyfikuj(wymowka);
      if (ostatnia) ostatnia.typ = typ;
      const b = BANK[typ];
      return { podejrzany: { nazwa: b.nazwa, emoji: b.emoji, nowy: false, zatrzymanie: b.zatrzymanie, ostatnio: "2026-09-19" },
               pytanie: b.pytanie, podpowiedz: b.podpowiedz, zrodlo: "model" };
    },
    async riposta(_id, dane) {
      await czekaj(1500);
      let w: Wyrok;
      if ("uniewinnienie" in dane) {
        w = { werdykt: "uniewinniona", podsumowanie: "Uczciwie: dziś baterie są na zerze i to nie jest wymówka. Odpoczynek to też ruch do przodu.",
              krok: "Zamknij laptopa i wyjdź na 10 minut bez telefonu", zrodlo: "model" };
      } else if (dane.riposta.trim().length < 12) {
        w = { werdykt: "czesciowo", podsumowanie: "Coś w tej wymówce jest, ale da się ruszyć w mniejszej wersji.",
              krok: "Otwórz to zadanie i napisz jedno zdanie, od czego zaczniesz", zrodlo: "model" };
      } else {
        const perf = ostatnia?.typ === "perf";
        w = { werdykt: "obalona",
              podsumowanie: perf ? "Perfekcjonizm to strach przed startem w ładnym płaszczu. Szkielet teraz, szlify w kolejnym kroku."
                                 : "Wymówka nie przetrwała jednego pytania. Nie potrzebujesz całości, żeby ruszyć.",
              krok: perf ? "Otwórz repo i utwórz pusty index.html z trzema sekcjami" : "Otwórz plik i napisz pierwsze zdanie, byle jakie",
              zrodlo: "model" };
      }
      if (ostatnia) { ostatnia.krok = w.krok; ostatnia.werdykt = w.werdykt; }
      return w;
    },
    async zamknij(_id, kontrolaMin) {
      await czekaj(400);
      numer++;
      const kontrola = kontrolaMin ? new Date(Date.now() + kontrolaMin * 60_000).toISOString() : null;
      return { ok: true, kontrola };
    },
    async sprawa(id) {
      await czekaj(300);
      const b = BANK[ostatnia?.typ ?? "perf"];
      return { id, numer: 7, podejrzany: { nazwa: b.nazwa, emoji: b.emoji },
               krok: ostatnia?.krok ?? "Otwórz repo i utwórz pusty index.html z trzema sekcjami",
               werdykt: ostatnia?.werdykt ?? "obalona", kontrola: new Date().toISOString() };
    },
    async kontrola() {
      await czekaj(400);
      return { ok: true };
    },
    async kartoteka() {
      await czekaj(300);
      return {
        podejrzani: [
          { nazwa: "Perfekcjonista", emoji: "🎩", zatrzymania: 5, obalone: 4, ruszylo: 2, ostatnio: "2026-09-24" },
          { nazwa: "Jutrzejszy Ja", emoji: "📅", zatrzymania: 3, obalone: 2, ruszylo: 1, ostatnio: "2026-09-22" },
          { nazwa: "Research Bez Dna", emoji: "🔎", zatrzymania: 2, obalone: 1, ruszylo: 1, ostatnio: "2026-09-20" },
          { nazwa: "Brak Paliwa", emoji: "🔋", zatrzymania: 1, obalone: 0, ruszylo: 0, ostatnio: "2026-09-18" },
          { nazwa: "Mgła Startowa", emoji: "🌫️", zatrzymania: 1, obalone: 1, ruszylo: 0, ostatnio: "2026-09-17" },
          { nazwa: "Tylko Sprawdzę", emoji: "📱", zatrzymania: 1, obalone: 1, ruszylo: 0, ostatnio: "2026-09-22" },
        ],
        sprawy: [],
      };
    },
  };
}

export const api: Api = sztuczneApi ? sztuczne() : prawdziwe;
