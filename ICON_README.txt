# Add-on Icons

Home Assistant add-ons require icon images. These files are not included in this distribution.

## Required Files

1. **icon.png** - 256x256 pixels, shown in add-on store
2. **logo.png** - (optional) larger logo for branding

## Creating Icons

### Option 1: Use a simple design tool

- Canva (https://www.canva.com/)
- Figma (https://www.figma.com/)
- GIMP (https://www.gimp.org/)

### Option 2: Icon generators

- https://favicon.io/
- https://www.favicon-generator.org/

### Design Suggestions

**icon.png (256x256):**
- Thread mesh network pattern (hexagons)
- CoAP symbol or radio waves
- Colors: Blue/green (connectivity theme)
- Keep it simple - will be displayed small

**Example design elements:**
- Hexagonal mesh pattern (Thread)
- Bidirectional arrows (bridge concept)
- House icon (Home Assistant)
- Radio/wireless symbol

### Placeholder Command

If you just want to test without icons:

```bash
# Create a simple colored square placeholder
convert -size 256x256 xc:#0288d1 icon.png
convert -size 512x512 xc:#0288d1 logo.png
```

(Requires ImageMagick installed)

### Where to place them

```
thread-coap-bridge-addon/
├── icon.png       # Place here
└── logo.png       # Place here (optional)
```

The add-on will work without icons, but they make it look more professional!
