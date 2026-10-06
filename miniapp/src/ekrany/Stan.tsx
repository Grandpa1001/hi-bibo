/** Check-in stanu dnia (FR-1, FR-2, FR-11 w Mini App).
 *  Pad 4×4 podzielony na cztery podpisane ćwiartki: jedno stuknięcie zapisuje wpis (bez pisania),
 *  potem opcjonalnie stan uwagi i jedno słowo. Pole dalej od środka = silniejszy stan. */
import { useEffect, useState } from "preact/hooks";
import { api, BladApi, type Cwiartka, type StanWidok, type Uwaga } from "../api";
import { blad, idz } from "../stan";
import { haptyka } from "../tg";
import { IKONA_TRYBU, IKONA_UWAGI, IkonaKsiezyc, IkonaPiorun, IkonaSmutek, IkonaUsmiech } from "../ui/Ikony";
import { Dymek, usePrzyciski, type Poza } from "../ui/ui";
import { NAZWY_TRYBOW, natezenie, pole, UWAGA_NAZWA, Widget } from "../ui/Widget";

const OPIS_E: Record<number, string> = { 2: "bardzo wysoka", 1: "raczej wysoka", [-1]: "raczej niska", [-2]: "bardzo niska" };
const OPIS_P: Record<number, string> = { [-2]: "bardzo nieprzyjemnie", [-1]: "raczej nieprzyjemnie", 1: "raczej przyjemnie", 2: "bardzo przyjemnie" };
const UWAGI: Uwaga[] = ["hypofocus", "normal", "hyperfocus"];
const POZA_TRYBU: Record<Cwiartka, Poza> = { peak: "radosc", steady: "skupienie", tension: "ruch", recovery: "mysli" };

/** Ćwiartki w układzie padu: góra = więcej energii, prawa = przyjemniej. Każda ma 2×2 pola (energia, przyjemność). */
const CWIARTKI: { c: Cwiartka; opis: string; pola: [number, number][] }[] = [
  { c: "tension", opis: "dużo energii, nieprzyjemnie", pola: [[2, -2], [2, -1], [1, -2], [1, -1]] },
  { c: "peak", opis: "dużo energii, przyjemnie", pola: [[2, 1], [2, 2], [1, 1], [1, 2]] },
  { c: "recovery", opis: "mało energii, nieprzyjemnie", pola: [[-1, -2], [-1, -1], [-2, -2], [-2, -1]] },
  { c: "steady", opis: "mało energii, przyjemnie", pola: [[-1, 1], [-1, 2], [-2, 1], [-2, 2]] },
];

