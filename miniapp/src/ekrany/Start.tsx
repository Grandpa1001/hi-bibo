import { useEffect, useState } from "preact/hooks";
import { api, type Hub } from "../api";
import { idz, nowaSprawa } from "../stan";
import { Postac, usePrzyciski, type Poza } from "../ui/ui";

const POZY: Record<string, Poza> = { detektyw: "detektyw", misja10: "ruch", zrzut: "skupienie" };

function powitanie() {
  const h = new Date().getHours();
  if (h < 5 || h >= 22) return "Nocna zmiana,";
  if (h < 12) return "Dzień dobry,";
  if (h < 18) return "Cześć,";
  return "Dobry wieczór,";
}

export function Start() {
  const [hub, setHub] = useState<Hub | null>(null);
  useEffect(() => { api.hub().then(setHub).catch(() => setHub(null)); }, []);

  usePrzyciski(
    { tekst: "🕵️ Nowa sprawa", onClick: nowaSprawa },
    { tekst: "📂 Kartoteka", onClick: () => idz("kartoteka") },
  );

  const s = hub?.statystyki;
  return (
    <div class="ekran">
      <div class="hero">
        <div>
          <h1>{powitanie()}<br /><span>detektywie.</span></h1>
          <p>Czym się dziś zajmujemy?</p>
        </div>
        <Postac poza="detektyw" opis="Bibo w czapce detektywa z lupą" />
      </div>

      <div class="tryby">
        {(hub?.tryby ?? [{ id: "detektyw", nazwa: "Bibotektyw", opis: "Przesłuchaj wymówkę, która Cię blokuje", aktywny: true }]).map((t) => (
          <button type="button" key={t.id} class={`tryb ${t.aktywny ? "on" : ""}`} disabled={!t.aktywny}
                  onClick={t.aktywny ? nowaSprawa : undefined}>
            <span class="tryb-ikona"><Postac poza={POZY[t.id] ?? "logo"} /></span>
            <span class="tryb-opis"><b>{t.nazwa}</b><small>{t.opis}</small></span>
            <span class="tag">{t.aktywny ? "Graj" : "Wkrótce"}</span>
          </button>
        ))}
      </div>

      {s && s.zamkniete > 0 && (
        <div class="statystyki">
          <div><strong>{s.zamkniete}</strong><span>spraw zamkniętych</span></div>
          <div><strong>{s.obalone}</strong><span>wymówek obalonych</span></div>
          <div><strong>{s.najczestszy?.emoji ?? "—"}</strong><span>najczęstszy podejrzany</span></div>
        </div>
      )}
    </div>
  );
}
