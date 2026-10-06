/** Ikony liniowe w stylu postaci Bibo: gruba, zaokrąglona kreska w kolorze tekstu (currentColor).
 *  Zastępują emoji w interfejsie — emoji wyglądają inaczej na każdym telefonie i gryzą się z kreską ilustracji. */
import type { ComponentChildren } from "preact";
import type { Cwiartka, Uwaga } from "../api";

type P = { rozmiar?: number; klasa?: string };

function Svg({ rozmiar = 24, klasa, children }: P & { children: ComponentChildren }) {
  return (
    <svg class={`ikona ${klasa ?? ""}`} width={rozmiar} height={rozmiar} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
      {children}
    </svg>
  );
}

// --- nawigacja ---------------------------------------------------------------

export const IkonaDzis = (p: P) => (
  <Svg {...p}><circle cx="12" cy="12" r="4" /><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4" /></Svg>
);
export const IkonaGry = (p: P) => (
  <Svg {...p}>
    <path d="M7 8h10a5 5 0 0 1 4.6 6.9l-.4.9a2.6 2.6 0 0 1-4.3.7L15 14.5H9l-1.9 2a2.6 2.6 0 0 1-4.3-.7l-.4-.9A5 5 0 0 1 7 8z" />
    <path d="M7.5 10.5v3M6 12h3" /><circle cx="16" cy="11" r=".6" fill="currentColor" /><circle cx="17.8" cy="12.8" r=".6" fill="currentColor" />
  </Svg>
);
export const IkonaDalej = (p: P) => <Svg {...p}><path d="M9 5.5 15.5 12 9 18.5" /></Svg>;
export const IkonaPlus = (p: P) => <Svg {...p}><path d="M12 5v14M5 12h14" /></Svg>;

// --- osie siatki ---------------------------------------------------------------

export const IkonaPiorun = (p: P) => <Svg {...p}><path d="M13.5 2.5 5 13.5h6.5l-1 8 8.5-11h-6.5z" /></Svg>;
export const IkonaKsiezyc = (p: P) => <Svg {...p}><path d="M20 14.6A8.3 8.3 0 1 1 9.4 4a6.6 6.6 0 0 0 10.6 10.6z" /></Svg>;
export const IkonaUsmiech = (p: P) => (
  <Svg {...p}><circle cx="12" cy="12" r="9" /><path d="M8.3 14.2a4.6 4.6 0 0 0 7.4 0" /><path d="M9 9.6v.1M15 9.6v.1" stroke-width="2.8" /></Svg>
);
export const IkonaSmutek = (p: P) => (
  <Svg {...p}><circle cx="12" cy="12" r="9" /><path d="M8.3 16.2a4.6 4.6 0 0 1 7.4 0" /><path d="M9 9.6v.1M15 9.6v.1" stroke-width="2.8" /></Svg>
);

// --- tryby dnia (ćwiartki) ------------------------------------------------------

export const IkonaSzczyt = (p: P) => (
  <Svg {...p}><path d="M2.5 19.5 9 9.5l3.6 5.2 2.4-3.2 6.5 8z" /><path d="M17 3.5v3M15.5 5h3" /></Svg>
);
export const IkonaStabilnie = (p: P) => (
  <Svg {...p}><path d="M2.5 10c2.4-2.2 4.8-2.2 7.2 0s4.8 2.2 7.2 0 3.6-1.6 4.6-1" /><path d="M2.5 15.5c2.4-2.2 4.8-2.2 7.2 0s4.8 2.2 7.2 0 3.6-1.6 4.6-1" /></Svg>
);
export const IkonaNapiecie = (p: P) => <Svg {...p}><path d="M2.5 13 5.5 8l3.2 9 3.3-11 3.3 11 3.2-9 3 5" /></Svg>;
export const IkonaRegeneracja = (p: P) => (
  <Svg {...p}><rect x="2.5" y="7" width="16.5" height="10" rx="2.2" /><path d="M21.5 10.5v3" /><path d="m11.5 9.2-2.2 3.3h3.4l-2.2 3.3" /></Svg>
);
export const IkonaPytanie = (p: P) => (
  <Svg {...p}><circle cx="12" cy="12" r="9" /><path d="M9.6 9.4a2.5 2.5 0 1 1 3.4 2.3c-.6.3-1 .8-1 1.5v.6" /><path d="M12 16.9v.1" stroke-width="2.8" /></Svg>
);

