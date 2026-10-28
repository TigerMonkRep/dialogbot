# Brand-kit generator

Regenerates every raster/vector brand asset from `docs/brand.md` (logo SVGs, app icons, OG image, social
profile kit, the `foto-*`/cover panels). Run from the repo root in this order:

```
pip install pillow fonttools brotli            # Python 3
python3 web/scripts/brand/make_fonts.py        # static Outfit/Inter TTFs from web/node_modules → .build/fonts/
python3 web/scripts/brand/svg_logo.py          # web/public/brand/logo*.svg (wordmark as Outfit 800 outlines)
NODE_PATH=$(npm root -g) node web/scripts/brand/svg2png.js jobs.json  # render logo-mark.svg → .build/mark-2048.png (Playwright/Chromium);
                                               # jobs.json: [{"svg": ".../logo-mark.svg", "out": ".../.build/mark-2048.png",
                                               #              "width": 2048, "height": 2048, "transparent": true}]
python3 web/scripts/brand/gen_assets.py        # every PNG/ICO under web/public/brand, web/public/icons, web/src/app
```

`brand.py` is the Pillow helper library (palette, fonts, mark, step squares, chips, cards, block shadow,
parts motif). `.build/` is scratch output and is not committed. After a run, copy
`.build/fonts/Outfit-ExtraBold.ttf` + `Outfit-Bold.ttf` and `web/public/brand/logo-mark-1024.png` (scaled to 512)
into `app/modules/social/assets/` if the fonts or the mark changed.
