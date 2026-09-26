"""Generuje 3 karty wyniku (1200×630) do sendPhoto: public/karty/{obalona,czesciowo,uniewinniona}.png.

    python3 miniapp/narzedzia/karty.py --roboto Roboto.ttf --mono RobotoMono.ttf

Fonty: zmienne Roboto i Roboto Mono z github.com/google/fonts (licencja OFL) — nie trzymamy ich w repo.
Postaci: public/postaci/*.png (docelowo podmienione na eksporty 2×/3× — wtedy wygenerować ponownie).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

MINIAPP = Path(__file__).resolve().parents[1]
CZERN, BIEL, TURKUS, TURKUS_50 = (0, 0, 0), (255, 255, 255), (0, 150, 136), (224, 242, 241)

KARTY = {
    "obalona": ("radosc", "OBALONA", TURKUS, "Wymówka nie przetrwała przesłuchania."),
    "czesciowo": ("mysli", "CZĘŚCIOWO", CZERN, "Jest w niej ziarno prawdy. Ruszamy w mniejszej wersji."),
    "uniewinniona": ("skupienie", "UNIEWINNIONA", CZERN, "Tym razem wymówka miała rację."),
}


def font(sciezka: str, rozmiar: int, waga: int) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(sciezka, rozmiar)
    try:
        f.set_variation_by_axes([waga, 100] if len(f.get_variation_axes()) > 1 else [waga])
    except Exception:
        pass
    return f


def pieczatka(tekst: str, kolor, f: ImageFont.FreeTypeFont) -> Image.Image:
    l, t, r, b = f.getbbox(tekst)
    w, h = r - l + 56, b - t + 40
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((4, 4, w - 5, h - 5), radius=14, outline=kolor, width=8, fill=(255, 255, 255, 215))
    d.text((28 - l, 20 - t), tekst, font=f, fill=kolor)
    return img.rotate(10, resample=Image.BICUBIC, expand=True)


def karta(nazwa: str, roboto: str, mono: str) -> None:
    poza, napis, kolor, zdanie = KARTY[nazwa]
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), TURKUS_50)
    d = ImageDraw.Draw(img)

    # Komiksowa ramka z cieniem jak w UI (kontur 2 px × skala).
    d.rounded_rectangle((52, 52, W - 28, H - 28), radius=36, fill=CZERN)
    d.rounded_rectangle((36, 36, W - 44, H - 44), radius=36, fill=BIEL, outline=CZERN, width=6)

    # Postać (multiply na białym tle = czysta kreska).
    p = Image.open(MINIAPP / "public" / "postaci" / f"{poza}.png").convert("RGB")
    skala = 440 / p.height
    p = p.resize((round(p.width * skala), 440), Image.LANCZOS)
    img.paste(p, (90, (H - 440) // 2 + 6))

    x = 90 + p.width + 60
    d.text((x, 118), "BIBOTEKTYW · SPRAWA ZAMKNIĘTA", font=font(mono, 26, 700), fill=(94, 94, 94))
    d.text((x, 160), "Werdykt", font=font(roboto, 64, 900), fill=CZERN)
    st = pieczatka(napis, kolor, font(roboto, 76 if len(napis) < 10 else 62, 900))
    img.paste(st, (x - 10, 240), st)
    y_zdania = 240 + st.height + 18

    # Zdanie pod pieczątką, zawijane do szerokości.
    fz = font(roboto, 34, 500)
    slowa, linie, biezaca = zdanie.split(), [], ""
    for s in slowa:
        proba = f"{biezaca} {s}".strip()
        if fz.getlength(proba) > W - x - 90:
            linie.append(biezaca)
            biezaca = s
        else:
            biezaca = proba
    linie.append(biezaca)
    for i, linia in enumerate(linie[:2]):
        d.text((x, y_zdania + i * 46), linia, font=fz, fill=CZERN)

    cel = MINIAPP / "public" / "karty" / f"{nazwa}.png"
    img.save(cel, optimize=True)
    print(cel.relative_to(MINIAPP.parent), f"{cel.stat().st_size // 1024} KB")


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--roboto", required=True)
    a.add_argument("--mono", required=True)
    args = a.parse_args()
    for n in KARTY:
        karta(n, args.roboto, args.mono)
