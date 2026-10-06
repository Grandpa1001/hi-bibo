/** Bibotektyw: strona gry z podzakładkami „Śledztwo” (jak to działa + statystyki) i „Kartoteka”. */
import { useEffect, useState } from "preact/hooks";
import { api, type Hub } from "../api";
import { idz, nowaSprawa, type ZakladkaDetektywa } from "../stan";
import { IkonaKrok, IkonaLupa, IkonaTeczka, IkonaZrzut } from "../ui/Ikony";
import { Postac, usePrzyciski } from "../ui/ui";
import { KartotekaTresc } from "./Kartoteka";

const KROKI = [
  { I: IkonaZrzut, tytul: "Zeznanie", opis: "Zapisujesz myśl, która Cię zatrzymuje — tak, jak brzmi w głowie." },
  { I: IkonaLupa, tytul: "Przesłuchanie", opis: "Bibo zadaje jedno pytanie. Odpowiadasz albo przyznajesz, że ma rację." },
  { I: IkonaKrok, tytul: "Werdykt", opis: "Dostajesz jeden krok na 5 minut i opcjonalną kontrolę." },
];

export function Detektyw({ zakladka }: { zakladka: ZakladkaDetektywa }) {
  const [hub, setHub] = useState<Hub | null>(null);
  useEffect(() => { api.hub().then(setHub).catch(() => setHub(null)); }, []);
  usePrzyciski({ tekst: "Nowa sprawa", onClick: nowaSprawa }, null, () => idz("gry"));

  const s = hub?.statystyki;
  return (
    <div class="ekran">
      <header class="gra-naglowek">
        <div>
          <small>Gra</small>
          <h1>Bibotektyw</h1>
          <p>Sprawdź, co Cię zatrzymuje, i znajdź mały krok.</p>
        </div>
        <Postac poza="detektyw" opis="Bibo w czapce detektywa z lupą" />
      </header>

      <div class="podzakladki" role="tablist" aria-label="Bibotektyw">
        <button type="button" role="tab" aria-selected={zakladka === "sledztwo"} class={zakladka === "sledztwo" ? "wybrana" : ""}
                onClick={() => idz("detektyw", true)}><IkonaLupa rozmiar={18} /> Śledztwo</button>
        <button type="button" role="tab" aria-selected={zakladka === "kartoteka"} class={zakladka === "kartoteka" ? "wybrana" : ""}
                onClick={() => idz("kartoteka", true)}><IkonaTeczka rozmiar={18} /> Kartoteka</button>
      </div>

      <div role="tabpanel">
        {zakladka === "kartoteka" ? <KartotekaTresc /> : (
          <div class="ekran">
            <ol class="kroki">
              {KROKI.map(({ I, tytul, opis }, i) => (
                <li key={tytul}>
                  <span class="krok-ikona" aria-hidden="true"><I rozmiar={22} /></span>
                  <span><b>{i + 1}. {tytul}</b><small>{opis}</small></span>
                </li>
              ))}
            </ol>
            {s && s.zamkniete > 0 && (
              <div class="statystyki">
                <div><strong>{s.zamkniete}</strong><span>spraw zamkniętych</span></div>
                <div><strong>{s.najczestszy?.emoji ?? "—"}</strong><span>{s.najczestszy ? <>najczęstszy podejrzany:<br /><b>{s.najczestszy.nazwa}</b></> : "najczęstszy podejrzany"}</span></div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
