import { useEffect, useState } from "preact/hooks";
import { api, BladApi, type Kartoteka as K } from "../api";
import { Dymek } from "../ui/ui";

const OBROT = ["-2deg", "1.5deg", "1deg", "-1.5deg", "-1deg", "2deg"];

/** Treść podzakładki „Kartoteka” w Bibotektywie. Przyciski natywne deklaruje strona gry (ekran-liść). */
export function KartotekaTresc() {
  const [k, setK] = useState<K | null>(null);
  const [blad, setBlad] = useState<string | null>(null);
  useEffect(() => {
    api.kartoteka().then(setK).catch((e) => setBlad(e instanceof BladApi ? e.message : "Nie udało się otworzyć kartoteki."));
  }, []);

  if (blad) return <div class="ekran"><Dymek poza="mysli" etykieta="Kartoteka"><p>{blad}</p></Dymek></div>;
  if (!k) return <p class="ladowanie" aria-live="polite"><span class="kropki" aria-hidden="true"><i /><i /><i /></span> Otwieram kartotekę</p>;

  const lista = [...k.podejrzani].sort((a, b) => b.zatrzymania - a.zatrzymania);
  const lider = lista[0];
  return (
    <div class="ekran">
      <p class="podpowiedz-tekst">{lider ? <>Najczęściej wracający podejrzany: {lider.emoji} {lider.nazwa}.</> : "Jeszcze pusto. Pierwsza sprawa czeka."}</p>
      {lista.length > 0 && (
        <>
          <div class="tablica">
            {lista.map((p, i) => (
              <div class="teczka" style={{ "--obrot": OBROT[i % OBROT.length] }} key={p.nazwa}>
                <span class="teczka-emoji">{p.emoji}</span>
                <b>{p.nazwa}</b>
                <small>{p.zatrzymania} × zatrzymany</small>
                <div class="kwadraty" aria-label={`${p.zatrzymania} zatrzymań, ${p.ruszylo} z ruszeniem`}>
                  {Array.from({ length: Math.min(p.zatrzymania, 10) }, (_, j) => <i class={j < p.ruszylo ? "ok" : ""} />)}
                </div>
              </div>
            ))}
          </div>
          <div class="legenda">
            <span><i /> zatrzymanie</span>
            <span><i class="ok" /> ruszyło</span>
          </div>
        </>
      )}
    </div>
  );
}
