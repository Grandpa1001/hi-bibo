/** Wspólne elementy interfejsu w stylu Bibo (style guide: czarna kreska, biel, turkus). */
import type { ComponentChildren } from "preact";
import { useEffect } from "preact/hooks";
import { drugi, drugiNatywny, glowny, mock, popupMock, wstecz, wTelegramie, type Przycisk } from "../tg";
import { blad } from "../stan";

export type Poza = "logo" | "detektyw" | "mysli" | "radosc" | "skupienie" | "ruch";

export function Postac({ poza, klasa, opis = "" }: { poza: Poza; klasa?: string; opis?: string }) {
  return <img class={`postac ${klasa ?? ""}`} src={`./postaci/${poza}.png`} alt={opis} draggable={false} />;
}

export function Dymek({ poza, etykieta, children }: { poza: Poza; etykieta?: string; children: ComponentChildren }) {
  return (
    <div class="mowca">
      <Postac poza={poza} />
      <div class="dymek">
        {etykieta && <small>{etykieta}</small>}
        <div class="dymek-tresc">{children}</div>
      </div>
    </div>
  );
}

export function Panel({ children, klasa }: { children: ComponentChildren; klasa?: string }) {
  return <section class={`panel ${klasa ?? ""}`}>{children}</section>;
}

export function Etykieta({ lewa, prawa }: { lewa: string; prawa?: string }) {
  return <div class="etykieta"><span>{lewa}</span>{prawa && <span>{prawa}</span>}</div>;
}

/** Deklaracja przycisków natywnych dla ekranu (sprząta po odmontowaniu). */
export function usePrzyciski(g: Przycisk | null, d: Przycisk | null = null, w: (() => void) | null = null) {
  useEffect(() => {
    glowny.value = g;
    drugi.value = d;
    wstecz.value = w;
  });
  useEffect(() => () => { glowny.value = null; drugi.value = null; wstecz.value = null; }, []);
}

/** Dolny pasek: w mocku rysuje oba przyciski, w starym Telegramie tylko drugorzędny. */
export function PasekDolny() {
  const g = glowny.value;
  const d = drugi.value;
  const rysujG = !wTelegramie && g;
  const rysujD = !drugiNatywny && d;
  if (!rysujG && !rysujD) return null;
  return (
    <div class="pasek">
      {rysujD && <button type="button" class="btn-drugi" disabled={d.wylaczony} onClick={d.onClick}>{d.tekst}</button>}
      {rysujG && (
        <button type="button" class="btn-glowny" disabled={g.wylaczony || g.postep} onClick={g.onClick}>
          {g.postep ? <span class="kropki" aria-label="Czekam"><i /><i /><i /></span> : g.tekst}
        </button>
      )}
      {mock && <div class="pasek-uwaga">tryb mock · w Telegramie to natywne przyciski</div>}
    </div>
  );
}

/** Nagłówek w trybie mock (w Telegramie rysuje go klient). */
export function NaglowekMock({ tytul }: { tytul: string }) {
  if (wTelegramie) return null;
  const w = wstecz.value;
  return (
    <header class="naglowek-mock">
      <span class="nm-lewo">{w && <button type="button" onClick={w}>‹ Wstecz</button>}</span>
      <b>{tytul}</b>
      <span class="nm-prawo">mock</span>
    </header>
  );
}

export function PopupMock() {
  const p = popupMock.value;
  useEffect(() => {
    if (!p) return;
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") popupMock.value = null; };
    addEventListener("keydown", esc);
    return () => removeEventListener("keydown", esc);
  }, [p]);
  if (!p) return null;
  return (
    <div class="popup" role="dialog" aria-modal="true" onClick={() => (popupMock.value = null)}>
      <div class="popup-box" onClick={(e) => e.stopPropagation()}>
        <b>{p.tytul}</b>
        <p>{p.tresc}</p>
        <button type="button" class="btn-glowny" autoFocus onClick={() => (popupMock.value = null)}>OK</button>
      </div>
    </div>
  );
}

export function Blad() {
  const b = blad.value;
  if (!b) return null;
  return (
    <div class="blad" role="alert">
      <Dymek poza="mysli" etykieta="Coś się zacięło">
        <p>{b.komunikat}</p>
        <button type="button" class="btn-drugi maly" onClick={b.ponow}>Spróbuj jeszcze raz</button>
      </Dymek>
    </div>
  );
}

export function Czekanie({ poza, tekst, podpis }: { poza: Poza; tekst: string; podpis: string }) {
  return (
    <div class="czekanie" aria-live="polite">
      <div class="czekanie-postac">
        <Postac poza={poza} />
        <span class="mysl" aria-hidden="true"><span class="kropki"><i /><i /><i /></span></span>
      </div>
      <p>{tekst}</p>
      <small>{podpis}</small>
    </div>
  );
}
