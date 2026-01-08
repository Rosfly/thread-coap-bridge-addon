# GitHub Repository Structure Guide

When publishing to GitHub, Home Assistant add-ons can be structured two ways:

## Option 1: Single Add-on Repository (Recommended - Simpler)

**Structure:** Add-on files directly at repository root.

```
ha-addon-thread-coap-bridge/          ← GitHub repository root
├── config.yaml                        ← Add-on metadata (HA uses this)
├── Dockerfile
├── build.yaml
├── requirements.txt
├── DOCS.md
├── README.md
├── INSTALL.md
├── CHANGELOG.md
├── LICENSE
└── rootfs/
    ├── etc/services.d/
    └── app/
```

**Setup steps:**

1. **Create GitHub repository:**
   ```bash
   # On your local machine
   cd thread-coap-bridge-addon
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/yourusername/ha-addon-thread-coap-bridge.git
   git push -u origin main
   ```

2. **Add to Home Assistant:**
   - Settings → Add-ons → Add-on Store → ⋮ → Repositories
   - Add URL: `https://github.com/yourusername/ha-addon-thread-coap-bridge`
   - ✅ Home Assistant detects `config.yaml` and recognizes it as a single add-on

**No `repository.yaml` needed!** The `config.yaml` file identifies it as an add-on.

---

## Option 2: Multi-Add-on Repository

**Structure:** Repository can contain multiple add-ons.

```
ha-addons-collection/                  ← GitHub repository root
├── repository.yaml                    ← Repository metadata (required)
├── thread-coap-bridge/                ← First add-on
│   ├── config.yaml
│   ├── Dockerfile
│   └── rootfs/
└── another-addon/                     ← Second add-on (future)
    ├── config.yaml
    └── ...
```

**repository.yaml contents:**

```yaml
name: Thread IoT Add-ons
url: https://github.com/yourusername/ha-addons-collection
maintainer: Your Name <your.email@example.com>
```

**Setup steps:**

1. **Create repository structure:**
   ```bash
   mkdir ha-addons-collection
   cd ha-addons-collection
   
   # Create repository.yaml
   cat > repository.yaml << 'EOF'
   name: Thread IoT Add-ons
   url: https://github.com/yourusername/ha-addons-collection
   maintainer: Your Name <your.email@example.com>
   EOF
   
   # Move add-on into subdirectory
   mkdir thread-coap-bridge
   # Copy all add-on files into thread-coap-bridge/
   
   git init
   git add .
   git commit -m "Initial commit"
   git push -u origin main
   ```

2. **Add to Home Assistant:**
   - Add URL: `https://github.com/yourusername/ha-addons-collection`
   - ✅ Home Assistant reads `repository.yaml` and discovers all add-ons in subdirectories

---

## Which Structure Should You Use?

| Scenario | Recommendation |
|----------|----------------|
| Just this one add-on | **Option 1** (simpler) |
| Planning multiple related add-ons | **Option 2** |
| Want to keep it simple | **Option 1** |
| Want professional appearance | Either works |

---

## Current Package Structure

The zip file you downloaded is structured as **Option 1** (single add-on).

To use it:

**For Option 1 (recommended):**
```bash
# Extract zip
unzip thread-coap-bridge-addon.zip

# The files are ready to push to GitHub root
cd thread-coap-bridge-addon
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/yourusername/ha-addon-thread-coap-bridge.git
git push -u origin main
```

**For Option 2 (multi-add-on repo):**
```bash
# Create parent repository
mkdir ha-addons-collection
cd ha-addons-collection

# Extract your add-on into subdirectory
unzip ../thread-coap-bridge-addon.zip

# Create repository.yaml (use the file I created)
cat > repository.yaml << 'EOF'
name: Thread IoT Add-ons
url: https://github.com/yourusername/ha-addons-collection
maintainer: Your Name <your.email@example.com>
EOF

git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/yourusername/ha-addons-collection.git
git push -u origin main
```

---

## Testing Your Repository Structure

**Before pushing to GitHub, verify locally:**

```bash
# Option 1 structure check
ls -la
# Should see: config.yaml, Dockerfile, rootfs/, etc. at root

# Option 2 structure check
ls -la
# Should see: repository.yaml at root
ls -la thread-coap-bridge/
# Should see: config.yaml, Dockerfile, etc. in subdirectory
```

**After pushing to GitHub:**

1. **Check repository structure on GitHub website**
   - For Option 1: config.yaml should be visible at root
   - For Option 2: repository.yaml should be visible at root

2. **Add repository to Home Assistant**
   - Settings → Add-ons → Add-on Store → ⋮ → Repositories
   - Add your GitHub URL
   - Click "Add"

3. **Verify it works**
   - Refresh add-on store
   - Your add-on should appear in the list
   - If you see "Repository is not compatible", check the structure

---

## Common Issues

### "Repository is not compatible"

**Cause:** Home Assistant can't find either:
- `config.yaml` (Option 1)
- `repository.yaml` (Option 2)

**Fix:**
- Verify file is at correct location
- Check filename spelling (case-sensitive!)
- Make sure file was committed to git: `git ls-files`

### "No add-ons found in repository"

**For Option 2 only:**

**Cause:** `repository.yaml` exists but add-ons aren't in subdirectories

**Fix:**
```bash
# Check structure
ls -la
# Should show:
# repository.yaml
# thread-coap-bridge/
#   └── config.yaml
```

### Files not showing on GitHub

**Cause:** Forgot to commit or push

**Fix:**
```bash
git status                    # Check what's not committed
git add .                     # Add all files
git commit -m "Add files"     # Commit
git push                      # Push to GitHub
```

---

## Recommendation for You

Since you're building a single add-on, use **Option 1**:

1. Extract the zip
2. `cd thread-coap-bridge-addon`
3. `git init && git add . && git commit -m "Initial commit"`
4. Push to GitHub (files at repository root)
5. Add GitHub URL to HA

**No repository.yaml needed** - the `config.yaml` is sufficient!

---

## Quick Test Commands

**Verify your structure is correct before pushing:**

```bash
# For Option 1 (single add-on)
cd thread-coap-bridge-addon
test -f config.yaml && echo "✅ config.yaml found at root" || echo "❌ config.yaml missing"
test -f Dockerfile && echo "✅ Dockerfile found" || echo "❌ Dockerfile missing"
test -d rootfs && echo "✅ rootfs directory found" || echo "❌ rootfs missing"

# For Option 2 (multi-add-on)
test -f repository.yaml && echo "✅ repository.yaml found" || echo "❌ repository.yaml missing"
test -f thread-coap-bridge/config.yaml && echo "✅ Add-on config.yaml found" || echo "❌ Add-on config.yaml missing"
```

Let me know which structure you prefer and I can provide the exact commands!
