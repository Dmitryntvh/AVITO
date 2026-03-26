# Zvezda Card Generator — MVP Technical Specification

## 1) Goal
Build an internal web service that generates a consistent series of product cards for bath tubs (банные чаны) from templates.

### Core outcomes
- Upload product photo.
- Select model/type and fill product attributes.
- Generate 8 PNG slides from JSON templates.
- Preview generated slides.
- Download single PNGs and full ZIP archive.

## 2) Product principles
- Template-based composition only (no free-form AI rendering in main pipeline).
- Product photo must keep original geometry (no stretching).
- Text must be rendered via fonts (`.ttf`), not embedded as raster text.
- Visual consistency across all slides.
- Production-ready flow for repeatable generation.

## 3) MVP output
Input:
- Product photo.
- Product attributes.
- Template series.

Output:
- 8 rendered PNG files.
- ZIP archive with all slides.
- UI preview.

## 4) Functional scope
1. Create/edit/delete product.
2. Upload product photo (PNG/JPG/JPEG/WEBP, max ~15 MB).
3. Select template series.
4. Generate all 8 slides.
5. Preview outputs.
6. Download one file, all files, or ZIP.

## 5) Slide set (8)
1. Cover.
2. Kit contents.
3. Easy assembly.
4. Specs.
5. Benefits.
6. Assembly process.
7. Delivery.
8. Final CTA.

## 6) Critical requirements
1. No geometry distortion of product photo.
2. No generative AI rendering in primary pipeline.
3. Sharp font-based text rendering.
4. Unified style and grid.
5. Reliability for mass generation later.

## 7) Proposed stack
- **Backend:** Python 3.11+, FastAPI.
- **Image rendering:** Pillow (+ optional OpenCV).
- **Archive:** Python `zipfile`.
- **Storage (MVP):** SQLite + filesystem.
- **Frontend:** React + Vite (or lightweight HTML/JS for first launch).

## 8) Suggested project structure
```text
project/
├─ apps/
│  ├─ api/
│  │  ├─ main.py
│  │  ├─ routes/
│  │  ├─ services/
│  │  ├─ models/
│  │  ├─ schemas/
│  │  ├─ db/
│  │  └─ utils/
│  └─ web/
│     └─ src/
├─ storage/
│  ├─ uploads/
│  ├─ outputs/
│  ├─ stickers/
│  ├─ backgrounds/
│  └─ fonts/
├─ templates/
│  └─ series_default/
└─ README.md
```

## 9) Data entities
### Product
`id, sku, name, model, type, capacity, diameter_mm, depth_mm, bowl_thickness_mm, furnace_thickness_mm, chimney_diameter_mm, material_bowl, material_furnace, description_short, photo_path, is_active, created_at, updated_at`

### TemplateSeries
`id, name, slug, canvas_width, canvas_height, safe_zone, background_mode, font_family_main, font_family_secondary, is_active`

### SlideTemplate
`id, series_id, slide_key, title, json_config_path, preview_image_path`

### GenerationJob
`id, product_id, series_id, status, output_dir, zip_path, created_at`

## 10) Template JSON requirements
Each slide template is JSON and contains:
- Canvas size.
- Safe zone.
- Background settings.
- `photo_box` (`x, y, width, height, fit, anchor`).
- Text blocks with style and positioning.
- Sticker definitions.

## 11) Rendering rules
### Photo fitting
- Keep aspect ratio.
- Support `contain` and `cover`.
- Default for product photo: `contain`.
- Center in `photo_box`.
- Avoid aggressive crop.

### Text layout
- Render from `.ttf` font files with Cyrillic support.
- Width constraints + wrapping.
- Auto font downscale if overflow.
- Align: `left | center | right`.

### Stickers
- On/off per slide.
- Predefined styles:
  - `orange_badge`
  - `gray_badge`
  - `dark_badge`
  - `outline_badge`

## 12) Variable substitution
Support placeholders:
- `{MODEL}` `{TYPE}` `{SKU}` `{CAPACITY}`
- `{DIAMETER}` `{DEPTH}`
- `{BOWL_THICKNESS}` `{FURNACE_THICKNESS}`
- `{CHIMNEY_DIAMETER}`
- `{MATERIAL_BOWL}` `{MATERIAL_FURNACE}`

## 13) API surface (MVP)
### Products
- `GET /products`
- `POST /products`
- `GET /products/{id}`
- `PUT /products/{id}`
- `DELETE /products/{id}`

### Uploads
- `POST /uploads/photo`

### Template series
- `GET /template-series`
- `GET /template-series/{id}`
- `GET /template-series/{id}/slides`

### Generation
- `POST /generate/{product_id}`
- `GET /generate/{job_id}`

## 14) Non-functional requirements
- Target: 8 slides in ~5–10 seconds for one product.
- Clear error reporting and logs.
- Slide-by-slide fault isolation.
- Extensible architecture for batch mode, Telegram bot, Excel import, and additional template series.

## 15) Out of scope for MVP
- AI image generation.
- Multi-role authorization.
- Full CRM.
- PostgreSQL.
- Marketplace publishing integrations.
- In-browser visual template editor.

## 16) Phased roadmap
### Week-1 style plan
- Day 1–2: backend skeleton, product CRUD, upload.
- Day 3–4: JSON templates + rendering core.
- Day 5: 8-slide generation + ZIP.
- Day 6: frontend forms + preview.
- Day 7: stabilization and local packaging.

## 17) Acceptance criteria
MVP is accepted when:
1. Product can be created in UI.
2. Product photo can be uploaded.
3. Template series can be selected.
4. All 8 slides can be generated.
5. Photo proportions remain intact.
6. Text is crisp and programmatically rendered.
7. ZIP download works.
8. Visual style is consistent.
9. Errors are understandable.
10. Local setup is straightforward.
