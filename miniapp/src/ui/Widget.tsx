/** Widget stanu dnia (FR-8): tryb w kolorze ćwiartki, punkt na siatce, stan uwagi i 7 ostatnich dni.
 *  Kolor nigdy nie jest jedynym nośnikiem: tryb ma nazwę i ikonę, kropki mają podpis dnia i opis dla czytników. */
import { cwiartkaZOsi, type Cwiartka, type StanDzien, type StanDzis, type Uwaga } from "../api";
import { IKONA_TRYBU, IKONA_UWAGI, IkonaDalej, IkonaPytanie } from "./Ikony";

export const UWAGA_NAZWA: Record<Uwaga, string> = { hypofocus: "Rozproszony", normal: "W normie", hyperfocus: "Hiperfokus" };
export const NAZWY_TRYBOW: Record<Cwiartka, string> = { peak: "Szczyt", steady: "Stabilnie", tension: "Napięcie", recovery: "Regeneracja" };
const DNI = ["Nd", "Pn", "Wt", "Śr", "Cz", "Pt", "So"];
const DNI_PELNE = ["niedziela", "poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota"];

/** Wiersze od góry (energia wysoka → niska) i kolumny od lewej (nieprzyjemnie → przyjemnie), jak na klawiaturze w czacie. */
export const WIERSZE = [2, 1, -1, -2];
export const KOLUMNY = [-2, -1, 1, 2];

/** Oś 0 (nieużywana przez siatkę, ale dopuszczalna w danych) wpada tam, gdzie `stan.cwiartka`: energia 0 = niska, przyjemność 0 = przyjemnie. */
export function pole(e: number, p: number): [number, number] {
  return [e > 0 ? (e >= 2 ? 2 : 1) : (e <= -2 ? -2 : -1), p >= 0 ? (p >= 2 ? 2 : 1) : (p <= -2 ? -2 : -1)];
}

/** Natężenie pola: rogi siatki (|2|,|2|) są najmocniejsze, środek najsłabszy — „im głębszy kolor, tym silniejszy stan”. */
export function natezenie(e: number, p: number): 1 | 2 | 3 {
  const s = Math.abs(e) + Math.abs(p);
  return s >= 4 ? 3 : s === 3 ? 2 : 1;
}

export function MiniSiatka({ e, p }: { e?: number; p?: number }) {
  const [re, rp] = e === undefined || p === undefined ? [null, null] : pole(e, p);
  return (
    <div class="mini-siatka" aria-hidden="true">
      {WIERSZE.flatMap((w) => KOLUMNY.map((k) => (
        <i key={`${w}${k}`} class={`c-${cwiartkaZOsi(w, k)} n${natezenie(w, k)}${w === re && k === rp ? " punkt" : ""}`} />
      )))}
    </div>
  );
}

function dzienTygodnia(dzien: string) {
  return new Date(`${dzien}T12:00:00`).getDay();
}

export function Tydzien({ dni }: { dni: StanDzien[] }) {
  return (
    <ol class="tydzien" aria-label="Ostatnie 7 dni">
      {dni.map((d, i) => {
        const nazwa = d.cwiartka ? NAZWY_TRYBOW[d.cwiartka] : "brak wpisu";
        const IkonaU = d.uwaga && d.uwaga !== "normal" ? IKONA_UWAGI[d.uwaga] : null;
        return (
          <li key={d.dzien} class={i === dni.length - 1 ? "dzis" : ""}>
            <i class={d.cwiartka ? `c-${d.cwiartka}` : "pusty"} aria-hidden="true">{IkonaU && <IkonaU rozmiar={12} />}</i>
            <span aria-hidden="true">{DNI[dzienTygodnia(d.dzien)]}</span>
            <span class="sr">{`${DNI_PELNE[dzienTygodnia(d.dzien)]}: ${nazwa}${IkonaU ? `, ${UWAGA_NAZWA[d.uwaga!]}` : ""}`}</span>
          </li>
        );
      })}
    </ol>
  );
}

export function Widget({ dzis, tydzien, onClick }: { dzis: StanDzis | null; tydzien: StanDzien[]; onClick?: () => void }) {
  const IkonaT = dzis ? IKONA_TRYBU[dzis.cwiartka] : IkonaPytanie;
  const IkonaU = dzis ? IKONA_UWAGI[dzis.uwaga] : null;
  const opis = dzis
    ? `Stan dnia: ${dzis.nazwa}, uwaga: ${UWAGA_NAZWA[dzis.uwaga]}.${onClick ? " Otwórz, żeby zmienić." : ""}`
    : "Stan dnia: bez wpisu. Otwórz, żeby zapisać, jak się czujesz.";
  const Tag = onClick ? "button" : "div";
  return (
    <Tag type={onClick ? "button" : undefined} class={`widget ${dzis ? `t-${dzis.cwiartka}` : "t-brak"}${onClick ? " klikalny" : ""}`}
         onClick={onClick} aria-label={onClick ? opis : undefined}>
      <span class="widget-gora">
        <span class="widget-znak" aria-hidden="true"><IkonaT rozmiar={26} /></span>
        <span class="widget-tekst">
          <small>Stan dnia</small>
          <b>{dzis ? dzis.nazwa : "Jak się czujesz?"}</b>
          <span class="widget-uwaga">
            {IkonaU ? <><IkonaU rozmiar={16} /> {UWAGA_NAZWA[dzis!.uwaga]}{dzis!.slowo ? ` · ${dzis!.slowo}` : ""}</> : "Jedno stuknięcie, bez pisania"}
          </span>
        </span>
        <MiniSiatka e={dzis?.energia} p={dzis?.przyjemnosc} />
      </span>
      <Tydzien dni={tydzien} />
      {onClick && <span class="widget-cta" aria-hidden="true">{dzis ? "Zmień stan" : "Zapisz stan"} <IkonaDalej rozmiar={16} /></span>}
    </Tag>
  );
}
