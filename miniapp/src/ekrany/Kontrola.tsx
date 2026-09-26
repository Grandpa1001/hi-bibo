/** Kontrola po sprawie: „ruszyło?” — otwierana z wiadomości w czacie (#/kontrola/<id>). */
import { useEffect, useState } from "preact/hooks";
import { api, BladApi, type SprawaInfo } from "../api";
import { idz } from "../stan";
import { haptyka, zamknij } from "../tg";
import { Czekanie, Dymek, Postac, usePrzyciski } from "../ui/ui";

export function Kontrola({ id }: { id: string }) {
  const [info, setInfo] = useState<SprawaInfo | null>(null);
  const [blad, setBlad] = useState<string | null>(null);
  const [wynik, setWynik] = useState<"ruszylo" | "nie" | null>(null);
  const [wysylam, setWysylam] = useState(false);

  useEffect(() => {
    api.sprawa(id).then(setInfo).catch((e) => setBlad(e instanceof BladApi ? e.message : "Nie udało się otworzyć akt."));
  }, [id]);

  async function odpowiedz(ruszylo: boolean) {
    if (wysylam) return;
    setWysylam(true);
    try {
      await api.kontrola(id, ruszylo);
      haptyka(ruszylo ? "sukces" : "lekko");
      setWynik(ruszylo ? "ruszylo" : "nie");
      setTimeout(zamknij, ruszylo ? 1600 : 900);
    } catch (e) {
      setBlad(e instanceof BladApi ? e.message : "Nie udało się zapisać odpowiedzi.");
      setWysylam(false);
    }
  }

  const gotowe = !!info && !wynik && !blad;
  usePrzyciski(
    gotowe ? { tekst: "✅ Ruszyło", onClick: () => odpowiedz(true), postep: wysylam } : null,
    gotowe ? { tekst: "🐢 Jeszcze nie", onClick: () => odpowiedz(false), wylaczony: wysylam } : null,
    blad ? () => idz("start") : null,
  );

  if (blad) return <div class="ekran"><Dymek poza="mysli" etykieta="Kontrola"><p>{blad}</p></Dymek></div>;
  if (!info) return <Czekanie poza="detektyw" tekst="Wyciągam akta" podpis="Kontrola po sprawie" />;
  if (wynik === "ruszylo") return (
    <div class="ekran srodek"><Postac poza="radosc" klasa="duza wskok" /><h2>Akta: ruszyło ✓</h2><p>Zapisane w kartotece. Działaj dalej.</p></div>
  );
  if (wynik === "nie") return (
    <div class="ekran srodek"><Postac poza="skupienie" klasa="duza" /><h2>Spoko, pogadajmy</h2><p>Bibo zaraz zapyta w czacie, co blokuje.</p></div>
  );
  return (
    <div class="ekran">
      <div class="werdykt-hero"><Postac poza="ruch" klasa="wskok" /></div>
      <Dymek poza="detektyw" etykieta={`Kontrola · sprawa #${info.numer}`}>
        <p>Umawialiśmy się na pierwszy krok. Ruszyło?</p>
      </Dymek>
      <div class="karta-kroku">
        <div><span>👣 Krok ze sprawy · {info.podejrzany.emoji} {info.podejrzany.nazwa}</span><p>{info.krok}</p></div>
      </div>
    </div>
  );
}
