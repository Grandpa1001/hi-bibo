import { useEffect, useState } from "preact/hooks";
import { api, BladApi, type Kartoteka as K } from "../api";
import { idz, nowaSprawa } from "../stan";
import { Czekanie, Dymek, Postac, usePrzyciski } from "../ui/ui";

const OBROT = ["-2deg", "1.5deg", "1deg", "-1.5deg", "-1deg", "2deg"];

export function Kartoteka() {
  const [k, setK] = useState<K | null>(null);
  const [blad, setBlad] = useState<string | null>(null);
  useEffect(() => {
    api.kartoteka().then(setK).catch((e) => setBlad(e instanceof BladApi ? e.message : "Nie udało się otworzyć kartoteki."));
  }, []);
  usePrzyciski({ tekst: "🕵️ Nowa sprawa", onClick: nowaSprawa }, null, () => idz("start"));

  if (blad) return <div class="ekran"><Dymek poza="mysli" etykieta="Kartoteka"><p>{blad}</p></Dymek></div>;
  if (!k) return <Czekanie poza="detektyw" tekst="Otwieram kartotekę" podpis="Podejrzani i sprawy" />;

  const lista = [...k.podejrzani].sort((a, b) => b.zatrzymania - a.zatrzymania);
  const lider = lista[0];
  return (
    <div class="ekran">
      <div class="kartoteka-naglowek">
        <div>
          <h1>Kartoteka</h1>
          <p>{lider ? <>Najczęstszy recydywista: {lider.emoji} {lider.nazwa}.</> : "Jeszcze pusto. Pierwsza sprawa czeka."}</p>
        </div>
        <Postac poza="detektyw" />
      </div>
      {lista.length > 0 && (
        <>
          <div class="tablica">
            {lista.map((p, i) => (
              <div class="teczka" style={{ "--obrot": OBROT[i % OBROT.length] }} key={p.nazwa}>
                <span class="teczka-emoji">{p.emoji}</span>
                <b>{p.nazwa}</b>
                <small>{p.zatrzymania} × zatrzymany · {p.obalone} obal.</small>
                <div class="kwadraty" aria-label={`${p.zatrzymania} zatrzymań, ${p.ruszylo} z ruszeniem`}>
                  {Array.from({ length: Math.min(p.zatrzymania, 10) }, (_, j) => <i class={j < p.ruszylo ? "ok" : ""} />)}
                </div>
              </div>
            ))}
          </div>
          <div class="legenda">
            <span><i /> zatrzymanie</span>
            <span><i class="ok" /> obalona + ruszyło</span>
          </div>
        </>
      )}
    </div>
  );
}
