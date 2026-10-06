/** Zakładka „Dziś”: stan dnia na górze, pod nim skrót do gier. */
import { useEffect, useState } from "preact/hooks";
import { api, type Hub, type StanWidok } from "../api";
import { idz } from "../stan";
import { DOMYSLNE_GRY, KartaGry } from "../ui/Gry";
import { Postac, usePrzyciski } from "../ui/ui";
import { Widget } from "../ui/Widget";

function powitanie() {
  const h = new Date().getHours();
  if (h < 5 || h >= 22) return "Nocna zmiana";
  if (h < 12) return "Dzień dobry";
  if (h < 18) return "Cześć";
  return "Dobry wieczór";
}

const dzisiaj = () => new Date().toLocaleDateString("pl-PL", { weekday: "long", day: "numeric", month: "long" });

export function Dzis() {
  const [stan, setStan] = useState<StanWidok | null>(null);
  const [hub, setHub] = useState<Hub | null>(null);
  useEffect(() => {
    api.stan().then(setStan).catch(() => setStan({ wlaczone: false }));   // brak widgetu przy błędzie, reszta działa
    api.hub().then(setHub).catch(() => setHub(null));
  }, []);
  usePrzyciski(null);

  const gry = hub?.tryby ?? DOMYSLNE_GRY;
  return (
    <div class="ekran">
      <header class="powitanie">
        <div>
          <small>{dzisiaj()}</small>
          <h1>{powitanie()}!</h1>
        </div>
        <Postac poza="logo" klasa="powitanie-postac" opis="Bibo" />
      </header>

      {stan === null && <div class="widget szkielet" aria-hidden="true" />}
      {stan?.wlaczone && <Widget dzis={stan.dzis ?? null} tydzien={stan.tydzien ?? []} onClick={() => idz("stan")} />}

      <section class="sekcja" aria-labelledby="gry-tytul">
        <div class="sekcja-naglowek">
          <h2 id="gry-tytul" class="sekcja-tytul">Gry z Bibo</h2>
          <button type="button" class="link" onClick={() => idz("gry", true)}>Wszystkie</button>
        </div>
        <div class="lista-gier">
          {gry.filter((g) => g.aktywny).map((g) => <KartaGry key={g.id} gra={g} onClick={() => idz("detektyw")} />)}
        </div>
      </section>
    </div>
  );
}
