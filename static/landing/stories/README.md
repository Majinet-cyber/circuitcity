# Stories Image Assets — EMAJINET Landing Page

## How to add your images (one command)

1. Open PowerShell
2. Navigate to the folder where your original images live (with spaces in the names)
3. Run the helper script:

```powershell
cd "C:\path\to\your\images\folder"
& "C:\Users\CHRIS PAUL MWALE\PycharmProjects\circuitcity_clean\copy_story_images.ps1"
```

The script will automatically copy and rename every file to this folder.

---

## Filename mapping (what to rename to)

| Original filename             | Safe name (goes here)         |
|-------------------------------|-------------------------------|
| gym Dashboard.png             | gym-dashboard.png             |
| gym dashboard 1.png           | gym-dashboard-1.png           |
| gym member public view.png    | gym-member-public-view.png    |
| gym member QR code.png        | gym-member-qr-code.png        |
| gym member.png                | gym-member.png                |
| GYM QR code.jpg               | gym-qr-code.jpg               |
| manual gym entry.jpg          | manual-gym-entry.jpg          |
| manual gym records.jpg        | manual-gym-records.jpg        |
| members payment status.png    | members-payment-status.png    |
| payment status.png            | payment-status.png            |
| phamarcy app sales.jpg        | pharmacy-app-sales.jpg        |
| phamarcy sales agent.jpg      | pharmacy-sales-agent.jpg      |
| Phamarcy stock.jpg            | pharmacy-stock.jpg            |
| training.jpg                  | gym-training.jpg              |
| Yohane Kajanga Gym owner.jpg  | yohane-kajanga.jpg            |
| zaina.jpg                     | zaina.jpg                     |

---

## Used in the template

**Gym carousel slide (Story 1)**
- `manual-gym-entry.jpg` — Before label
- `manual-gym-records.jpg` — Before label
- `gym-qr-code.jpg` — QR label
- `gym-member-qr-code.png` — QR label
- `gym-dashboard.png` — Dashboard label
- `members-payment-status.png` — Payment status label

**Pharmacy carousel slide (Story 2)**
- `pharmacy-stock.jpg` — Stock label
- `pharmacy-sales-agent.jpg` — In use label
- `pharmacy-app-sales.jpg` — Mobile sales label

**Testimonials**
- `yohane-kajanga.jpg` — Yohane Kajanga photo
- `zaina.jpg` — Zaina photo

---

Until images are placed here, the template gracefully shows a dashed placeholder
box labelled "Image coming soon" — the layout remains intact.
After copying, do a hard-refresh (Ctrl+Shift+R) in the browser to see images.
