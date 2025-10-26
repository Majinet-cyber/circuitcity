import io, os, re, sys

p = os.path.join("cc", "settings.py")
with io.open(p, "r", encoding="utf-8") as f:
    s = f.read()

# Replace any top-level 'accounts' entries with the correct dotted paths.
# We handle both plain "accounts" and "accounts.apps.AccountsConfig".
subs = [
    (r'([\'"])accounts\.apps\.AccountsConfig\1\s*,', r'"circuitcity.accounts.apps.AccountsConfig",'),
    (r'([\'"])accounts\1\s*,',                        r'"circuitcity.accounts.apps.AccountsConfig",'),
    (r'([\'"])inventory\1\s*,',                      r'"circuitcity.inventory",'),
    (r'([\'"])sales\1\s*,',                          r'"circuitcity.sales",'),
    (r'([\'"])dashboard\1\s*,',                      r'"circuitcity.dashboard",'),
]

for pat, repl in subs:
    s = re.sub(pat, repl, s)

with io.open(p + ".bak", "w", encoding="utf-8") as f:
    f.write(s)

# Write back updated file
with io.open(p, "w", encoding="utf-8") as f:
    f.write(s)

print("Patched:", p)