export function Stan() {
  const [widok, setWidok] = useState<StanWidok | null>(null);
  const [wynik, setWynik] = useState<{ reakcja: string } | null>(null);
  const [komunikat, setKomunikat] = useState<string | null>(null);
  const [wysylam, setWysylam] = useState(false);
  const [wybrane, setWybrane] = useState<string | null>(null);

  useEffect(() => {
    api.stan().then(setWidok).catch((e) => {
      blad.value = { komunikat: e instanceof BladApi ? e.message : "Nie udało się otworzyć stanu dnia.", ponow: () => location.reload() };
    });
  }, []);

  async function wykonaj(akcja: () => Promise<StanWidok>, po?: (w: StanWidok) => void) {
    if (wysylam) return false;
    setWysylam(true);
    blad.value = null;
    try {
      const w = await akcja();
      setWidok(w);
      po?.(w);
      return true;
    } catch (e) {
      blad.value = { komunikat: e instanceof BladApi ? e.message : "Nie udało się zapisać. Nic nie zostało zmienione.", ponow: () => { blad.value = null; } };
      return false;
    } finally {
      setWysylam(false);
    }
  }

  async function tap(e: number, p: number) {
    haptyka("lekko");
    setWybrane(`${e}${p}`);
    const ok = await wykonaj(() => api.stanWpis(e, p), (w) => { setWynik({ reakcja: w.reakcja ?? "" }); setKomunikat(null); });
    if (ok) haptyka("sukces");
    else setWybrane(null);
  }

  usePrzyciski(wynik ? { tekst: "Gotowe", onClick: () => idz("dzis") } : null, null, () => idz("dzis"));

  if (widok && !widok.wlaczone) {
    return <div class="ekran"><Dymek poza="mysli" etykieta="Stan dnia"><p>Stan dnia jest wyłączony w tej instancji.</p></Dymek></div>;
  }
  const dzis = widok?.dzis ?? null;

  if (wynik && dzis) {
    const linie = wynik.reakcja.split("\n");
    return (
      <div class="ekran">
        <Widget dzis={dzis} tydzien={widok?.tydzien ?? []} />
        <Dymek poza={POZA_TRYBU[dzis.cwiartka]} etykieta={`Zapisane · ${dzis.nazwa}`}>
          <p>{linie[0]}</p>
          {linie[1] && <p class="krok-reakcji">{linie[1].replace(/^👣\s*/, "")}</p>}
        </Dymek>

        <section class="sekcja" aria-labelledby="uwaga-tytul">
          <h2 id="uwaga-tytul" class="sekcja-tytul">Jak z uwagą? <small>opcjonalnie</small></h2>
          <div class="segmenty" role="radiogroup" aria-labelledby="uwaga-tytul">
            {UWAGI.map((u) => {
              const I = IKONA_UWAGI[u];
              return (
                <button type="button" key={u} role="radio" aria-checked={dzis.uwaga === u} class={`segment${dzis.uwaga === u ? " wybrany" : ""}`}
                        disabled={wysylam} onClick={() => wykonaj(() => api.stanUwaga(u), (w) => setKomunikat(w.komunikat ?? null))}>
                  <I rozmiar={22} /><span>{UWAGA_NAZWA[u]}</span>
                </button>
              );
            })}
          </div>
          {komunikat && <p class="potwierdzenie" role="status">{komunikat.split("\n").filter(Boolean).join(" ")}</p>}
        </section>

        <section class="sekcja" aria-labelledby="slowo-tytul">
          <h2 id="slowo-tytul" class="sekcja-tytul">Jedno słowo? <small>opcjonalnie</small></h2>
          <div class="chipy">
            {dzis.slowa.map((s) => (
              <button type="button" key={s} class={`chip${dzis.slowo === s ? " wybrany" : ""}`} aria-pressed={dzis.slowo === s} disabled={wysylam}
                      onClick={() => wykonaj(() => api.stanSlowo(s))}>{s}</button>
            ))}
          </div>
        </section>
      </div>
    );
  }

  const [ae, ap] = dzis ? pole(dzis.energia, dzis.przyjemnosc) : [null, null];
  return (
    <div class="ekran">
      <Dymek poza="logo" etykieta="Stan dnia">
        <p>Jak się dziś czujesz? Stuknij jedno pole.</p>
        {dzis && <p class="podpowiedz-tekst">Dziś: {dzis.nazwa}. Nowy wpis zastąpi ten tryb.</p>}
      </Dymek>

      <div class="pad-ramka">
        <span class="pad-os pad-gora"><IkonaPiorun rozmiar={16} /> więcej energii</span>
        <span class="pad-os pad-lewo" aria-hidden="true"><IkonaSmutek rozmiar={18} /></span>
        <div class="pad" role="group" aria-label="Energia i samopoczucie">
          {CWIARTKI.map(({ c, opis, pola }) => {
            const I = IKONA_TRYBU[c];
            return (
              <div key={c} class={`cwiartka c-${c}`} role="group" aria-label={`${NAZWY_TRYBOW[c]}: ${opis}`}>
                <span class="cwiartka-nazwa" aria-hidden="true"><I rozmiar={14} />{NAZWY_TRYBOW[c]}</span>
                {pola.map(([e, p]) => {
                  const klucz = `${e}${p}`;
                  const aktualne = e === ae && p === ap;
                  return (
                    <button type="button" key={klucz} disabled={wysylam}
                            class={`pole n${natezenie(e, p)}${aktualne ? " aktualne" : ""}${wybrane === klucz ? " wybrane" : ""}`}
                            aria-label={`${NAZWY_TRYBOW[c]}: energia ${OPIS_E[e]}, ${OPIS_P[p]}${aktualne ? " (dzisiejszy wpis)" : ""}`}
                            onClick={() => tap(e, p)}>
                      <i />
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>
        <span class="pad-os pad-prawo" aria-hidden="true"><IkonaUsmiech rozmiar={18} /></span>
        <span class="pad-os pad-dol"><IkonaKsiezyc rozmiar={16} /> mniej energii</span>
      </div>
      <p class="podpowiedz-tekst srodek-tekst">W lewo: nieprzyjemnie · w prawo: przyjemnie. Im dalej od środka, tym mocniej.</p>
    </div>
  );
}
