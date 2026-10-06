/** Karta „Twój tydzień” (FR-9, FR-16): rozkład trybów, rozkład stanów uwagi i po jednym wniosku.
 *  Kolor nigdy sam: każdy segment ma nazwę i liczbę dni w legendzie. */
import type { Cwiartka, Podsumowanie, Uwaga } from "../api";
import { IKONA_UWAGI } from "./Ikony";
import { NAZWY_TRYBOW, UWAGA_NAZWA } from "./Widget";

const KOLEJNOSC: Cwiartka[] = ["peak", "steady", "tension", "recovery"];
const UWAGI: Uwaga[] = ["normal", "hypofocus", "hyperfocus"];
const dm = (iso: string) => iso.slice(8, 10) + "." + iso.slice(5, 7);

export function PodsumowanieTygodnia({ p }: { p: Podsumowanie }) {
  return (
    <section class="tydzien-karta" aria-labelledby="tydzien-tytul">
      <div class="sekcja-naglowek">
        <h2 id="tydzien-tytul" class="sekcja-tytul">Twój tydzień</h2>
        <span class="tydzien-daty">{dm(p.od)}–{dm(p.do)}</span>
      </div>

      <div class="rozklad" role="img"
           aria-label={KOLEJNOSC.filter((c) => p.tryby[c]).map((c) => `${NAZWY_TRYBOW[c]}: ${p.tryby[c]}`).join(", ")}>
        {KOLEJNOSC.filter((c) => p.tryby[c]).map((c) => <i key={c} class={`c-${c}`} style={{ flexGrow: p.tryby[c] }} />)}
      </div>
      <ul class="legenda-trybow">
        {KOLEJNOSC.filter((c) => p.tryby[c]).map((c) => (
          <li key={c} class={`c-${c}`}><i /> {NAZWY_TRYBOW[c]} <b>{p.tryby[c]}</b></li>
        ))}
        {p.dni_bez_wpisu > 0 && <li class="brak"><i /> bez wpisu <b>{p.dni_bez_wpisu}</b></li>}
      </ul>
      {p.wniosek_trybow && <p class="wniosek">{p.wniosek_trybow}</p>}

      <h3 class="tydzien-podtytul">Uwaga, liczba dni</h3>
      <ul class="chipy-uwagi">
        {UWAGI.filter((u) => p.uwaga[u]).map((u) => {
          const I = IKONA_UWAGI[u];
          return <li key={u}><I rozmiar={16} /> {UWAGA_NAZWA[u]} <b>{p.uwaga[u]}</b></li>;
        })}
      </ul>
      {p.wniosek_uwagi && <p class="wniosek">{p.wniosek_uwagi}</p>}
    </section>
  );
}
