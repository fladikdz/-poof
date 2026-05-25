# Steam Deck (SteamOS) — Setup for PGP BLE Emulator

This is the testing target for the Iteration 5 BLE peripheral work. SteamOS is
Arch-based Linux with BlueZ, which fully supports BLE peripheral role out of
the box.

## One-time setup

Switch to **Desktop Mode** (long-press power button → "Switch to Desktop"),
then open **Konsole**.

### 1. Set a sudo password if you haven't

```bash
passwd
```

### 2. Transfer the project

Easiest path: USB stick with the `poof/` directory copied from your main PC.
Plug it in, copy to `/home/deck/poof`.

Alternatives:
- `scp -r user@mainpc:/path/to/poof /home/deck/`
- `git clone <your repo>` if pushed somewhere

### 3. Python + venv

Python 3 is preinstalled on SteamOS. Create the venv:

```bash
cd /home/deck/poof
python3 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -U pip
pip install -r backend/requirements.txt
```

On SteamOS the system filesystem is read-only by default, but `/home/deck` is
fully writable so the venv works without touching `/`.

If `pip install` errors with "externally-managed-environment", that only
applies to the system Python — our venv is unaffected.

### 4. Place the master key

There are two paths depending on whether you have real PGP credentials.

**A) Real credentials (only works against Pokemon GO):**
Extract MAC + BLOB + device_key from a physical Pokemon Go Plus accessory using the
firmware-tools at https://github.com/yohanes/pgpemu/tree/master/firmware-tools .
Place the device_key (16 raw bytes) at `backend/data/pgp_master_key.bin`.

**B) Test placeholder (for verifying BLE peripheral works at all):**

```bash
python backend/cli_pgp.py init-test-key
```

This generates 16 random bytes. iPhone will discover and may pair with the
emulator, but Pokemon GO server-side validation will reject. Useful only to
confirm the BLE stack on this machine is working before you invest in real
credentials.

### 5. Verify BlueZ is ready

```bash
bluetoothctl show | grep -i 'le advertising'
# Expect: "Roles: peripheral, central"  or  "AdvertisingFlags: ..."

systemctl status bluetooth | head -3
# Expect: active (running)
```

## Run

```bash
cd /home/deck/poof
source backend/.venv/bin/activate
python backend/cli_pgp.py status
# Should print: Transport: BlueZ via dbus-next (ready)
#               Master key: loaded OK

python backend/cli_pgp.py start
# Advertises as 'Pokemon GO Plus' until Ctrl+C.
```

On the iPhone: **Settings → Bluetooth**, wait for "Pokemon GO Plus" to appear,
tap it to pair. Pokémon GO with BLE accessory support enabled should then see
it as a paired aksесsuar.

## Troubleshooting

- **"Adapter is missing required interfaces"** — BlueZ is too old (<5.50) or
  the chipset doesn't expose peripheral role. SteamOS ships a recent enough
  BlueZ; if this happens, check `bluetoothctl show` to confirm the adapter
  status.
- **"Operation not permitted" during advertising** — usually a `bluez` daemon
  permission issue. Try `sudo systemctl restart bluetooth`.
- **iPhone doesn't see the device** — `bluetoothctl scan on` from another
  Linux machine should also see it. If only iPhone misses it, the LocalName
  may need to be advertised differently — file issue.
- **Authentication failure during pair** — almost always a master-key
  mismatch. Re-check that `pgp_master_key.bin` is exactly 16 bytes and
  matches the key your reference pgpemu uses.

## Returning to gaming

When done, just close Konsole, click "Return to Gaming Mode" on the desktop.
The emulator stops cleanly (it releases advertising + GATT on `Ctrl+C`).
