/** Zakładka „Gry”: wszystkie tryby; każda gra ma własną stronę z podzakładkami. */
import { useEffect, useState } from "preact/hooks";
import { api, type Hub } from "../api";
import { idz } from "../stan";
import { DOMYSLNE_GRY, KartaGry } from "../ui/Gry";
import { usePrzyciski } from "../ui/ui";

export function Gry() {
  const [hub, setHub] = useState<Hub | null>(null);
  useEffect(() => { api.hub().then(setHub).catch(() => setHub(null)); }, []);
  usePrzyciski(null);

  const gry = hub?.tryby ?? DOMYSLNE_GRY;
  return (
    <div class="ekran">
      <header class="tytul-ekranu">
        <h1>Gry</h1>
        <p>Krótkie tryby, które pomagają ruszyć z miejsca. Bez punktów i bez serii.</p>
      </header>
      <div class="lista-gier">
        {gry.map((g) => <KartaGry key={g.id} gra={g} duza onClick={() => idz("detektyw")} />)}
      </div>
      {gry.every((g) => g.aktywny) && <p class="podpowiedz-tekst srodek-tekst">Kolejne gry są w drodze.</p>}
    </div>
  );
}
