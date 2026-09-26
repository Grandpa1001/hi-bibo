/** Przebieg sprawy: zeznanie → analiza → przesłuchanie → obrady → werdykt. */
import { KONTROLA_MIN } from "../konfig";
import { useEffect } from "preact/hooks";
import {
  odpowiedz, porzucSprawe, przelaczKontrole, sprawa, uzyjPodpowiedzi, wpiszRiposte, wpiszWymowke,
  zamknijAkta, zapewnijSprawe, zlozZeznanie, type Sprawa as S,
} from "../stan";
import { okienko } from "../tg";
import { Czekanie, Dymek, Etykieta, Panel, Postac, usePrzyciski } from "../ui/ui";

const data = () => new Date().toLocaleString("pl-PL", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });

// Przyciski natywne deklaruje tylko ekran-liść: efekt rodzica uruchamia się po efekcie
// dziecka i nadpisałby jego przyciski.
export function Sprawa() {
  const s = sprawa.value;
  useEffect(zapewnijSprawe, []);
  if (!s) return <CzekanieSprawy poza="detektyw" tekst="Otwieram akta" podpis="Nowa sprawa" />;
  switch (s.krok) {
    case "zeznanie": return <Zeznanie s={s} />;
    case "analiza": return <CzekanieSprawy poza="mysli" tekst="Analizuję zeznanie" podpis="Kto to jest i o co zapytać" />;
    case "przesluchanie": return <Przesluchanie s={s} />;
    case "obrady": return <CzekanieSprawy poza="detektyw" tekst="Sąd obraduje" podpis="Werdykt i pierwszy krok" />;
    case "werdykt": return <Werdykt s={s} />;
  }
}

function CzekanieSprawy(p: Parameters<typeof Czekanie>[0]) {
  usePrzyciski(null, null, porzucSprawe);
  return <Czekanie {...p} />;
}

function Zeznanie({ s }: { s: S }) {
  usePrzyciski({ tekst: "Złóż zeznanie", onClick: zlozZeznanie, wylaczony: !s.wymowka.trim() }, null, porzucSprawe);
  return (
    <div class="ekran">
      <Dymek poza="skupienie" etykieta="Bibo · detektyw">
        <p>Na krześle siedzi wymówka, nie Ty. Jak dokładnie brzmi? Tak, jak mówisz ją sobie w głowie.</p>
      </Dymek>
      <Panel>
        <Etykieta lewa={`Sprawa #${s.numer}`} prawa={data()} />
        <h2>Zeznanie wymówki</h2>
        <label class="lbl" for="wymowka">Wymówka mówi:</label>
        <textarea id="wymowka" rows={4} maxLength={500} value={s.wymowka}
                  placeholder="np. Zacznę, jak ogarnę wszystko inne…"
                  onInput={(e) => wpiszWymowke((e.target as HTMLTextAreaElement).value)} />
      </Panel>
      <p class="podpowiedz-tekst">Bez licznika. Jedno zdanie wystarczy.</p>
    </div>
  );
}

function Przesluchanie({ s }: { s: S }) {
  const z = s.zeznanie!;
  usePrzyciski({ tekst: "Odpowiedz", onClick: () => odpowiedz(false), wylaczony: !s.riposta.trim() }, null, porzucSprawe);
  const nr = String(z.podejrzany.zatrzymanie).padStart(2, "0");
  return (
    <div class="ekran">
      <Panel>
        <Etykieta lewa={`Sprawa #${s.numer}`} prawa={z.podejrzany.nowy ? "Nowy podejrzany" : "Podejrzany"} />
        <div class="podejrzany">
          <div class="zdjecie" aria-hidden="true">
            <span class="twarz">{z.podejrzany.emoji}</span>
            <span class="numer">NR {String(s.numer).padStart(2, "0")}-{nr}</span>
          </div>
          <div class="kartoteka-wpis">
            <b>{z.podejrzany.nazwa}</b>
            {z.podejrzany.ostatnio && <span>ostatnio widziany: {z.podejrzany.ostatnio.split("-").reverse().slice(0, 2).join(".")}</span>}
            <span class="pigulka">{z.podejrzany.nowy ? "pierwsze zatrzymanie" : `${z.podejrzany.zatrzymanie}. zatrzymanie`}</span>
          </div>
        </div>
        <blockquote>„{s.wymowka}”</blockquote>
      </Panel>

      <Dymek poza="detektyw" etykieta="Pytanie śledczego"><p>{z.pytanie}</p></Dymek>

      <div>
        <label class="lbl" for="riposta">Twoja riposta</label>
        <textarea id="riposta" rows={3} maxLength={500} value={s.riposta}
                  onInput={(e) => wpiszRiposte((e.target as HTMLTextAreaElement).value)} />
      </div>
      <div class="rzad">
        <button type="button" class="btn-drugi" disabled={s.podpowiedzUzyta}
                onClick={() => { uzyjPodpowiedzi(); okienko("💡 Podpowiedź", z.podpowiedz); }}>💡 Podpowiedź</button>
        <button type="button" class="btn-drugi" onClick={() => odpowiedz(true)}>🟢 Ona ma rację</button>
      </div>
    </div>
  );
}

const PIECZATKA = { obalona: "OBALONA", czesciowo: "CZĘŚCIOWO", uniewinniona: "UNIEWINNIONA" } as const;
const POZA_WERDYKTU = { obalona: "radosc", czesciowo: "mysli", uniewinniona: "skupienie" } as const;

function Werdykt({ s }: { s: S }) {
  const w = s.wyrok!;
  const z = s.zeznanie!;
  usePrzyciski(
    { tekst: "Zamknij akta i wróć do Bibo", onClick: () => zamknijAkta(KONTROLA_MIN), postep: s.zamykanie },
    { tekst: s.kontrola ? `⏰ Kontrola za ${KONTROLA_MIN} min ✓` : `⏰ Zajrzyj za ${KONTROLA_MIN} min`, onClick: przelaczKontrole },
    null,
  );
  return (
    <div class="ekran">
      <div class="werdykt-hero">
        <Postac poza={POZA_WERDYKTU[w.werdykt]} klasa="wskok" />
        <span class={`pieczatka ${w.werdykt}`}>{PIECZATKA[w.werdykt]}</span>
      </div>
      <Panel>
        <Etykieta lewa={`Sprawa #${s.numer} · zamknięta`} prawa={`${z.podejrzany.emoji} ${z.podejrzany.nazwa}`} />
        <h2>Werdykt</h2>
        <p class="podsumowanie">{w.podsumowanie}</p>
      </Panel>
      <div class="karta-kroku">
        <div>
          <span>👣 Pierwszy krok · ≤ 5 min</span>
          <p>{w.krok}</p>
        </div>
        <Postac poza={w.werdykt === "uniewinniona" ? "skupienie" : "ruch"} />
      </div>
    </div>
  );
}
