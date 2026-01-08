# SETUP INSTRUCTIONS - Multi-Add-on Repository Structure

## What Changed

Your repository now uses the **multi-add-on structure**:

```
ha-addon-repository/                    ← Repository root
├── repository.yaml                     ← Required!
├── README.md                           ← Repository info
└── thread-coap-bridge/                 ← Add-on directory
    ├── config.yaml                     ← Add-on metadata
    ├── Dockerfile
    ├── build.yaml
    ├── requirements.txt
    ├── DOCS.md
    ├── README.md
    ├── INSTALL.md
    ├── LICENSE
    └── rootfs/
        ├── etc/services.d/
        └── app/
```

**Key points:**
- ✅ `repository.yaml` at root (tells HA this is a multi-add-on repo)
- ✅ Add-on files in `thread-coap-bridge/` subdirectory
- ✅ Fixed `config.yaml` (removed invalid image/privileged fields)

---

## How to Push to GitHub

### Option 1: Replace Existing Repository (Recommended)

```bash
# Extract the zip file
unzip ha-addon-repository.zip
cd ha-addon-repository

# Initialize git
git init
git add .
git commit -m "Multi-addon repository structure"

# Connect to your existing GitHub repository
git remote add origin https://github.com/Rosfly/thread-coap-bridge-addon.git

# Force push (replaces everything)
git branch -M main
git push -f origin main
```

### Option 2: Clone and Replace

```bash
# Clone your existing repo
git clone https://github.com/Rosfly/thread-coap-bridge-addon.git
cd thread-coap-bridge-addon

# Delete everything
rm -rf *
rm -rf .gitignore

# Extract new structure here
unzip ../ha-addon-repository.zip
mv ha-addon-repository/* .
mv ha-addon-repository/.gitignore . 2>/dev/null || true
rmdir ha-addon-repository

# Commit and push
git add -A
git commit -m "Restructure as multi-addon repository"
git push
```

---

## Verify on GitHub

After pushing, go to https://github.com/Rosfly/thread-coap-bridge-addon

You should see:
```
📄 repository.yaml       ← At root
📄 README.md
📁 thread-coap-bridge/   ← Add-on in subdirectory
```

Click into `thread-coap-bridge/` and verify you see:
```
📄 config.yaml
📄 Dockerfile
📁 rootfs/
```

---

## Test in Home Assistant

1. **Remove old repository:**
   - Settings → Add-ons → Add-on Store → ⋮ → Repositories
   - Remove `https://github.com/Rosfly/thread-coap-bridge-addon`

2. **Add it back:**
   - Click ⋮ → Repositories
   - Add: `https://github.com/Rosfly/thread-coap-bridge-addon`
   - Click **Add**

3. **Verify:**
   - Should NOT show error anymore ✅
   - Add-on should appear in the store
   - You can install it (even if it doesn't work yet)

---

## Why This Structure?

Home Assistant supports two repository types:

**Single Add-on (what you had):**
```
repo/
├── config.yaml    ← Add-on at root
└── Dockerfile
```
Works by adding the repo URL directly.

**Multi Add-on (what you have now):**
```
repo/
├── repository.yaml    ← Repository metadata
└── my-addon/
    ├── config.yaml    ← Add-on in subdirectory
    └── Dockerfile
```
Allows multiple add-ons in one repository.

Your repository now follows the **multi-add-on structure**, which is what Home Assistant was expecting based on the error message.

---

## Quick Test

After pushing to GitHub:

```bash
# Verify repository.yaml is accessible
curl https://raw.githubusercontent.com/Rosfly/thread-coap-bridge-addon/main/repository.yaml

# Should show:
# name: Thread IoT Add-ons
# url: https://github.com/Rosfly/thread-coap-bridge-addon
# maintainer: Rosfly

# Verify config.yaml is in subdirectory
curl https://raw.githubusercontent.com/Rosfly/thread-coap-bridge-addon/main/thread-coap-bridge/config.yaml

# Should show the add-on config
```

Both should return content (not 404) if the structure is correct.

---

## Troubleshooting

### Still getting "not a valid add-on repository"?

**Check:**
1. Is `repository.yaml` at the repository root? (not in a folder)
2. Is the add-on in a subdirectory? (`thread-coap-bridge/`)
3. Did you push to the correct branch? (main or master)
4. Is the repository public?

**View in browser:**
- Go to https://github.com/Rosfly/thread-coap-bridge-addon
- You should see `repository.yaml` and `thread-coap-bridge/` folder immediately
- Click into folder, see `config.yaml`

### Supervisor Logs

Check for specific errors:
- Settings → System → Logs → Supervisor
- Look for messages about your repository

---

## Next Steps

Once the add-on validates and installs:

1. **Configure** the add-on (MQTT credentials, etc.)
2. **Start** it (will run but won't do much yet)
3. **Check logs** to see it's running
4. **Implement** the Python code (CoAP/MQTT functionality)

The skeleton is complete - now you just need to fill in the TODOs in the Python modules!

---

## Summary

✅ Extracted zip has correct structure  
✅ Push to GitHub (force push OK since it's just you)  
✅ Add repository to Home Assistant  
✅ Should validate successfully  

This structure will work! Let me know if you see any errors after pushing.
