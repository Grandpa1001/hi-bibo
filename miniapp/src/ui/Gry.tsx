/** Karty gier — wspólne dla zakładki „Dziś” (skrót) i „Gry” (pełna lista). */
import type { Hub } from "../api";
import { IKONA_GRY, IkonaDalej, IkonaGry } from "./Ikony";
import { Postac, type Poza } from "./ui";

export type Gra = Hub["tryby"][number];
export const DOMYSLNE_GRY: Gra[] = [
  { id: "detektyw", nazwa: "Bibotektyw", opis: "Sprawdź, co Cię zatrzymuje, i znajdź mały krok", aktywny: true },
];
const POZY: Record<string, Poza> = { detektyw: "detektyw", misja10: "ruch", zrzut: "skupienie" };

export function KartaGry({ gra, onClick, duza = false }: { gra: Gra; onClick?: () => void; duza?: boolean }) {
  const I = IKONA_GRY[gra.id] ?? IkonaGry;
  return (
    <button type="button" class={`gra${gra.aktywny ? " on" : ""}${duza ? " duza" : ""}`} disabled={!gra.aktywny}
            onClick={gra.aktywny ? onClick : undefined}>
      <span class="gra-obraz" aria-hidden="true">
        {duza ? <Postac poza={POZY[gra.id] ?? "logo"} /> : <I rozmiar={24} />}
      </span>
      <span class="gra-opis">
        <b>{gra.nazwa}</b>
        <small>{gra.opis}</small>
      </span>
      {gra.aktywny ? <IkonaDalej klasa="gra-strzalka" /> : <span class="tag">Wkrótce</span>}
    </button>
  );
}
