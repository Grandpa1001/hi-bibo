import "./fonty.css";
import "./styl.css";

import { render } from "preact";
import { Kartoteka } from "./ekrany/Kartoteka";
import { Kontrola } from "./ekrany/Kontrola";
import { Sprawa } from "./ekrany/Sprawa";
import { Start } from "./ekrany/Start";
import { trasa } from "./stan";
import { mock, start, wTelegramie, zamknieta } from "./tg";
import { Blad, NaglowekMock, PasekDolny, Postac, PopupMock } from "./ui/ui";

start();

const TYTULY = { start: "Bibo", sprawa: "Bibotektyw", kartoteka: "Kartoteka", kontrola: "Kontrola" } as const;

function App() {
  if (!wTelegramie && !mock) {
    return (
      <div class="ekran srodek">
        <Postac poza="logo" klasa="duza" opis="Bibo" />
        <h2>Otwórz z czatu z Bibo</h2>
        <p>Ta aplikacja działa w Telegramie — użyj przycisku <b>🎲 Tryby</b> obok pola wiadomości.</p>
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
      <NaglowekMock tytul={TYTULY[t.ekran]} />
      <main class="tresc">
        {t.ekran === "start" && <Start />}
        {t.ekran === "sprawa" && <Sprawa />}
        {t.ekran === "kartoteka" && <Kartoteka />}
        {t.ekran === "kontrola" && <Kontrola id={t.id} />}
        <Blad />
      </main>
      <PasekDolny />
      <PopupMock />
    </>
  );
}

render(<App />, document.getElementById("app")!);