export const IKONA_TRYBU: Record<Cwiartka, (p: P) => preact.JSX.Element> = {
  peak: IkonaSzczyt, steady: IkonaStabilnie, tension: IkonaNapiecie, recovery: IkonaRegeneracja,
};

// --- stan uwagi -----------------------------------------------------------------

export const IkonaRozproszony = (p: P) => (
  <Svg {...p}>
    <circle cx="5.5" cy="7" r="1.6" /><circle cx="17.5" cy="5.5" r="1.6" /><circle cx="12" cy="12.5" r="1.6" />
    <circle cx="5" cy="17.5" r="1.6" /><circle cx="18.5" cy="16" r="1.6" /><path d="M8.5 6.5 10 7M14 8.5l1.3-1M15 14.5l1.4.8M8.3 15.5l1.6-1" />
  </Svg>
);
export const IkonaWNormie = (p: P) => (
  <Svg {...p}><circle cx="12" cy="12" r="9" /><path d="m8 12.3 2.7 2.7L16.2 9.5" /></Svg>
);
export const IkonaHiperfokus = (p: P) => (
  <Svg {...p}><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1.2" fill="currentColor" /></Svg>
);

export const IKONA_UWAGI: Record<Uwaga, (p: P) => preact.JSX.Element> = {
  hypofocus: IkonaRozproszony, normal: IkonaWNormie, hyperfocus: IkonaHiperfokus,
};

// --- gry ------------------------------------------------------------------------

export const IkonaLupa = (p: P) => <Svg {...p}><circle cx="10.5" cy="10.5" r="6.5" /><path d="m15.4 15.4 5.6 5.6" /><path d="M8 8.6a3.3 3.3 0 0 1 2.6-1.6" /></Svg>;
export const IkonaTeczka = (p: P) => (
  <Svg {...p}><path d="M2.5 7.2c0-1.2 1-2.2 2.2-2.2h4.1l2 2.2h8.5c1.2 0 2.2 1 2.2 2.2v8.4c0 1.2-1 2.2-2.2 2.2H4.7c-1.2 0-2.2-1-2.2-2.2z" /><path d="M2.5 10.5h19" /></Svg>
);
export const IkonaZegar = (p: P) => <Svg {...p}><circle cx="12" cy="13" r="8" /><path d="M12 9v4.2l2.8 1.8M9.5 2.5h5" /></Svg>;
export const IkonaZrzut = (p: P) => <Svg {...p}><path d="M4 6h16M4 12h11M4 18h7" /><path d="m17 15.5 2 2.5 2.5-4" /></Svg>;
export const IkonaKrok = (p: P) => (
  <Svg {...p}><path d="M8.5 3.5c1.8 0 2.8 2.1 2.6 4.6-.2 2.2-1.2 3.4-2.6 3.4S6 10.3 5.9 8.1C5.7 5.6 6.7 3.5 8.5 3.5zM6.3 14h4.4l-.4 2.6a1.9 1.9 0 0 1-3.6 0z" />
    <path d="M15.5 8.5c1.8 0 2.8 2.1 2.6 4.6-.2 2.2-1.2 3.4-2.6 3.4S13 15.3 12.9 13.1c-.2-2.5.8-4.6 2.6-4.6zM13.3 19h4.4" /></Svg>
);

export const IKONA_GRY: Record<string, (p: P) => preact.JSX.Element> = {
  detektyw: IkonaLupa, misja10: IkonaZegar, zrzut: IkonaZrzut,
};
