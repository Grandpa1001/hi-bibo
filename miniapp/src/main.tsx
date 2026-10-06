import "./fonty.css";
import "./styl.css";

import { render } from "preact";
import { Detektyw } from "./ekrany/Detektyw";
import { Dzis } from "./ekrany/Dzis";
import { Gry } from "./ekrany/Gry";
import { Kontrola } from "./ekrany/Kontrola";
import { Sprawa } from "./ekrany/Sprawa";
import { Stan } from "./ekrany/Stan";
import { trasa } from "./stan";
import { mock, start, sztuczneApi, wTelegramie, zamknieta } from "./tg";
import { Blad, NaglowekMock, PasekDolny, Postac, PopupMock, Zakladki } from "./ui/ui";

start();

const TYTULY = { dzis: "Bibo", gry: "Bibo", detektyw: "Bibotektyw", sprawa: "Bibotektyw", kontrola: "Kontrola", stan: "Stan dnia" } as const;

function App() {
  if (!wTelegramie && !mock) {
    return (
      <div class="ekran srodek">
        <Postac poza="logo" klasa="duza" opis="Bibo" />
        <h2>Otwórz z czatu z Bibo</h2>
        <p>Ta aplikacja działa w Telegramie — użyj przycisku <b>Bibo</b> obok pola wiadomości.</p>
      </div>
    );
  }
  if (zamknieta.value) {
    return (
      <div class="ekran srodek">
        <Postac poza="radosc" klasa="duza" />
        <h2>Mini App zamknięta</h2>
        <p>W Telegramie wracasz teraz do czatu, a Bibo komentuje wynik.</p>
        <button type="button" class="btn-drugi" onClick={() => { zamknieta.value = false; location.hash = "#/"; }}>Otwórz ponownie (mock)</button>
      </div>
    );
  }
  const t = trasa.value;
  return (
    <>
      <div class="gora">
        <NaglowekMock tytul={TYTULY[t.ekran]} />
        {wTelegramie && sztuczneApi && <div class="demo">Tryb demo · odpowiedzi Bibo są udawane</div>}
        {(t.ekran === "dzis" || t.ekran === "gry" || t.ekran === "detektyw") && <Zakladki aktywna={t.ekran === "dzis" ? "dzis" : "gry"} />}
      </div>
      <main class="tresc">
        {t.ekran === "dzis" && <Dzis />}
        {t.ekran === "gry" && <Gry />}
        {t.ekran === "detektyw" && <Detektyw zakladka={t.zakladka} />}
        {t.ekran === "sprawa" && <Sprawa />}
        {t.ekran === "kontrola" && <Kontrola id={t.id} />}
        {t.ekran === "stan" && <Stan />}
        <Blad />
      </main>
      <PasekDolny />
      <PopupMock />
    </>
  );
}

render(<App />, document.getElementById("app")!);
