# apeCAD logo

Caravaggio ape at the CAD desk: we see the back of the monitor; the
screen lights the face. Type is blueprint construction lettering.

Lock this folder as the brand source. Do not regenerate from chat
history.

## Palette

| Token | Hex | Use |
|---|---|---|
| Void | `#000000` | field |
| Paper | `#f4f0e6` | hat, lettering, frame |
| Vest | `#c64a1a` | orange / title underline |
| Fur | warm umber | painting only |

## Files

```text
logo/
  lockup.png                 full mark (ape + APE CAD + frame) 1024²
  icon.png                   ape only, for app / tab icons 1024²
  icon-simple.png            higher-contrast ape, 32px and under
  wordmark.png               painted wordmark plate
  wordmark.svg               vector wordmark on black
  wordmark-transparent.svg   vector wordmark, no fill
  og.png                     1200×630 Open Graph / hero
  favicon.ico                16 / 32 / 48
  web/
    favicon-32.png
    apple-touch-icon.png     180²
    icon-192.png
    icon-512.png
    lockup-512.png
```

## Use

- **Tab / shortcut / PWA:** `icon.png` at 192 and 512; `icon-simple.png`
  at 16–32. The painting does not read at favicon size without the
  simple crop.
- **Site header:** `icon.png` 32–40px beside `wordmark-transparent.svg`.
- **README / splash / social:** `lockup.png` or `og.png`.
- **Print / dark slide:** `lockup.png` on black only. There is no light
  variant yet.

Scratchpad chrome loads `web/favicon-32.png` and `favicon.ico`.
